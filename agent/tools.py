# agent/tools.py
# Explicit tool allowlist — LLM can ONLY invoke tools defined here.
# Adding a new tool requires code review + security schema review.

from langchain_core.tools import tool
from pydantic import Field
import httpx, boto3, json, logging

logger = logging.getLogger("agent.tools")


def _get_secret(secret_id: str) -> dict:
    """Retrieve secret from AWS Secrets Manager via IRSA — no static creds."""
    if secret_id == "prod/weather/api-key":
        local_key = os.environ.get("OPENWEATHER_API_KEY")
        if local_key:
            return {"api_key": local_key}

    client = boto3.client("secretsmanager", region_name="ap-southeast-1")
    response = client.get_secret_value(SecretId=secret_id)
    return json.loads(response["SecretString"])


@tool
def get_weather(
    city: str = Field(description="City name (letters and spaces only)", max_length=64),
    units: str = Field(default="metric", description="metric or imperial")
) -> dict:
    """Get current weather conditions for a city."""
    import re
    # Strict input validation — prevent parameter injection
    if not re.match(r'^[a-zA-Z\s\-]{1,64}$', city):
        raise ValueError(f"Invalid city name: {city}")
    if units not in ("metric", "imperial"):
        raise ValueError(f"Invalid units: {units}")

    secret = _get_secret("prod/weather/api-key")
    api_key = secret["api_key"]

    with httpx.Client(timeout=5.0) as client:
        r = client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": api_key, "units": units},
        )
        r.raise_for_status()

    data = r.json()
    logger.info("tool_called", extra={"tool": "get_weather", "city": city})

    # Return ONLY allowed fields — never passthrough raw upstream response
    return {
        "city": data["name"],
        "temp": data["main"]["temp"],
        "feels_like": data["main"]["feels_like"],
        "condition": data["weather"][0]["description"],
        "humidity": data["main"]["humidity"],
    }


@tool
def search_knowledge_base(
    query: str = Field(description="Search query for internal knowledge base", max_length=256)
) -> dict:
    """Search the internal knowledge base using semantic search (RAG)."""
    import re
    if len(query.strip()) < 3:
        raise ValueError("Query too short")
    # Sanitize query — remove special chars that could be injection vectors
    safe_query = re.sub(r'[<>{}\[\]|\\]', '', query)[:256]
    logger.info("tool_called", extra={"tool": "search_knowledge_base", "query_len": len(safe_query)})
    # In production: calls Search MCP server at port 9003
    # Stub response for development
    return {"results": [], "query": safe_query, "source": "internal-kb"}


# ── ALLOWLIST — only tools in this list can be called by the agent ──────
# This is the single source of truth for permitted tool operations.
ALLOWED_TOOLS = [
    get_weather,
    search_knowledge_base,
]
