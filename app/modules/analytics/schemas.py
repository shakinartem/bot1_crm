from __future__ import annotations

from pydantic import BaseModel, Field


class FunnelAnalyticsRead(BaseModel):
    total_companies: int
    new_count: int
    research_needed_count: int
    prepared_count: int
    call_planned_count: int
    called_count: int
    no_answer_count: int
    interested_count: int
    consultation_planned_count: int
    proposal_sent_count: int
    deal_won_count: int
    deal_lost_count: int
    do_not_contact_count: int
    new_to_interested_conversion: float | None = None
    interested_to_consultation_conversion: float | None = None
    consultation_to_proposal_conversion: float | None = None
    proposal_to_won_conversion: float | None = None
    note: str = "Ориентировочно по текущей CRM-базе."


class SourceAnalyticsItem(BaseModel):
    source: str
    total_companies: int
    new_count: int
    interested_count: int
    consultation_planned_count: int
    proposal_sent_count: int
    deal_won_count: int
    deal_lost_count: int
    open_tasks: int
    interactions_total: int
    conversion_to_interested: float | None = None
    conversion_to_consultation: float | None = None
    conversion_to_won: float | None = None


class CityAnalyticsItem(BaseModel):
    city: str
    region: str | None = None
    total_companies: int
    interested_count: int
    consultation_planned_count: int
    proposal_sent_count: int
    deal_won_count: int
    deal_lost_count: int
    open_tasks: int
    stale_leads: int
    overdue_tasks: int
    conversion_to_interested: float | None = None
    conversion_to_consultation: float | None = None


class LeadScoreRead(BaseModel):
    company_id: int
    company_name: str
    city: str | None = None
    source: str | None = None
    status: str
    priority: str
    score: int
    grade: str
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_best_action: str
    has_open_task: bool = False
    has_overdue_task: bool = False
    last_interaction_result: str | None = None
    can_prepare_proposal: bool = False
    proposal_recommendation: str | None = None


class LeadScoreListRead(BaseModel):
    total: int
    items: list[LeadScoreRead]


class ColdBaseItem(BaseModel):
    company_id: int
    company_name: str
    city: str | None = None
    status: str
    score: int
    missing_fields: list[str] = Field(default_factory=list)
    next_best_action: str
    reasons: list[str] = Field(default_factory=list)


class AnalyticsExportResult(BaseModel):
    export_type: str
    file_path: str
    filename: str
    total_exported: int
    created_at: str
