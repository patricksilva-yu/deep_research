import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_ai.exceptions import ModelHTTPError
from api.orchestrator.router import router as orchestrator_router
from api.code_executor.router import router as code_executor_router
from api.summarizer.router import router as summarizer_router
from api.verification.router import router as verification_router
from api.files.router import router as files_router
from auth.router import router as auth_router
from auth.conversation_router import router as conversation_router
from auth.database import init_db, close_db
from auth.sessions import init_sessions, close_sessions
from auth.redis_client import init_redis, close_redis
from auth.csrf import verify_csrf_token
import logfire
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

logfire.configure()
logfire.instrument_pydantic_ai()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Initializes database, Redis client, and session manager on startup.
    Closes resources on shutdown.
    """
    # Startup
    logger.info("Application starting up")
    await init_db()
    await init_redis()  # Initialize Redis client before sessions (sessions will use it)
    await init_sessions()
    yield
    # Shutdown
    logger.info("Application shutting down")
    await close_db()
    await close_sessions()
    await close_redis()


app = FastAPI(
    title="Deep Research API",
    description="Multi-agent deep research system with web search, orchestration, code execution, and verification",
    version="0.1.0",
    lifespan=lifespan
)

# CORS configuration - allow Flask frontend to access the API
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
allowed_origins = [
    frontend_url,
    frontend_url.replace("localhost", "127.0.0.1"),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,  # Required for cookies (session_id, csrf_token)
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    expose_headers=["Set-Cookie"],
)

# Exempt paths from CSRF protection
CSRF_EXEMPT_PATHS = {"/auth/login", "/auth/register", "/health", "/api/webhooks"}

# CSRF protection middleware
@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """
    Verify CSRF token for state-changing requests (POST, PUT, PATCH, DELETE).
    Only enforces when session_id cookie is present (cookie-authenticated requests).
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        session_id = request.cookies.get("session_id")

        # Only enforce CSRF if request has a session cookie
        if session_id and request.url.path not in CSRF_EXEMPT_PATHS:
            cookie_token = request.cookies.get("csrf_token")
            header_token = request.headers.get("X-CSRF-Token")

            if not header_token or not cookie_token:
                return JSONResponse(status_code=403, content={"detail": "CSRF token missing"})

            csrf_secret = os.getenv("CSRF_SECRET")
            if not verify_csrf_token(header_token, session_id, csrf_secret):
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})

    return await call_next(request)



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
app.include_router(auth_router)
app.include_router(conversation_router)
app.include_router(files_router)
app.include_router(orchestrator_router)
app.include_router(code_executor_router)
app.include_router(summarizer_router)
app.include_router(verification_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
