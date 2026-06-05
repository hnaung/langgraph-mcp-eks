# MCP Server implementing the Model Context Protocol spec
# Exposed only inside the cluster — never publicly routable
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
import httpx, boto3, json

mcp = FastMCP("weather-server")

# Retrieve API key from Secrets Manager — not from env/config file
def get_api_key() -> str:
    client = boto3.client("secretsmanager", region_name="ap-southeast-1")
    secret = client.get_secret_value(SecretId="prod/weather/api-key")
    return json.loads(secret["SecretString"])["api_key"]

# Tool with explicit schema — LLM cannot request arbitrary params
@mcp.tool()
async def get_weather(
    city: str = Field(description="City name", max_length=64, pattern=r"^[a-zA-Z\s\-]+$"),
    units: str = Field(default="metric", pattern=r"^(metric|imperial)$")
) -> dict:
    """Get current weather for a city."""
    key = get_api_key()
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": key, "units": units},
        )
        r.raise_for_status()
    # Return only needed fields — never passthrough raw API response
    data = r.json()
    return {
        "city": data["name"],
        "temp_c": data["main"]["temp"],
        "condition": data["weather"][0]["description"]
    }
