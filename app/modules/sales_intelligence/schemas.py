from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SalesMaterialScore(BaseModel):
    company_id: int
    total_score: int = Field(ge=0, le=100)
    grade: Literal["weak", "basic", "normal", "strong", "excellent"]
    website_score: int = Field(ge=0, le=100)
    socials_score: int = Field(ge=0, le=100)
    maps_score: int = Field(ge=0, le=100)
    trust_score: int = Field(ge=0, le=100)
    conversion_score: int = Field(ge=0, le=100)
    contact_score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    next_improvements: list[str] = Field(default_factory=list)


class ClosingCriterionReadiness(BaseModel):
    score: int = Field(ge=0, le=100)
    status: Literal["unknown", "weak", "possible", "strong"]
    evidence: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class ClosingCriteriaReadiness(BaseModel):
    financial_opportunity: ClosingCriterionReadiness
    conscious_need: ClosingCriterionReadiness
    trust: ClosingCriterionReadiness
    decision_maker: ClosingCriterionReadiness
    here_and_now: ClosingCriterionReadiness
    summary: str
    risks: list[str] = Field(default_factory=list)
    next_best_question: str


class SopranoQuestionSet(BaseModel):
    company_id: int
    niche: str | None = None
    niche_detected: str | None = None
    niche_confidence: float | None = Field(default=None, ge=0, le=1)
    intro: str
    situation: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    principles: list[str] = Field(default_factory=list)
    solutions: list[str] = Field(default_factory=list)
    analogies: list[str] = Field(default_factory=list)
    undesired: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_order: list[str] = Field(default_factory=list)


class ObjectionHandlingItem(BaseModel):
    objection: str
    response_principle: str
    suggested_response: str


class ColdCallPlan(BaseModel):
    company_id: int
    company_name: str
    niche: str | None = None
    niche_detected: str | None = None
    niche_confidence: float | None = Field(default=None, ge=0, le=1)
    generation_mode: Literal["ai", "fallback"]
    confidence: Literal["low", "medium", "high"]
    created_at: datetime
    call_goal: str
    opener: str
    reason_for_call: str
    personalization_points: list[str] = Field(default_factory=list)
    digital_observations: list[str] = Field(default_factory=list)
    likely_pains: list[str] = Field(default_factory=list)
    closing_criteria: ClosingCriteriaReadiness
    soprano_questions: SopranoQuestionSet
    objection_preparation: list[ObjectionHandlingItem] = Field(default_factory=list)
    first_offer: str
    next_best_action: str
    call_script_short: str
    call_script_detailed: str
    copyable_short_script: str
    manager_checklist: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    do_not_say: list[str] = Field(default_factory=list)


class ColdCallPlanRequest(BaseModel):
    use_ai: bool = True
    force_regenerate: bool = False
    niche: str | None = None


class LatestSalesIntelligenceRead(BaseModel):
    material_score: SalesMaterialScore
    closing_criteria: ClosingCriteriaReadiness
    soprano_questions: SopranoQuestionSet
    cold_call_plan: ColdCallPlan | None = None
    saved_at: datetime | None = None


__all__ = [
    "ClosingCriteriaReadiness",
    "ClosingCriterionReadiness",
    "ColdCallPlan",
    "ColdCallPlanRequest",
    "LatestSalesIntelligenceRead",
    "ObjectionHandlingItem",
    "SalesMaterialScore",
    "SopranoQuestionSet",
]
