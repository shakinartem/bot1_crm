from enum import StrEnum


class CompanyStatus(StrEnum):
    NEW = "new"
    NEEDS_CHECK = "needs_check"
    READY_FOR_CALL = "ready_for_call"
    CALL_PLANNED = "call_planned"
    NO_ANSWER = "no_answer"
    REFUSED = "refused"
    INTERESTED = "interested"
    CONSULTATION_SCHEDULED = "consultation_scheduled"
    CONSULTATION_DONE = "consultation_done"
    CLIENT = "client"
    ARCHIVED = "archived"


class InteractionType(StrEnum):
    NOTE = "note"
    CALL = "call"
    STATUS_CHANGE = "status_change"
    CONSULTATION = "consultation"
