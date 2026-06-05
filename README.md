# Agentic AI Platform — AWS EKS
### LangGraph + Model Context Protocol (MCP) + Kubernetes

> Demonstrates production-grade agentic AI deployment with security-first design on AWS EKS.

---

## What This Is

A secure, production-ready AI agent platform that:
- Orchestrates multi-step workflows using **LangGraph** state machines
- Exposes backend tools via **MCP (Model Context Protocol)** servers — think API gateway for AI
- Serves requests via a **FastAPI** REST endpoint
- Runs on **AWS EKS** with full Kubernetes security hardening
- Uses **Amazon Bedrock** (Claude Sonnet) for LLM inference — never leaves AWS network

---

## Architecture

```
Internet → Route53 → WAF → ALB → EKS Cluster
                                    ├── FastAPI Pod (input validation, JWT auth)
                                    ├── LangGraph Agent Pod (state machine orchestrator)
                                    │     └── calls MCP servers via MCP protocol
                                    ├── MCP Server Pod: Weather (port 9001)
                                    ├── MCP Server Pod: ServiceNow (port 9002)
                                    └── MCP Server Pod: Search/RAG (port 9003)
                                         └── → AWS Bedrock (via VPC endpoint)
                                         └── → Secrets Manager (via IRSA, no static creds)
```

---

## Project Structure

```
langgraph-mcp-eks/
├── agent/
│   ├── graph.py          # LangGraph state machine
│   └── tools.py          # Tool definitions (allowlist)
├── mcp_server/
│   └── weather_server.py # MCP server implementation
├── main.py               # FastAPI entrypoint
├── requirements.txt      # Pinned Python dependencies
├── Dockerfile            # Hardened multi-stage build
├── k8s/
│   ├── deployment.yaml   # Pod security hardening
│   ├── service.yaml      # Internal ClusterIP service
│   ├── ingress.yaml      # ALB ingress with WAF
│   ├── networkpolicy.yaml# Default-deny + explicit allow
│   ├── serviceaccount.yaml # IRSA annotation
│   └── hpa.yaml          # Horizontal Pod Autoscaler
├── iam/
│   └── irsa-policy.json  # Least-privilege IAM policy
├── helm/
│   ├── Chart.yaml
│   └── values-prod.yaml  # Production security overrides
├── .cursor/
│   └── mcp.json          # Cursor MCP server config (dev)
├── .cursorignore         # Block secrets from AI context
└── tests/
    └── test_security.py  # Security-focused unit tests
```

---

## Security Highlights

| Control | Implementation |
|---|---|
| Zero static credentials | IRSA — pods assume IAM roles via OIDC |
| Prompt injection defense | 6-layer: regex → schema → allowlist → hop limit → Guardrails → output validation |
| Container hardening | Non-root UID 1001, readOnlyRootFilesystem, drop ALL capabilities, seccomp |
| Network isolation | NetworkPolicy default-deny, Istio mTLS east-west |
| Secret management | AWS Secrets Manager + KMS, auto-rotate 30 days |
| Supply chain | Cosign image signing, Trivy scan, pinned deps with hashes |
| Runtime threat detection | Falco syscall monitoring, GuardDuty EKS protection |
| Audit trail | CloudTrail + structured JSON logs + OpenTelemetry traces |

---

## Prerequisites

```bash
# AWS
aws configure  # or use IRSA in CI/CD
eksctl         # EKS cluster management
kubectl        # Kubernetes CLI
helm           # Package manager

# Python
python 3.12+
pip install -r requirements.txt

# Container
docker
cosign         # Image signing
```

---

## Local Development

```bash
# 1. Clone and install
git clone https://github.com/your-org/langgraph-mcp-eks
cd langgraph-mcp-eks
pip install -r requirements.txt

# 2. Set environment (local only — prod uses Secrets Manager)
cp .env.example .env
export AWS_REGION=ap-southeast-1
export OPENWEATHER_API_KEY=your_key_here  # local dev only

# 3. Start MCP server
python mcp_server/weather_server.py &

# 4. Start API
uvicorn main:app --reload --port 8080

# 5. Test
curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather in Singapore?"}'
```

### Cursor IDE Development

This project includes Cursor configuration for local MCP tool development:

1. **Install dependencies** — `pip install -r requirements.txt`
2. **Configure secrets** — copy `.env.example` to `.env` and set `OPENWEATHER_API_KEY`
3. **MCP server** — `.cursor/mcp.json` registers the weather MCP server via stdio transport
4. **Restart Cursor** — after changing `.cursor/mcp.json`, reload the window or restart Cursor
5. **Verify** — open **Settings → Features → Model Context Protocol** and confirm `weather-server` is connected

The weather MCP server is available in Cursor chat as a tool. Cursor spawns it on demand using:

```json
{
  "command": "python3",
  "args": ["${workspaceFolder}/mcp_server/weather_server.py"],
  "envFile": "${workspaceFolder}/.env"
}
```

Sensitive files are excluded from AI context via `.cursorignore` (`.env`, IAM policies, production Helm values).

---

## EKS Deployment

```bash
# 1. Create EKS cluster
eksctl create cluster \
  --name ai-platform \
  --region ap-southeast-1 \
  --nodegroup-name standard \
  --node-type m5.large \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 6 \
  --with-oidc \
  --managed

# 2. Build and push image (signed)
aws ecr get-login-password --region ap-southeast-1 | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

docker build -t $ECR_REGISTRY/langgraph-agent:latest .
docker push $ECR_REGISTRY/langgraph-agent:latest

# Sign with Cosign
cosign sign $ECR_REGISTRY/langgraph-agent@$(docker inspect --format='{{index .RepoDigests 0}}' $ECR_REGISTRY/langgraph-agent:latest)

# 3. Create IRSA role
eksctl create iamserviceaccount \
  --name langgraph-agent-sa \
  --namespace ai-workloads \
  --cluster ai-platform \
  --attach-policy-arn arn:aws:iam::$ACCOUNT_ID:policy/langgraph-agent-policy \
  --approve

# 4. Deploy via Helm
helm upgrade --install langgraph-agent ./helm \
  --namespace ai-workloads \
  --create-namespace \
  -f helm/values-prod.yaml \
  --set image.tag=$(git rev-parse HEAD)

# 5. Verify
kubectl get pods -n ai-workloads
kubectl logs -l app=langgraph-agent -n ai-workloads --tail=50
```

---

## Sample Request & Response

```bash
curl -X POST https://agent.company.com/v1/query \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather in Singapore and log a ServiceNow incident if temp > 35C"}'
```

```json
{
  "result": "Current weather in Singapore: 32°C, partly cloudy. Temperature is below the 35°C threshold — no ServiceNow incident created.",
  "trace_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "duration_ms": 1243.7,
  "tools_used": ["get_weather"]
}
```

---

## Sample Logs (Structured JSON)

```json
{"event": "input_validated", "len": 89, "trace_id": "f47ac10b", "timestamp": "2026-06-05T10:23:01Z"}
{"event": "planner_response", "tool_calls": 1, "trace_id": "f47ac10b", "timestamp": "2026-06-05T10:23:02Z"}
{"event": "tool_call", "tool": "get_weather", "input": {"city": "Singapore"}, "trace_id": "f47ac10b"}
{"event": "tool_result", "tool": "get_weather", "duration_ms": 312, "trace_id": "f47ac10b"}
{"event": "query_success", "tools_used": ["get_weather"], "duration_ms": 1243, "trace_id": "f47ac10b"}
```

---

## Trade-offs

See `ARCHITECTURE.md` and the full security proposal document for detailed trade-off analysis covering:
- LangGraph vs direct LLM calls
- MCP pods vs in-process tools
- Bedrock vs OpenAI
- Istio vs NetworkPolicy-only
- IRSA vs static credentials

---

*Prepared by: Principal Security Architect | Classification: Internal*
