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


COMPANY_STATUS_LABELS = {
    CompanyStatus.NEW.value: "Новый лид",
    CompanyStatus.RESEARCH_NEEDED.value: "Нужен ресерч",
    CompanyStatus.PREPARED.value: "Подготовлен",
    CompanyStatus.CALL_PLANNED.value: "Запланирован звонок",
    CompanyStatus.CALLED.value: "Был звонок",
    CompanyStatus.NO_ANSWER.value: "Не дозвонились",
    CompanyStatus.INTERESTED.value: "Интересно",
    CompanyStatus.CONSULTATION_PLANNED.value: "Назначена консультация",
    CompanyStatus.PROPOSAL_SENT.value: "КП отправлено",
    CompanyStatus.DEAL_WON.value: "Сделка выиграна",
    CompanyStatus.DEAL_LOST.value: "Сделка проиграна",
    CompanyStatus.DO_NOT_CONTACT.value: "Не контактировать",
}

PRIORITY_LABELS = {
    LeadPriority.LOW.value: "Низкий",
    LeadPriority.MEDIUM.value: "Средний",
    LeadPriority.HIGH.value: "Высокий",
}

CONTACT_TYPE_LABELS = {
    ContactType.PHONE.value: "phone",
    ContactType.EMAIL.value: "email",
    ContactType.WEBSITE.value: "website",
    ContactType.TELEGRAM.value: "telegram",
    ContactType.WHATSAPP.value: "whatsapp",
    ContactType.VK.value: "vk",
    ContactType.INSTAGRAM.value: "instagram",
    ContactType.OTHER.value: "other",
}

INTERACTION_TYPE_LABELS = {
    InteractionType.CALL.value: "Звонок",
    InteractionType.MESSAGE.value: "Сообщение",
    InteractionType.EMAIL.value: "Email",
    InteractionType.MEETING.value: "Встреча",
    InteractionType.CONSULTATION.value: "Консультация",
    InteractionType.PROPOSAL.value: "КП",
    InteractionType.NOTE.value: "Заметка",
}

INTERACTION_RESULT_LABELS = {
    InteractionResult.NO_ANSWER.value: "Не дозвонился",
    InteractionResult.REJECTED.value: "Отказ",
    InteractionResult.INTERESTED.value: "Интересно",
    InteractionResult.CALLBACK_REQUESTED.value: "Перезвонить позже",
    InteractionResult.CONSULTATION_BOOKED.value: "Назначена консультация",
    InteractionResult.PROPOSAL_REQUESTED.value: "Запросили КП",
    InteractionResult.DEAL_WON.value: "Сделка",
    InteractionResult.DEAL_LOST.value: "Сделка проиграна",
    InteractionResult.OTHER.value: "Другое",
}
