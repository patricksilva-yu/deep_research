import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_ai.exceptions import ModelHTTPError
from api.orchestrator.router import router as orchestrator_router
from api.code_executor.router import router as code_executor_router
from api.summarizer.router import router as summarizer_router
from api.verification.router import router as verification_router
import logfire

logger = logging.getLogger(__name__)

logfire.configure()
logfire.instrument_pydantic_ai()

app = FastAPI(
    title="Deep Research API",
    description="Multi-agent deep research system with web search, orchestration, code execution, and verification",
    version="0.1.0"
)

# Add CORS middleware to allow Flask frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5000", "http://127.0.0.1:5000"],  # Flask default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ModelHTTPError)
async def model_http_error_handler(_request: Request, exc: ModelHTTPError) -> JSONResponse:
    """
    Global handler for ModelHTTPError from Pydantic AI.

    This centralizes error handling for all model-related HTTP errors,
    preventing information leakage by safely extracting error messages.
    """
    # Safely extract the error message from the response body
    if exc.status_code == 429:
        default_message = 'Rate limit error'
    else:
        default_message = 'An error occurred with the AI model'

    error_message = exc.body.get('message', default_message) if isinstance(exc.body, dict) else default_message

    if exc.status_code == 429:
        detail = f"Rate limit exceeded. Try again shortly. Details: {error_message}"
        return JSONResponse(status_code=429, content={"detail": detail})

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": error_message}
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    """
    Global handler for uncaught exceptions.

    Logs full exception details server-side while returning
    a generic error message to the client to prevent information leakage.
    """
    # Log full exception details server-side for debugging
    logger.exception(f"Unexpected error in {request.url.path}")

    # Return generic error message to client (no sensitive info)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
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
