from __future__ import annotations
from pydantic import BaseModel, Field


class JobItem(BaseModel):
    job_id: str
    title: str
    company: str = "Unknown"
    url: str
    source: str
    location: str = "Remote / Unspecified"
    salary: str = "Not specified"
    description: str = ""
    needs_smart_fetch: bool = False


class ScoredJob(BaseModel):
    job_id: str = Field(description="Exact job_id from input.")
    score: int = Field(ge=1, le=100, description="Suitability score from 1 to 100.")
    salary_range: str = Field(description="Extracted salary/rate range or 'Tidak dicantumkan'.")
    work_mode: str = Field(description="e.g., Remote Worldwide (Async), Remote APAC, Hybrid, Onsite, or Unclear.")
    tech_stack: list[str] = Field(default_factory=list, description="Up to 6 core technologies mentioned.")
    match_reason: str = Field(description="1-2 concise Indonesian sentences explaining why this matches the candidate.")
    red_flags: list[str] = Field(
        default_factory=list,
        description="Potential dealbreakers in Indonesian (e.g., 'Wajib domisili US', 'Gaji tidak dicantumkan', 'Deskripsi terlalu singkat').",
    )
    pitch_hook: str = Field(
        description="2-3 English sentences tailored to the candidate's Local-First RAG, AI Systems Engineering, and Context Engineering skills, ready to copy-paste as an application opening hook."
    )


class BatchScoreResponse(BaseModel):
    results: list[ScoredJob] = Field(default_factory=list)