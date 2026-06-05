# agent/graph.py — LangGraph state machine with MCP tool integration
import logging
import operator
import re
from typing import Annotated, List, TypedDict

from langchain_aws import ChatBedrock
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agent.tools import ALLOWED_TOOLS

logger = logging.getLogger("agent")

MAX_TOOL_HOPS = 5

INJECTION_PATTERNS = [
    r"ignore.{0,20}(previous|above|instructions)",
    r"disregard.{0,20}(system|your).{0,20}prompt",
    r"you are now",
    r"forget everything",
    r"<script[\s>]|</script>",
]

SECRET_KEYWORDS = ("api_key", "secret", "password", "token", "credential")


class AgentState(TypedDict):
    messages: Annotated[List, operator.add]
    tool_calls_made: List[str]
    validated_input: str
    risk_score: int


def _injection_risk_score(text: str) -> int:
    lowered = text.lower()
    return sum(2 for keyword in SECRET_KEYWORDS if keyword in lowered)


def validate_input(state: AgentState) -> AgentState:
    user_msg = state["messages"][-1].content
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, user_msg, re.I):
            raise ValueError("prompt injection detected")
    if len(user_msg) > 4096:
        raise ValueError("Input too long")
    logger.info("input_validated", extra={"len": len(user_msg)})
    return {
        "validated_input": user_msg,
        "risk_score": _injection_risk_score(user_msg),
    }


def planner(state: AgentState) -> AgentState:
    llm = ChatBedrock(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        region_name="ap-southeast-1",
    ).bind_tools(ALLOWED_TOOLS)
    response = llm.invoke(state["messages"])
    logger.info("planner_response", extra={"tool_calls": len(response.tool_calls)})
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", []):
        if len(state["tool_calls_made"]) >= MAX_TOOL_HOPS:
            return "end"
        return "tools"
    return "end"


graph = StateGraph(AgentState)
graph.add_node("validate", validate_input)
graph.add_node("planner", planner)
graph.add_node("tools", ToolNode(ALLOWED_TOOLS))
graph.set_entry_point("validate")
graph.add_edge("validate", "planner")
graph.add_conditional_edges("planner", should_continue, {"tools": "tools", "end": END})
graph.add_edge("tools", "planner")
app = graph.compile()
