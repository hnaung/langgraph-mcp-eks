# AI Platform Security Architecture Proposal

**Document type:** Security Architecture Proposal  
**Platform:** Agentic AI on AWS EKS  
**Stack:** LangGraph · MCP · FastAPI · Amazon Bedrock · Kubernetes  
**Classification:** Internal  
**Status:** Reference implementation — see [langgraph-mcp-eks](https://github.com/hnaung/langgraph-mcp-eks)

---

## Executive Summary

Organizations are rapidly adopting **agentic AI** — systems where an LLM autonomously plans actions, calls tools, and executes multi-step workflows. Unlike traditional chatbots, agents can invoke external APIs, read internal data, and chain operations without human approval at each step. This creates new attack surfaces that existing application security models do not fully address.

This proposal defines a **security-first agentic AI platform** deployed on **AWS EKS**, designed to:

- Accept natural-language requests from authenticated users
- Plan and execute tool calls via a governed LLM (Amazon Bedrock)
- Enforce defense-in-depth across input, orchestration, tool access, network, and infrastructure layers
- Provide auditability, least privilege, and operational controls suitable for enterprise deployment

The accompanying repository (`langgraph-mcp-eks`) is a **working reference implementation** of this architecture. It is intended for security review, engineering evaluation, and as a blueprint for production deployment.

### Key outcomes

| Outcome | How it is achieved |
|---|---|
| Prevent prompt injection abuse | Multi-layer input validation before LLM invocation |
| Limit blast radius of agent actions | Tool allowlist, schema validation, hop limits |
| No long-lived credentials in pods | IRSA (IAM Roles for Service Accounts) |
| Network isolation between components | Kubernetes NetworkPolicy default-deny |
| Supply chain integrity | Pinned dependencies, signed container images |
| Full audit trail | Structured JSON logs with trace IDs |

---

## 1. Background & Problem Statement

### 1.1 Why agentic AI needs a different security model

Traditional web applications follow a predictable request → business logic → database pattern. Security controls (WAF, input validation, RBAC) are well understood.

**Agentic AI systems differ in three critical ways:**

1. **Non-deterministic execution** — The LLM decides which tools to call and in what order. The same input may produce different execution paths.
2. **Prompt as attack vector** — Users (or injected content) can attempt to override system instructions, exfiltrate secrets, or trigger unintended tool calls.
3. **Tool amplification** — A single accepted prompt can cascade into multiple API calls, data reads, or external actions before a human intervenes.

Without deliberate architecture, an AI agent becomes a **privileged automation engine** that attackers can steer via natural language.

### 1.2 Business objectives

| Objective | Description |
|---|---|
| Enable safe AI automation | Allow teams to deploy agents that call internal and external tools |
| Meet enterprise security bar | IRSA, network segmentation, secret management, audit logging |
| Support developer velocity | Local development with Cursor + MCP; same tools in dev and prod |
| Maintain AWS-native posture | Bedrock for LLM, EKS for compute, Secrets Manager for credentials |

### 1.3 Scope

**In scope:**

- REST API for agent queries (`POST /v1/query`)
- LangGraph orchestration (validate → plan → tool → respond)
- MCP-based tool servers (weather implemented; ServiceNow, RAG as extension points)
- AWS EKS deployment with hardened Kubernetes manifests
- Local development workflow via Cursor IDE

**Out of scope (this reference repo):**

- Full JWT/OAuth implementation (planned at ingress/API layer)
- Amazon Bedrock Guardrails integration (recommended for production)
- ServiceNow and RAG MCP servers (stubs documented)
- Multi-tenant isolation and per-tenant RBAC

---

## 2. Proposed Architecture

### 2.1 High-level topology

```
Internet
   │
   ▼
Route 53 (DNS)
   │
   ▼
AWS WAF (rate limiting, managed rule groups, geo restrictions)
   │
   ▼
Application Load Balancer (TLS 1.2+, security headers)
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│                        AWS EKS Cluster                          │
│                                                                 │
│  ┌──────────────┐      ┌─────────────────────────────────┐   │
│  │  FastAPI     │─────►│  LangGraph Agent                │   │
│  │  (API layer) │      │  validate → plan → tools → end  │   │
│  └──────────────┘      └──────────────┬──────────────────┘   │
│                                       │                         │
│              ┌────────────────────────┼────────────────┐       │
│              ▼                        ▼                ▼       │
│     ┌────────────────┐    ┌───────────────┐   ┌────────────┐  │
│     │ MCP: Weather   │    │ MCP: Service  │   │ MCP: RAG   │  │
│     │ (port 9001)    │    │ Now (9002)    │   │ (9003)     │  │
│     └───────┬────────┘    └───────────────┘   └────────────┘  │
│             │                                                   │
└─────────────┼───────────────────────────────────────────────────┘
              │
              ▼
     Amazon Bedrock (Claude Sonnet, via VPC endpoint)
     AWS Secrets Manager (API keys, via IRSA)
     OpenWeatherMap / internal APIs (external tool backends)
```

### 2.2 Component responsibilities

| Component | Responsibility | Security role |
|---|---|---|
| **FastAPI (`main.py`)** | HTTP entry point, request/response schema | Host allowlist, error sanitization, trace IDs |
| **LangGraph (`agent/graph.py`)** | State machine orchestration | Input validation gate, hop limit enforcement |
| **Tool allowlist (`agent/tools.py`)** | Defines callable functions | LLM cannot invoke arbitrary code |
| **MCP servers (`mcp_server/`)** | Tool microservices via MCP protocol | Schema validation, output filtering, network isolation |
| **Amazon Bedrock** | LLM inference | IAM-scoped model access, VPC endpoint |
| **IRSA / Secrets Manager** | Credential delivery | No static keys in pods or config |

### 2.3 Request lifecycle

Every query passes through a fixed state machine:

```
START → validate_input → planner → [tools → planner]* → END
                              ↑__________|
                         (max 5 tool hops)
```

1. **validate_input** — Reject prompt injection patterns, oversize input, score secret-related keywords
2. **planner** — Bedrock receives conversation + allowlisted tool definitions; may return tool calls
3. **tools** — Execute only allowlisted tools with parameter validation
4. **Loop or finish** — Repeat up to `MAX_TOOL_HOPS` (5), then return final answer

This design makes agent behavior **auditable and bounded** — every step is a named node with testable logic.

---

## 3. Security Architecture

Security is implemented in **six layers**. No single layer is sufficient on its own.

### Layer 1 — Edge & perimeter

| Control | Implementation |
|---|---|
| TLS termination | ALB with TLS 1.2 minimum, TLS 1.3 preferred (`ELBSecurityPolicy-TLS13-1-2-2021-06`) |
| WAF | AWS WAFv2 attached to ALB — managed rule groups, rate limiting |
| Security headers | HSTS, X-Frame-Options DENY, X-Content-Type-Options nosniff |
| Access logging | ALB logs to S3 for forensics |
| Host restriction | TrustedHostMiddleware on FastAPI |

**Reference:** `k8s/ingress.yaml`

### Layer 2 — Input validation (prompt injection defense)

Applied **before** any LLM call in `agent/graph.py`:

| Check | Detail |
|---|---|
| Injection patterns | Regex blocklist: "ignore previous instructions", "disregard system prompt", "you are now", "forget everything", `<script>` tags |
| Length limit | Reject inputs over 4,096 characters |
| Risk scoring | Elevate score when input contains secret-related keywords (`api_key`, `password`, `token`, etc.) |

**Reference:** `agent/graph.py`, `tests/test_security.py`

> **Production recommendation:** Add Amazon Bedrock Guardrails as Layer 2b for content filtering and denied topic enforcement.

### Layer 3 — Tool schema validation

Every tool parameter is validated before execution:

| Tool | Validation |
|---|---|
| `get_weather` | City: letters/spaces/hyphens only, max 64 chars; units: `metric` or `imperial` only |
| `search_knowledge_base` | Min query length 3; special characters stripped |

Invalid parameters raise errors — they are never passed to upstream APIs.

**Reference:** `agent/tools.py`, `mcp_server/weather_server.py`

### Layer 4 — Tool allowlist

The LLM is bound to an explicit list of tools via `ALLOWED_TOOLS` in `agent/tools.py`. Adding a new tool requires:

1. Code implementation with input/output filtering
2. Security review of the tool schema
3. Addition to the allowlist
4. NetworkPolicy update if the tool calls a new MCP pod
5. IAM policy update if new AWS permissions are needed

The agent **cannot** invoke shell commands, arbitrary HTTP endpoints, or undeclared functions.

### Layer 5 — Agent hop limit

`MAX_TOOL_HOPS = 5` prevents runaway agent loops where the LLM repeatedly calls tools without terminating. After 5 tool invocations, the agent stops and returns.

This mitigates cost abuse, denial-of-service via tool flooding, and unbounded autonomous behavior.

**Reference:** `agent/graph.py`, `tests/test_security.py`

### Layer 6 — Output validation

Tool implementations return **only approved fields** — never raw upstream API responses. This prevents accidental data leakage (internal IDs, API keys in response bodies, PII beyond what is needed).

Example: `get_weather` returns `{city, temp, condition, humidity}` — not the full OpenWeatherMap JSON.

---

## 4. Infrastructure Security

### 4.1 Identity — IRSA (no static credentials)

Pods assume IAM roles via EKS OIDC federation. The service account annotation links the pod to a least-privilege IAM role.

**IAM permissions (reference policy):**

| Permission | Resource | Purpose |
|---|---|---|
| `secretsmanager:GetSecretValue` | `prod/*` secrets in `ap-southeast-1` | Retrieve API keys at runtime |
| `bedrock:InvokeModel` | Claude Sonnet foundation model | LLM inference |

**Reference:** `iam/irsa-policy.json`, `k8s/serviceaccount.yaml`

### 4.2 Secret management

| Environment | Secret source |
|---|---|
| Production (EKS) | AWS Secrets Manager, fetched at runtime via boto3 + IRSA |
| Local development | `.env` file (never committed; excluded via `.gitignore` and `.cursorignore`) |
| Cursor AI context | `.cursorignore` blocks `.env`, IAM policies, prod Helm values |

Production secrets auto-rotate on a 30-day schedule (Secrets Manager configuration, outside this repo).

### 4.3 Container hardening

| Control | Value |
|---|---|
| Run as non-root | UID 1001 |
| Read-only root filesystem | `readOnlyRootFilesystem: true` |
| Capabilities | Drop ALL |
| Privilege escalation | Disabled |
| seccomp | RuntimeDefault (blocks 300+ syscalls) |
| Writable storage | Memory-backed `/tmp` emptyDir only |
| Resource limits | CPU 1 core, memory 1 GiB max |
| Image pinning | By digest, not `:latest` |
| automountServiceAccountToken | false (except where IRSA requires) |

**Reference:** `k8s/deployment.yaml`, `Dockerfile`, `helm/values-prod.yaml`

### 4.4 Network isolation

NetworkPolicy implements **default deny** for the agent pod:

| Direction | Allowed |
|---|---|
| Ingress | Only from ALB ingress controller on port 8080 |
| Egress | MCP weather server (port 9000), IMDS for IRSA (169.254.169.254), HTTPS (443) for Bedrock via VPC endpoint |

MCP server pods are not publicly routable — ClusterIP services only.

**Reference:** `k8s/networkpolicy.yaml`, `k8s/service.yaml`

**Production recommendation:** Istio service mesh for mTLS on east-west traffic (sidecar injection annotation present in deployment manifest).

### 4.5 High availability & resilience

| Control | Setting |
|---|---|
| Minimum replicas | 2 (no single point of failure) |
| HPA | Scale 2–6 pods at 70% CPU / 80% memory |
| PodDisruptionBudget | minAvailable: 1 during node drains |
| Health checks | Liveness and readiness probes on `/health` |

**Reference:** `k8s/hpa.yaml`, `k8s/deployment.yaml`

### 4.6 Supply chain security

| Control | Implementation |
|---|---|
| Pinned dependencies | `requirements.txt` with version pins |
| Multi-stage Docker build | Build tools excluded from runtime image |
| Image signing | Cosign sign after ECR push |
| Vulnerability scanning | Trivy scan in CI pipeline (recommended) |
| No package manager in runtime | apt packages purged from final image |

---

## 5. Threat Model

### 5.1 Threat actors

| Actor | Motivation | Example attack |
|---|---|---|
| External attacker | Data exfiltration, service abuse | Prompt injection to override agent behavior |
| Malicious insider | Access internal tools via agent | Craft queries to invoke unauthorized tool parameters |
| Compromised dependency | Supply chain attack | Malicious Python package in tool code |
| Runaway agent | Unintended autonomous behavior | Infinite tool call loop causing cost/abuse |

### 5.2 STRIDE analysis (selected)

| Threat | Category | Mitigation |
|---|---|---|
| Prompt injection overrides system instructions | Tampering | Layer 2 input validation + Bedrock Guardrails (prod) |
| Agent calls unauthorized external API | Elevation of privilege | Layer 4 tool allowlist + Layer 3 schema validation |
| Stolen pod credentials access all AWS resources | Information disclosure | IRSA least privilege — only Secrets Manager + Bedrock |
| Lateral movement from agent pod to other services | Spoofing / Tampering | NetworkPolicy default-deny + Istio mTLS |
| Unbounded tool calls drain budget | Denial of service | Layer 5 hop limit + HPA max replicas + WAF rate limiting |
| Secrets in container env vars leaked via logs | Information disclosure | Secrets Manager at runtime; no secrets in env/config |

### 5.3 Residual risks

| Risk | Status | Recommendation |
|---|---|---|
| JWT auth not yet implemented in reference API | Open | Implement at API or ingress layer before production |
| Bedrock Guardrails not wired in code | Open | Enable for content filtering and PII detection |
| `/ready` probe referenced in K8s but not in FastAPI | Open | Add readiness endpoint checking Bedrock connectivity |
| ServiceNow / RAG tools are stubs | Planned | Full implementation with same security pattern as weather |

---

## 6. Development Security — Cursor IDE

This platform is developed using **[Cursor](https://cursor.com)**, an AI-native IDE. Security considerations for AI-assisted development:

| Concern | Mitigation |
|---|---|
| API keys exposed to AI context | `.cursorignore` excludes `.env`, IAM, prod values |
| AI generates insecure tool code | Code review + security tests on every PR |
| Local MCP server runs with user privileges | stdio transport only; no network exposure |
| Dev/prod parity | Same MCP protocol and tool code locally and in EKS |

Developers test MCP tools in Cursor chat before deploying to Kubernetes. See [CURSOR_DEVELOPMENT.md](CURSOR_DEVELOPMENT.md).

---

## 7. Observability & Audit

### 7.1 Structured logging

Every request emits JSON logs with a shared `trace_id`:

```json
{"event": "input_validated", "len": 89, "trace_id": "f47ac10b"}
{"event": "planner_response", "tool_calls": 1, "trace_id": "f47ac10b"}
{"event": "tool_call", "tool": "get_weather", "input": {"city": "Singapore"}}
{"event": "query_success", "tools_used": ["get_weather"], "duration_ms": 1243}
```

### 7.2 Audit trail components

| Source | Data captured |
|---|---|
| Application logs | Input validation, tool calls, errors, duration |
| ALB access logs | Source IP, request path, response code |
| AWS CloudTrail | IAM role assumption, Secrets Manager access, Bedrock API calls |
| WAF logs | Blocked requests, rate limit triggers |
| OpenTelemetry (planned) | Distributed traces across agent → MCP → Bedrock |

### 7.3 Runtime threat detection (production)

| Tool | Purpose |
|---|---|
| Falco | Syscall anomaly detection in pods |
| GuardDuty EKS Protection | Cluster-level threat detection |
| Prometheus + alerts | CPU/memory anomalies, error rate spikes |

---

## 8. Design Trade-offs

### 8.1 LangGraph vs direct LLM calls

| | LangGraph | Direct LLM |
|---|---|---|
| **Pros** | Explicit flow, testable nodes, hop limits, audit points | Simpler code, faster to prototype |
| **Cons** | More boilerplate | Hard to enforce boundaries, opaque execution |
| **Decision** | LangGraph — security and auditability outweigh simplicity cost |

### 8.2 MCP pods vs in-process tools

| | MCP pods | In-process |
|---|---|---|
| **Pros** | Independent deploy/scale, team ownership, standard protocol | Lower latency, simpler local dev |
| **Cons** | Network hop, more K8s resources | Shared fate with agent pod, harder to isolate |
| **Decision** | Both — in-process for LangGraph agent, MCP servers for production isolation and Cursor dev parity |

### 8.3 Amazon Bedrock vs OpenAI

| | Bedrock | OpenAI API |
|---|---|---|
| **Pros** | AWS-native, VPC endpoint, IAM auth, data stays in AWS | Easier local dev, broader model selection |
| **Cons** | Requires AWS account, region availability | Data leaves VPC, API key management |
| **Decision** | Bedrock — aligns with enterprise AWS posture |

### 8.4 Istio mTLS vs NetworkPolicy only

| | Istio + NetworkPolicy | NetworkPolicy only |
|---|---|---|
| **Pros** | Encrypted east-west, identity-aware routing | Simpler, fewer moving parts |
| **Cons** | Operational complexity, sidecar overhead | No encryption between pods |
| **Decision** | Istio recommended for production; NetworkPolicy is minimum viable |

### 8.5 IRSA vs static credentials

| | IRSA | Static keys |
|---|---|---|
| **Pros** | Short-lived, auditable, rotatable | Simple to configure |
| **Cons** | Requires OIDC setup | Long-lived, high blast radius if leaked |
| **Decision** | IRSA — non-negotiable for production |

---

## 9. Implementation Roadmap

| Phase | Deliverable | Status in repo |
|---|---|---|
| **Phase 1 — Core agent** | LangGraph state machine, tool allowlist, input validation | Done |
| **Phase 2 — MCP tools** | Weather MCP server, Cursor dev integration | Done |
| **Phase 3 — K8s hardening** | Deployment, NetworkPolicy, IRSA, HPA, ingress | Done |
| **Phase 4 — Security tests** | Prompt injection, hop limit, schema validation tests | Done (17 tests) |
| **Phase 5 — Auth** | JWT validation at API/ingress layer | Planned |
| **Phase 6 — Guardrails** | Bedrock Guardrails for content filtering | Planned |
| **Phase 7 — Additional tools** | ServiceNow MCP, RAG/search MCP | Stub |
| **Phase 8 — Observability** | OpenTelemetry traces, Falco, GuardDuty | Planned |

---

## 10. Production Readiness Checklist

Before promoting to production, verify:

- [ ] JWT/OAuth authentication enforced on `/v1/query`
- [ ] Bedrock Guardrails enabled for the agent model
- [ ] All secrets in Secrets Manager — none in env vars or ConfigMaps
- [ ] Container images pinned by digest and Cosign-verified
- [ ] Trivy scan passes with no critical CVEs
- [ ] NetworkPolicy applied and tested (agent cannot reach unauthorized pods)
- [ ] WAF rules active (rate limiting, geo block if applicable)
- [ ] IRSA role scoped to minimum required permissions
- [ ] ALB access logs and CloudTrail enabled
- [ ] HPA and PDB configured for expected load
- [ ] Security tests pass in CI on every PR
- [ ] Incident response runbook documented for agent abuse scenarios

Full deployment steps: [DEPLOYMENT.md](DEPLOYMENT.md)

---

## 11. Mapping to Reference Repository

This proposal maps directly to code and manifests in the repository:

| Proposal section | Repository path |
|---|---|
| Input validation | `agent/graph.py` |
| Tool allowlist | `agent/tools.py` |
| MCP weather server | `mcp_server/weather_server.py` |
| REST API | `main.py` |
| Security tests | `tests/test_security.py` |
| K8s deployment | `k8s/deployment.yaml` |
| Network policy | `k8s/networkpolicy.yaml` |
| Ingress + WAF | `k8s/ingress.yaml` |
| IRSA policy | `iam/irsa-policy.json` |
| Helm prod values | `helm/values-prod.yaml` |
| Cursor dev config | `.cursor/mcp.json`, `.cursorignore` |
| Container build | `Dockerfile` |

---

## 12. Appendix — Sample API Interaction

**Request:**

```bash
curl -X POST https://agent.company.com/v1/query \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather in Singapore?"}'
```

**Response:**

```json
{
  "result": "Current weather in Singapore: 32°C, partly cloudy.",
  "trace_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "duration_ms": 1243.7
}
```

**Rejected request (prompt injection):**

```json
HTTP 400 Bad Request
{"detail": "Invalid input"}
```

Internal rejection reason is logged server-side but never returned to the client.

---

## Document History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-06-05 | Principal Security Architect | Initial proposal aligned with reference implementation |

---

*This document is the markdown equivalent of `AI_Platform_Security_Architecture_Proposal.docx`. Place the original Word file in [docs/source/](source/) for formal distribution.*
