from __future__ import annotations

from app.modules.ai.service import prepare_cold_call
from app.modules.crm.constants import TaskStatus
from app.modules.crm.service import format_datetime, get_company, humanize_company_status


async def build_consultation_handoff_payload(session, company_id: int) -> dict | None:
    company = await get_company(session, company_id)
    if not company:
        return None

    recent_interactions = sorted(
        company.interactions,
        key=lambda item: item.created_at,
        reverse=True,
    )[:5]
    tasks = sorted(
        company.tasks,
        key=lambda item: (item.due_at is None, item.due_at),
    )
    ai_call_prep = await prepare_cold_call(session, company_id)

    recommended_next_step = "Уточнить следующий шаг вручную."
    open_tasks = [task for task in tasks if task.status == TaskStatus.OPEN.value]
    if open_tasks:
        next_task = open_tasks[0]
        recommended_next_step = next_task.title
        if next_task.due_at:
            recommended_next_step = f"{recommended_next_step} ({format_datetime(next_task.due_at)})"
    elif recent_interactions and recent_interactions[0].next_action:
        recommended_next_step = recent_interactions[0].next_action

    return {
        "source": "bot1_crm",
        "company": {
            "id": company.id,
            "name": company.name,
            "legal_name": company.legal_name,
            "inn": company.inn,
            "ogrn": company.ogrn,
            "city": company.city,
            "region": company.region,
            "address": company.address,
            "phone": company.phone,
            "website": company.website,
            "status": company.status,
            "status_label": humanize_company_status(company.status),
            "source": company.source,
            "notes": company.notes,
        },
        "decision_makers": [
            {
                "id": dm.id,
                "full_name": dm.full_name,
                "role": dm.role,
                "phone": dm.phone,
                "email": dm.email,
                "telegram": dm.telegram,
                "is_primary": dm.is_primary,
                "notes": dm.notes,
            }
            for dm in company.decision_makers
        ],
        "contacts": [
            {
                "id": contact.id,
                "type": contact.type,
                "value": contact.value,
                "label": contact.label,
                "is_primary": contact.is_primary,
            }
            for contact in company.contacts
        ],
        "recent_interactions": [
            {
                "id": interaction.id,
                "type": interaction.type,
                "result": interaction.result,
                "summary": interaction.summary,
                "next_action": interaction.next_action,
                "created_at": format_datetime(interaction.created_at),
            }
            for interaction in recent_interactions
        ],
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "due_at": format_datetime(task.due_at) if task.due_at else None,
                "status": task.status,
                "priority": task.priority,
            }
            for task in tasks[:10]
        ],
        "ai_call_prep": ai_call_prep,
        "recommended_next_step": recommended_next_step,
    }
