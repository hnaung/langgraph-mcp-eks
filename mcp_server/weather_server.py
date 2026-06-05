# MCP Server implementing the Model Context Protocol spec
# Exposed only inside the cluster — never publicly routable
import json
import os

import boto3
import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("weather-server")


def get_api_key() -> str:
    """Resolve API key from env (local dev) or Secrets Manager (production)."""
    local_key = os.environ.get("OPENWEATHER_API_KEY")
    if local_key:
        return local_key

    region = os.environ.get("AWS_REGION", "ap-southeast-1")
    client = boto3.client("secretsmanager", region_name=region)
    secret = client.get_secret_value(SecretId="prod/weather/api-key")
    return json.loads(secret["SecretString"])["api_key"]


@mcp.tool()
async def get_weather(
    city: str = Field(description="City name", max_length=64, pattern=r"^[a-zA-Z\s\-]+$"),
    units: str = Field(default="metric", pattern=r"^(metric|imperial)$"),
) -> dict:
    """Get current weather for a city."""
    key = get_api_key()
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": key, "units": units},
        )
        r.raise_for_status()
    data = r.json()
    return {
        "city": data["name"],
        "temp_c": data["main"]["temp"],
        "condition": data["weather"][0]["description"],
    }


if __name__ == "__main__":
    mcp.run()
