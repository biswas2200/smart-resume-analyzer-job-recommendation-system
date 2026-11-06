import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.logging_setup import configure_logging, request_id_from, request_id_var
from app.models.schemas import HealthResponse
from app.routers.analyze import router as analyze_router
from app.routers.jobs import router as jobs_router
from app.routers.llm_usage import router as llm_usage_router
from app.routers.upload import router as upload_router
from app.services.fingerprint import engine_fingerprint
from app.services.llm_client import LLMUnavailableError
from app.services.local_ner_parser import ensure_local_model

_settings = get_settings()
configure_logging(_settings.log_level, _settings.log_file)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Before serving: fetch the NER model from the bucket if it is missing
    (NER_MODEL_GCS_URI). A failed download stops the service, so it never
    starts without its model."""
    ensure_local_model(_settings)
    yield


app = FastAPI(
    title="Smart Resume Analyser and Job Recommendation System — ML Service",
    description=(
        "Resume parsing, skill normalization, embedding-based role matching, "
        "ATS scoring, gap analysis, and explanation generation."
    ),
    lifespan=lifespan,
)

@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Tags everything logged while serving a request with its id (the
    backend's X-Request-Id, or a new one), echoes the id back, and writes one
    access line: method, path, status, duration. Never the query string or
    body."""
    request_id = request_id_from(request.headers.get("x-request-id"))
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("%s %s failed after %.0fms", request.method, request.url.path, _ms_since(start))
        raise
    else:
        level = logging.INFO
        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        log.log(level, "%s %s -> %d in %.0fms", request.method, request.url.path, response.status_code, _ms_since(start))
        response.headers["X-Request-Id"] = request_id
        return response
    finally:
        request_id_var.reset(token)


def _ms_since(start: float) -> float:
    return (time.perf_counter() - start) * 1000


app.include_router(analyze_router)
app.include_router(jobs_router)
app.include_router(upload_router)
app.include_router(llm_usage_router)


@app.exception_handler(LLMUnavailableError)
def llm_unavailable(_: Request, exc: LLMUnavailableError) -> JSONResponse:
    """Only the AI extraction path can surface this (the explainer
    falls back to the template on its own): a 503 with the reason, so the
    backend can tell the user "try again later" rather than a generic 502.
    """
    log.warning("AI engine unavailable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health")
def health() -> HealthResponse:
    """Liveness probe that also reports engine_fingerprint (FR-11.2) -- the
    value a Community user compares against a web deployment's to prove
    they're running the same core engine.
    """
    return HealthResponse(status="ok", engine_fingerprint=engine_fingerprint())
