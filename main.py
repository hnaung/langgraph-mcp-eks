from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from agent.graph import app as agent_graph
from langchain_core.messages import HumanMessage
import structlog, time, uuid

log = structlog.get_logger()
api = FastAPI(title="LangGraph Agent API", docs_url=None)  # Docs disabled in prod

# Middleware: restrict to known hosts only
api.add_middleware(TrustedHostMiddleware, allowed_hosts=["agent.internal.company.com"])

class QueryRequest(BaseModel):
    query: str = Field(max_length=2048)
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

class QueryResponse(BaseModel):
    result: str
    trace_id: str
    duration_ms: float

@api.post("/v1/query", response_model=QueryResponse)
async def query_agent(req: QueryRequest):
    start = time.monotonic()
    try:
        result = await agent_graph.ainvoke({
            "messages": [HumanMessage(content=req.query)],
            "tool_calls_made": [],
            "validated_input": "",
            "risk_score": 0
        })
        answer = result["messages"][-1].content
        log.info("query_success", trace_id=req.trace_id, tools_used=result["tool_calls_made"])
        return QueryResponse(
            result=answer,
            trace_id=req.trace_id,
            duration_ms=(time.monotonic()-start)*1000
        )
    except ValueError as e:
        log.warning("query_rejected", reason=str(e), trace_id=req.trace_id)
        raise HTTPException(400, detail="Invalid input")  # Never leak internal error

@api.get("/health")
async def health(): return {"status": "ok"}
