from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


LeadFitGroup = Literal[
    "A_hot_priority",
    "B_warm_potential",
    "C_neutral_database",
    "D_low_priority",
    "excluded_do_not_contact",
]


class LeadFitScore(BaseModel):
    company_id: int
    total_score: int
    group: LeadFitGroup
    group_label: str
    reasons: list[str] = Field(default_factory=list)
    disqualifiers: list[str] = Field(default_factory=list)
    recommended_next_action: str
    calculated_at: datetime


class LeadFitGroupSummary(BaseModel):
    total: int = 0
    A_hot_priority: int = 0
    B_warm_potential: int = 0
    C_neutral_database: int = 0
    D_low_priority: int = 0
    excluded_do_not_contact: int = 0
