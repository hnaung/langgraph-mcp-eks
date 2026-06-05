# agent/graph.py — LangGraph state machine with MCP tool integration
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_aws import ChatBedrock
from pydantic import BaseModel, validator
from typing import TypedDict, Annotated, List
import operator, logging, re

logger = logging.getLogger("agent")

# ── State schema (typed, not dict) ──────────────────────────
class AgentState(TypedDict):
    messages: Annotated[List, operator.add]
    tool_calls_made: List[str]
    validated_input: str
    risk_score: int

# ── Input validation node ────────────────────────────────────
def validate_input(state: AgentState) -> AgentState:
    user_msg = state["messages"][-1].content
    # Block prompt injection patterns
    if re.search(r"ignore.{0,20}(previous|above|instructions)", user_msg, re.I):
        raise ValueError("Prompt injection detected")
    if len(user_msg) > 4096:
        raise ValueError("Input exceeds max token budget")
    logger.info("input_validated", extra={"len": len(user_msg)})
    return {"validated_input": user_msg, "risk_score": 0}

# ── LLM planner node ────────────────────────────────────────
def planner(state: AgentState) -> AgentState:
    llm = ChatBedrock(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        region_name="ap-southeast-1"
    ).bind_tools(ALLOWED_TOOLS)  # allowlist — not open-ended
    response = llm.invoke(state["messages"])
    logger.info("planner_response", extra={"tool_calls": len(response.tool_calls)})
    return {"messages": [response]}

# ── Router: continue to tools or END ────────────────────────
def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", []):
        # Enforce max tool hops — prevent runaway agents
        if len(state["tool_calls_made"]) >= 5:
            return "end"
        return "tools"
    return "end"

# ── Graph assembly ───────────────────────────────────────────
graph = StateGraph(AgentState)
graph.add_node("validate", validate_input)
graph.add_node("planner", planner)
graph.add_node("tools", ToolNode(ALLOWED_TOOLS))
graph.set_entry_point("validate")
graph.add_edge("validate", "planner")
graph.add_conditional_edges("planner", should_continue, {"tools": "tools", "end": END})
graph.add_edge("tools", "planner")
app = graph.compile()
