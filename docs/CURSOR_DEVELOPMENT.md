# Cursor Development Guide

This project is designed to be developed in **[Cursor](https://cursor.com)** — an AI-native code editor. Cursor gives you codebase-aware AI assistance and can connect directly to the MCP tools this app exposes, so you build and test tools in the same environment you write code.

---

## What Cursor Does in This Project

Cursor serves two roles here:

| Role | How |
|---|---|
| **AI pair programmer** | Understands the full repo — agent graph, tools, K8s manifests — to help you write and refactor code |
| **MCP client** | Connects to the local weather MCP server so you can invoke `get_weather` from chat while developing |

This means you can ask Cursor to *"add a new MCP tool for currency conversion"* and then immediately test it via MCP without deploying to Kubernetes.

---

## Prerequisites

- [Cursor](https://cursor.com/download) installed
- Python 3.12+
- An [OpenWeatherMap API key](https://openweathermap.org/api) (free tier works)

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/hnaung/langgraph-mcp-eks.git
cd langgraph-mcp-eks
pip install -r requirements.txt
```

### 2. Configure local secrets

```bash
cp .env.example .env
```

Edit `.env`:

```env
AWS_REGION=ap-southeast-1
OPENWEATHER_API_KEY=your_actual_api_key_here
```

> `.env` is listed in `.cursorignore` — Cursor's AI will not read your API key from this file.

### 3. Open in Cursor

Open the project folder in Cursor:

```bash
cursor .
```

Or use **File → Open Folder** and select the repo root.

### 4. Verify MCP server connection

1. Restart Cursor or run **Developer: Reload Window** (Cmd/Ctrl + Shift + P)
2. Go to **Settings → Features → Model Context Protocol**
3. Confirm `weather-server` shows as **connected** (green)

If it fails, open **Output → MCP Logs** for error details. Common fixes:

- `python3` not on PATH → set full path in `.cursor/mcp.json`
- Missing dependency → run `pip install -r requirements.txt`
- Invalid API key → check `.env`

---

## How MCP Is Configured

The file `.cursor/mcp.json` tells Cursor how to start the weather MCP server:

```json
{
  "mcpServers": {
    "weather-server": {
      "type": "stdio",
      "command": "python3",
      "args": ["${workspaceFolder}/mcp_server/weather_server.py"],
      "env": {
        "AWS_REGION": "${env:AWS_REGION}",
        "OPENWEATHER_API_KEY": "${env:OPENWEATHER_API_KEY}"
      },
      "envFile": "${workspaceFolder}/.env"
    }
  }
}
```

| Field | Purpose |
|---|---|
| `type: stdio` | Cursor spawns the server as a subprocess and communicates over stdin/stdout |
| `command` / `args` | Runs the weather MCP server script |
| `envFile` | Loads secrets from `.env` without hardcoding them in the config |
| `${workspaceFolder}` | Resolves to the repo root — works on any machine |

Cursor starts the server **on demand** when a tool is needed, and stops it when the session ends.

---

## Using MCP Tools in Cursor Chat

Once connected, ask Cursor to use the weather tool directly:

```
What is the current weather in Tokyo? Use the weather MCP tool.
```

```
Test the get_weather tool with city="London" and units="metric".
```

Cursor will call the MCP tool, show you the arguments and response, and ask for approval before running (unless you've allowlisted the tool).

### Tool approval

By default Cursor asks before each MCP tool call. You can:

- Click **Allow** for a single call
- Allowlist the tool in Cursor settings for repeated use during development

---

## Typical Development Workflows

### Workflow 1 — Test an existing MCP tool

1. Open Cursor chat
2. Ask: *"Call get_weather for Singapore"*
3. Verify the response matches OpenWeatherMap data
4. Check MCP Logs if the call fails

### Workflow 2 — Build a new MCP tool with AI assistance

1. Ask Cursor: *"Create a new MCP server in mcp_server/ that converts USD to EUR using a free API"*
2. Review the generated code for input validation and secret handling
3. Register the new server in `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "weather-server": { "...": "..." },
    "currency-server": {
      "type": "stdio",
      "command": "python3",
      "args": ["${workspaceFolder}/mcp_server/currency_server.py"],
      "envFile": "${workspaceFolder}/.env"
    }
  }
}
```

4. Reload Cursor and test the new tool in chat
5. Add the tool to `agent/tools.py` allowlist when ready for the LangGraph agent

### Workflow 3 — Run security tests after changes

```bash
pytest tests/ -v
```

Or ask Cursor: *"Run the security tests and fix any failures in agent/graph.py"*

### Workflow 4 — Develop the LangGraph agent

Cursor understands `agent/graph.py` and can help you:

- Add new validation patterns
- Modify the planner logic
- Debug the should_continue router

For full agent testing (with Bedrock), configure AWS credentials:

```bash
aws configure
# Ensure Bedrock access in ap-southeast-1
```

Then run the API:

```bash
uvicorn main:app --reload --port 8080
```

---

## Protecting Secrets from AI Context

The file `.cursorignore` prevents Cursor from indexing or sending these to the AI:

```
**/.env
**/.env.*
iam/
helm/values-prod.yaml
**/*.pem
**/*.key
```

**Important:** `.cursorignore` is a best-effort safeguard. Never commit real API keys. Use `.env` locally and AWS Secrets Manager in production.

---

## Project Files for Cursor Development

| File | Purpose |
|---|---|
| `.cursor/mcp.json` | MCP server registration — commit this, share with team |
| `.cursorignore` | Files excluded from AI context — commit this |
| `.env.example` | Template for local secrets — commit this |
| `.env` | Your actual secrets — **never commit** (in `.gitignore`) |
| `mcp_server/weather_server.py` | MCP server with stdio entrypoint (`if __name__ == "__main__"`) |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| MCP server not listed | Reload Cursor window after editing `mcp.json` |
| Server crashes on start | Check MCP Logs; run `python3 mcp_server/weather_server.py` manually |
| `ModuleNotFoundError: mcp` | Run `pip install -r requirements.txt` (needs `mcp>=1.12.4`) |
| Weather tool returns 401 | Invalid `OPENWEATHER_API_KEY` in `.env` |
| Cursor can't find python3 | Use full path: `"command": "/usr/bin/python3"` in `mcp.json` |

---

## Why Develop with Cursor + MCP?

Traditional development: write tool code → deploy to K8s → test via API → debug logs.

With Cursor + MCP: write tool code → test immediately in chat → iterate → deploy when ready.

This repo bridges **local Cursor development** and **production EKS deployment** using the same MCP protocol and tool implementations. The weather server you test in Cursor is the same code that runs as a pod in the cluster.

---

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand how MCP tools connect to the LangGraph agent in production
- Read [DEPLOYMENT.md](DEPLOYMENT.md) when you're ready to deploy to EKS
- Add your own MCP tools and register them in `.cursor/mcp.json`
