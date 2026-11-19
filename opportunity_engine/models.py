from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl

OppType = Literal["event", "hackathon", "internship", "job", "program", "fellowship", "competition", "other"]
Status = Literal["new", "saved", "applied", "skipped", "expired"]

class RawItem(BaseModel):
    source: str
    source_id: str
    url: str
    title: str
    org: str = ""
    description: str = ""
    location: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)

class Opportunity(BaseModel):
    id: int | None = None
    source: str
    source_id: str
    url: str
    title: str
    org: str = ""
    type: OppType = "other"
    description: str = ""
    location: str = ""
    is_remote: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    deadline: datetime | None = None
    eligibility: str = ""
    compensation: str = ""
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    score: int | None = None
    score_reason: str = ""
    status: Status = "new"

class Profile(BaseModel):
    skills: list[str] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
    goals: str = ""
