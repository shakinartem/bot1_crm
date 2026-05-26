from __future__ import annotations

from pydantic import BaseModel


class TaskDigestItem(BaseModel):
    task_id: int
    company_id: int
    company_name: str
    title: str
    due_at: str | None = None
    priority: str
    company_status: str


class LeadDigestItem(BaseModel):
    company_id: int
    company_name: str
    city: str | None = None
    status: str
    priority: str
    score: int | None = None
    grade: str | None = None
    last_interaction_at: str | None = None
    last_interaction_result: str | None = None
    next_task_due_at: str | None = None
    next_task_title: str | None = None
    reason: str
    days_without_interaction: int | None = None
    proposal_recommendation: str | None = None


class ActivitySummary(BaseModel):
    interactions_total: int = 0
    calls_total: int = 0
    messages_total: int = 0
    emails_total: int = 0
    interested_count: int = 0
    consultations_count: int = 0
    proposals_count: int = 0
    deals_won_count: int = 0
    deals_lost_count: int = 0
    tasks_done_count: int = 0
    new_companies_count: int = 0
    overdue_tasks_count: int = 0


class DailyDigestRead(BaseModel):
    date: str
    overdue_tasks: list[TaskDigestItem]
    today_tasks: list[TaskDigestItem]
    hot_leads: list[LeadDigestItem]
    top_scored_leads: list[LeadDigestItem]
    stale_leads: list[LeadDigestItem]
    yesterday_activity: ActivitySummary
    recommendation: str


class WeeklySummaryRead(BaseModel):
    date_from: str
    date_to: str
    activity: ActivitySummary
    recommendation: str


class DigestSettingsRead(BaseModel):
    enabled: bool
    send_time: str
    weekdays: str
    stale_days: int
