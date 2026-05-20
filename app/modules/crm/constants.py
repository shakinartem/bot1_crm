from enum import StrEnum


class CompanyStatus(StrEnum):
    NEW = "new"
    RESEARCH_NEEDED = "research_needed"
    PREPARED = "prepared"
    CALL_PLANNED = "call_planned"
    CALLED = "called"
    NO_ANSWER = "no_answer"
    INTERESTED = "interested"
    CONSULTATION_PLANNED = "consultation_planned"
    PROPOSAL_SENT = "proposal_sent"
    DEAL_WON = "deal_won"
    DEAL_LOST = "deal_lost"
    DO_NOT_CONTACT = "do_not_contact"


class LeadPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContactType(StrEnum):
    PHONE = "phone"
    EMAIL = "email"
    WEBSITE = "website"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    VK = "vk"
    INSTAGRAM = "instagram"
    OTHER = "other"


class InteractionType(StrEnum):
    CALL = "call"
    MESSAGE = "message"
    EMAIL = "email"
    MEETING = "meeting"
    CONSULTATION = "consultation"
    PROPOSAL = "proposal"
    NOTE = "note"


class InteractionResult(StrEnum):
    NO_ANSWER = "no_answer"
    REJECTED = "rejected"
    INTERESTED = "interested"
    CALLBACK_REQUESTED = "callback_requested"
    CONSULTATION_BOOKED = "consultation_booked"
    PROPOSAL_REQUESTED = "proposal_requested"
    DEAL_WON = "deal_won"
    DEAL_LOST = "deal_lost"
    OTHER = "other"


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"
