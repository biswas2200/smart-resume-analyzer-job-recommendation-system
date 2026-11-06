"""Job recommendation endpoints (services/job_rank.py). The backend stores
the postings; this service only reads their text and ranks them."""

from fastapi import APIRouter

from app.models.schemas import (
    ExtractJobSkillsRequest,
    ExtractJobSkillsResponse,
    MarketDemandRequest,
    MarketDemandResponse,
    RankJobsRequest,
    RankJobsResponse,
    WeightsSnapshot,
    WeightsSnapshotAck,
)
from app.services import job_rank, market_demand, weights
from app.services.fingerprint import engine_fingerprint

router = APIRouter()


@router.post("/extract-job-skills")
def extract_job_skills(request: ExtractJobSkillsRequest) -> ExtractJobSkillsResponse:
    """The canonical skills each job posting asks for -- run once per
    posting when the backend stores it, and kept for every later ranking."""
    return ExtractJobSkillsResponse(
        jobs=job_rank.extract_job_skills(request.jobs), engine_fingerprint=engine_fingerprint()
    )


@router.post("/rank-jobs")
def rank_jobs(request: RankJobsRequest) -> RankJobsResponse:
    """Rank jobs (with their stored skills) against a resume's skills and its
    best-matched roles; every result carries its reasons. Deterministic, no LLM."""
    ranked = job_rank.rank_jobs(request.skills, request.roles, request.jobs, top_n=request.top_n)
    return RankJobsResponse(jobs=ranked, engine_fingerprint=engine_fingerprint())


@router.post("/market-demand")
def demand(request: MarketDemandRequest) -> MarketDemandResponse:
    """Which skills open jobs ask for, per catalogue role, and the EMA signal
    each role's catalogue skills should get (services/market_demand.py)."""
    roles, unassigned = market_demand.market_demand(request.jobs)
    return MarketDemandResponse(roles=roles, unassigned_jobs=unassigned)


@router.put("/weights-snapshot")
def install_weights(snapshot: WeightsSnapshot) -> WeightsSnapshotAck:
    """Installs the backend's latest EMA weights (FR-7.5) so role matching
    uses them from the next request on."""
    weights.install_snapshot(snapshot.model_dump())
    return WeightsSnapshotAck(snapshot_id=snapshot.snapshot_id, roles=len(snapshot.weights))

