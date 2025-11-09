from fastapi import FastAPI
from api.orchestrator.router import router as orchestrator_router
from api.code_executor.router import router as code_executor_router
from api.summarizer.router import router as summarizer_router
from api.verification.router import router as verification_router
import logfire

logfire.configure()
logfire.instrument_pydantic_ai()

app = FastAPI(
    title="Deep Research API",
    description="Multi-agent deep research system with web search, orchestration, code execution, and verification",
    version="0.1.0"
)

# Include routers
app.include_router(orchestrator_router)
app.include_router(code_executor_router)
app.include_router(summarizer_router)
app.include_router(verification_router)


@app.get("/")
async def root():
    return {
        "message": "Deep Research API",
        "endpoints": {
            "orchestrator": "/orchestrator/plan",
            "code_executor": "/code_executor/execute",
            "summarizer": "/summarizer/report",
            "verification": "/verification/verify"
        }
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
