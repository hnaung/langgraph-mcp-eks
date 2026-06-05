# Architecture

This document explains how the LangGraph MCP EKS platform is designed, how a request flows through the system, and the security decisions behind each layer.

> **Audience note:** For the full stakeholder-facing security proposal (executive summary, threat model, STRIDE analysis, production checklist), see [AI_PLATFORM_SECURITY_ARCHITECTURE_PROPOSAL.md](AI_PLATFORM_SECURITY_ARCHITECTURE_PROPOSAL.md).

---

## System Overview

The platform is a **secure AI agent API** deployed on AWS EKS. Clients send natural-language queries; an LLM-powered agent decides whether to call tools and returns a final answer.

```
┌─────────────┐     HTTPS      ┌──────────────────────────────────────────────┐
│   Client    │ ─────────────► │              AWS EKS Cluster                 │
│ (web, CLI)  │                │                                              │
└─────────────┘                │  ┌─────────────┐    ┌─────────────────────┐  │
                               │  │   FastAPI   │───►│  LangGraph Agent    │  │
                               │  │  (main.py)  │    │  (agent/graph.py)   │  │
                               │  └─────────────┘    └──────────┬──────────┘  │
                               │                                │             │
                               │                    ┌───────────▼──────────┐  │
                               │                    │   Tool Allowlist       │  │
                               │                    │   (agent/tools.py)     │  │
                               │                    └───────────┬──────────┘  │
                               │              ┌─────────────────┼─────────┐   │
                               │              ▼                 ▼         ▼   │
                               │     ┌──────────────┐  ┌──────────┐  ┌──────┐ │
                               │     │ MCP Weather  │  │ Service  │  │ RAG  │ │
                               │     │   (9001)     │  │ Now stub │  │ stub │ │
                               │     └──────┬───────┘  └──────────┘  └──────┘ │
                               └────────────┼─────────────────────────────────┘
                                            │
                               ┌────────────▼────────────┐
                               │   Amazon Bedrock        │
                               │   (Claude Sonnet)       │
                               └─────────────────────────┘
```

**Edge traffic path (production):** Internet → Route53 → WAF → ALB → EKS Ingress → FastAPI pod

---

## Request Lifecycle

Every query follows the same state machine defined in `agent/graph.py`:

```
                    ┌──────────────┐
                    │   START      │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ validate_input│  Block injection, enforce max length,
                    │              │  compute risk score for secret keywords
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   planner    │  Call Bedrock with allowlisted tools
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
              ┌─────┤ should_continue├─────┐
              │     └──────────────┘     │
              │ tool calls?              │ no tool calls
              │ yes (under hop limit)    │
     ┌────────▼────────┐          ┌──────▼──────┐
     │     tools       │          │     END     │
     │  (ToolNode)     │          └─────────────┘
     └────────┬────────┘
              │ loop back to planner (max 5 hops)
              └──────────────────────────────► planner
```

### Step-by-step

1. **HTTP ingress** — `POST /v1/query` with `{ "query": "..." }` hits FastAPI (`main.py`)
2. **Input validation** — `validate_input` rejects known injection patterns and inputs over 4096 characters
3. **Planning** — Bedrock receives the conversation and may return tool calls
4. **Tool execution** — Only tools in `ALLOWED_TOOLS` run; each tool validates its own parameters
5. **Loop or finish** — Agent loops planner → tools up to `MAX_TOOL_HOPS` (5), then returns the final message
6. **Response** — FastAPI returns `{ result, trace_id, duration_ms }`

---

## Component Responsibilities

### FastAPI (`main.py`)

- Public HTTP interface
- TrustedHost middleware (production host allowlist)
- Structured logging via structlog
- Maps validation errors to HTTP 400 without leaking internals

### LangGraph agent (`agent/graph.py`)

- Typed state: messages, tool call history, validated input, risk score
- Orchestrates the validate → plan → tool loop
- Enforces maximum tool hops to prevent runaway agents

### Tool allowlist (`agent/tools.py`)

- **Single source of truth** for what the LLM can invoke
- Each tool has Pydantic-validated parameters and output filtering
- Production secrets come from AWS Secrets Manager via IRSA
- Local dev uses `OPENWEATHER_API_KEY` from `.env`

| Tool | Status | Description |
|---|---|---|
| `get_weather` | Implemented | Fetches weather from OpenWeatherMap |
| `search_knowledge_base` | Stub | Placeholder for RAG / vector search MCP server |

### MCP server (`mcp_server/weather_server.py`)

- Implements the same weather capability via the **Model Context Protocol**
- Runs as a **stdio process** locally (Cursor) or as a **Kubernetes pod** in production
- Decouples tool implementation from the agent — teams can own and deploy tools independently

---

## Local vs Production

| Concern | Local development | Production (EKS) |
|---|---|---|
| LLM | Amazon Bedrock (requires AWS creds) | Bedrock via VPC endpoint |
| Weather API key | `OPENWEATHER_API_KEY` in `.env` | AWS Secrets Manager |
| MCP server | Cursor spawns via `.cursor/mcp.json` | Dedicated pod, ClusterIP only |
| Tool invocation | In-process via LangGraph `ToolNode` | Agent pod → MCP pod over cluster network |
| Secrets in AI context | Blocked by `.cursorignore` | N/A |

---

## Security Layers

Defense is layered — no single check is relied on alone.

| Layer | Where | What it does |
|---|---|---|
| 1. Input regex | `agent/graph.py` | Blocks prompt injection patterns |
| 2. Input length | `agent/graph.py` | Rejects inputs over 4096 chars |
| 3. Tool schema | `agent/tools.py`, MCP server | Pydantic validates city names, units, query length |
| 4. Tool allowlist | `agent/tools.py` | LLM can only call predefined tools |
| 5. Hop limit | `agent/graph.py` | Max 5 tool calls per request |
| 6. Output filtering | Tool implementations | Return only allowed fields, never raw upstream API responses |

### Kubernetes hardening (`k8s/`)

- **Non-root** container (UID 1001)
- **Read-only root filesystem**
- **Dropped capabilities** (ALL)
- **seccomp** RuntimeDefault profile
- **NetworkPolicy** default-deny with explicit allow rules
- **IRSA** — pods get IAM roles via service account annotation, no static keys
- **HPA** — horizontal scaling under load

---

## Design Trade-offs

For the full trade-off analysis with decision rationale, see the [Security Architecture Proposal — Section 8](AI_PLATFORM_SECURITY_ARCHITECTURE_PROPOSAL.md#8-design-trade-offs).

### LangGraph vs direct LLM calls

LangGraph adds a state machine with explicit nodes and edges. This makes the agent flow auditable, testable (each node can be unit tested), and safe (hop limits, validation gates). The cost is more boilerplate than a single `llm.invoke()` call.

### MCP pods vs in-process tools

In-process tools (`agent/tools.py`) are simpler for local dev. MCP servers add a network hop but enable:

- Independent deployment and scaling per tool
- Team ownership boundaries (weather team owns port 9001)
- Standard protocol reusable by Cursor, Claude Desktop, and other MCP clients

This repo implements **both**: in-process tools for the LangGraph agent, and a standalone MCP server for the same weather capability.

### Bedrock vs OpenAI

Bedrock keeps inference inside AWS, supports VPC endpoints, and integrates with IAM. Requires AWS account setup. OpenAI would simplify local dev but moves data outside your VPC.

### IRSA vs static credentials

IRSA (IAM Roles for Service Accounts) eliminates long-lived keys in pods. Pods assume short-lived credentials via OIDC. Local dev uses environment variables instead.

---

## Observability

Production deployments emit structured JSON logs:

```json
{"event": "input_validated", "len": 89, "trace_id": "f47ac10b"}
{"event": "planner_response", "tool_calls": 1, "trace_id": "f47ac10b"}
{"event": "tool_call", "tool": "get_weather", "input": {"city": "Singapore"}}
{"event": "query_success", "tools_used": ["get_weather"], "duration_ms": 1243}
```

OpenTelemetry and Prometheus client libraries are included in `requirements.txt` for trace and metrics export in production setups.

---

## Extending the Platform

To add a new tool:

1. Implement the tool in `agent/tools.py` with input validation and output filtering
2. Add it to `ALLOWED_TOOLS`
3. (Optional) Create a new MCP server in `mcp_server/` and register it in `.cursor/mcp.json`
4. Add Kubernetes deployment manifest and NetworkPolicy allow rule
5. Write security tests in `tests/test_security.py`
6. Update IAM policy if the tool needs new AWS permissions

See [CURSOR_DEVELOPMENT.md](CURSOR_DEVELOPMENT.md) for the Cursor-specific workflow when building MCP tools.
