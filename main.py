import logging
import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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

# Setup templates
templates = Jinja2Templates(directory="templates")

# Add context processor for templates
@app.middleware("http")
async def add_template_context(request: Request, call_next):
    request.state.current_year = datetime.date.today().year
    response = await call_next(request)
    return response

# CORS no longer needed - FastAPI serves both frontend and API on the same origin


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

# Include API routers
app.include_router(orchestrator_router)
app.include_router(code_executor_router)
app.include_router(summarizer_router)
app.include_router(verification_router)


# HTML Routes (formerly in Flask app.py)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "Hivemind – Deep Research Chatbot", "current_year": request.state.current_year}
    )


@app.get("/chat", response_class=HTMLResponse)
async def chat(request: Request):
    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "title": "Chat – Hivemind", "current_year": request.state.current_year}
    )


@app.get("/sign-in", response_class=HTMLResponse)
async def sign_in(request: Request):
    return templates.TemplateResponse(
        "signin.html",
        {"request": request, "title": "Sign in – Hivemind", "current_year": request.state.current_year}
    )


@app.get("/health")
async def health():
    return {"status": "healthy"}


# Mount static files LAST (after all routes)
app.mount("/static", StaticFiles(directory="static"), name="static")
