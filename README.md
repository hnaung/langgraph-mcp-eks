# LangGraph MCP EKS

A reference implementation of a **secure, production-style AI agent platform** on AWS EKS.

It shows how to build an agent that accepts natural-language requests, plans actions with an LLM, calls external tools safely, and runs in Kubernetes with security controls applied from day one.

**Stack:** LangGraph · Model Context Protocol (MCP) · FastAPI · Amazon Bedrock · AWS EKS

---

## Purpose

This repository is meant for teams who want to:

- **Learn** how to design agentic AI systems that are safe to run in production
- **Prototype** multi-step AI workflows (plan → tool call → respond) with real infrastructure patterns
- **Develop with Cursor** — use the IDE's MCP integration to build and test tools while coding

It is a **working demo and blueprint**, not a drop-in SaaS product. You can fork it, swap tools, plug in your own LLM endpoints, and extend the Kubernetes manifests for your environment.

---

## What It Does

A user sends a question to a REST API. The platform:

1. **Validates input** — blocks prompt injection, enforces length limits, scores risky content
2. **Plans with an LLM** — Claude on Amazon Bedrock decides whether tools are needed
3. **Calls allowed tools only** — weather lookup, knowledge-base search (stub), via an explicit allowlist
4. **Returns a structured answer** — with trace ID and timing metadata

### Example flow

```
User: "What is the weather in Singapore?"
  │
  ▼
FastAPI (main.py)          POST /v1/query
  │
  ▼
LangGraph agent (agent/graph.py)
  ├── validate_input   → reject injection / oversize input
  ├── planner          → Bedrock decides to call get_weather
  ├── tools            → fetch weather from OpenWeatherMap
  └── planner          → format final answer
  │
  ▼
Response: { "result": "32°C, partly cloudy in Singapore", "trace_id": "...", "duration_ms": 1243 }
```

### Components at a glance

| Component | Role |
|---|---|
| `main.py` | HTTP API — entry point for clients |
| `agent/graph.py` | LangGraph state machine — orchestrates validate → plan → tool → plan |
| `agent/tools.py` | Tool allowlist — only these functions can be invoked by the agent |
| `mcp_server/weather_server.py` | Standalone MCP server — same weather tool, exposed via MCP protocol |
| `k8s/` | Kubernetes manifests — hardened pods, network policy, ingress, HPA |
| `iam/` | Least-privilege IAM policy for IRSA (no static AWS keys in pods) |
| `.cursor/` | Cursor IDE config — connect MCP tools during local development |

---

## Why MCP and Why Cursor?

**MCP (Model Context Protocol)** is an open standard for connecting AI assistants to tools and data. In production, each tool can run as its own pod (weather, ServiceNow, search/RAG). In development, the same MCP server runs locally so you test the exact interface the agent will use.

**Cursor** is used here as the **development environment** for this app:

- Open the repo in Cursor and get full project context for AI-assisted coding
- `.cursor/mcp.json` registers the weather MCP server — test `get_weather` directly in chat
- `.cursorignore` keeps secrets and IAM policies out of AI context
- Build new tools in `mcp_server/` and validate them in Cursor before deploying to EKS

See **[docs/CURSOR_DEVELOPMENT.md](docs/CURSOR_DEVELOPMENT.md)** for the full Cursor workflow.

---

## Quick Start

### Option A — Develop with Cursor (recommended)

```bash
git clone https://github.com/hnaung/langgraph-mcp-eks.git
cd langgraph-mcp-eks
pip install -r requirements.txt
cp .env.example .env   # add your OPENWEATHER_API_KEY
```

Open the folder in **Cursor**, restart or reload the window, then verify `weather-server` under **Settings → Features → Model Context Protocol**.

Ask Cursor chat: *"Use the weather tool to get the current weather in Singapore."*

### Option B — Run the API locally

```bash
pip install -r requirements.txt
cp .env.example .env
export OPENWEATHER_API_KEY=your_key

python mcp_server/weather_server.py &   # optional: standalone MCP process
uvicorn main:app --reload --port 8080

curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather in Singapore?"}'
```

> **Note:** The agent planner calls Amazon Bedrock. For full end-to-end API tests you need AWS credentials configured (`aws configure`) with Bedrock access in `ap-southeast-1`. Security unit tests run without AWS.

### Run tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Documentation

| Document | Description |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, request lifecycle, security layers, deployment topology |
| [docs/CURSOR_DEVELOPMENT.md](docs/CURSOR_DEVELOPMENT.md) | How to use Cursor for MCP tool development on this project |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | EKS deployment steps and production checklist |

---

## Project Structure

```
langgraph-mcp-eks/
├── agent/
│   ├── graph.py              # LangGraph state machine (validate → plan → tools)
│   └── tools.py              # Tool allowlist + implementations
├── mcp_server/
│   └── weather_server.py     # MCP server (stdio) — used by Cursor and EKS
├── main.py                   # FastAPI REST API
├── tests/
│   └── test_security.py      # Prompt injection, hop limits, input validation
├── k8s/                      # Kubernetes manifests
├── iam/                      # IRSA policy
├── helm/                     # Helm chart values
├── .cursor/
│   └── mcp.json              # Cursor MCP server registration
├── .cursorignore             # Files excluded from Cursor AI context
├── .env.example              # Local dev environment template
├── Dockerfile                # Multi-stage hardened container build
└── requirements.txt          # Python dependencies
```

---

## Security Highlights

| Control | Implementation |
|---|---|
| No static AWS credentials | IRSA — pods assume IAM roles via OIDC |
| Prompt injection defense | Regex patterns, length limits, tool hop cap (5), schema validation |
| Tool access | Explicit allowlist in `agent/tools.py` — LLM cannot call arbitrary code |
| Container hardening | Non-root UID 1001, read-only root FS, dropped capabilities, seccomp |
| Network isolation | NetworkPolicy default-deny, Istio mTLS (production) |
| Secrets | AWS Secrets Manager in prod; `.env` for local dev only |
| AI context safety | `.cursorignore` blocks `.env`, IAM, prod Helm values from Cursor |

---

## Production Deployment

Deploy to AWS EKS with Helm:

```bash
helm upgrade --install langgraph-agent ./helm \
  --namespace ai-workloads \
  --create-namespace \
  -f helm/values-prod.yaml
```

Full steps (cluster creation, ECR, IRSA, Cosign signing): **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**

---

## License

Reference implementation — adapt for your organization's policies and compliance requirements.
