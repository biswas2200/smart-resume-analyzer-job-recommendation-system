"""LLM spend since the process started: GET /llm-usage reads the ledger
llm_client.py keeps of every provider call (token counts straight from the
responses, priced with the list prices in Settings), POST /llm-usage/reset
zeroes it. This is how an analysis's real cost is checked against the
assumptions in ml-service/README.md -- the per-request figures are on
AnalyzeResponse.llm_usage, this is the running total.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings
from app.models.schemas import LLMPricing, LLMUsageReport
from app.services.llm_client import ledger, usage_summary

router = APIRouter()


def _report() -> LLMUsageReport:
    settings = get_settings()
    model = settings.gemini_model if settings.llm_provider == "gemini" else settings.groq_model
    totals = usage_summary(ledger.recent())
    # The recent list is capped; the counters are not -- prefer them.
    totals.calls = ledger.calls
    totals.cache_hits = ledger.cache_hits
    totals.prompt_tokens = ledger.prompt_tokens
    totals.output_tokens = ledger.output_tokens
    totals.thinking_tokens = ledger.thinking_tokens
    totals.cached_tokens = ledger.cached_tokens
    totals.estimated_cost_usd = ledger.estimated_cost_usd
    return LLMUsageReport(
        since=datetime.fromtimestamp(ledger.started_at, tz=timezone.utc).isoformat(timespec="seconds"),
        provider=settings.llm_provider,
        model=model,
        pricing=LLMPricing(
            input_usd_per_1m=settings.llm_input_usd_per_1m,
            output_usd_per_1m=settings.llm_output_usd_per_1m,
        ),
        totals=totals,
    )


@router.get("/llm-usage")
def llm_usage() -> LLMUsageReport:
    """Token counts and estimated spend for every LLM call this process
    has made (the last 200 individually, all of them in the totals)."""
    return _report()


@router.post("/llm-usage/reset")
def reset_llm_usage() -> LLMUsageReport:
    """Zero the ledger -- e.g. right before a measured sample run."""
    ledger.reset()
    return _report()
