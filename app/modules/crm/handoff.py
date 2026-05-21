from __future__ import annotations

from datetime import datetime

from app.modules.ai.service import generate_mini_audit, prepare_cold_call
from app.modules.crm.constants import TaskStatus
from app.modules.crm.service import (
    format_datetime,
    get_company_full_context,
    get_company_last_interaction,
    get_company_last_interactions,
    get_company_next_task,
    get_company_open_tasks,
    humanize_company_status,
    humanize_interaction_result,
    humanize_priority,
)


async def build_consultation_handoff_payload(session, company_id: int) -> dict | None:
    company = await get_company_full_context(session, company_id)
    if not company:
        return None

    recent_interactions = await get_company_last_interactions(session, company_id, limit=5)
    open_tasks = await get_company_open_tasks(session, company_id)
    next_task = await get_company_next_task(session, company_id)
    last_interaction = await get_company_last_interaction(session, company_id)
    ai_call_prep = await prepare_cold_call(session, company_id)
    mini_audit = await generate_mini_audit(session, company_id)

    recommended_next_step = "Уточнить следующий шаг вручную."
    if next_task:
        recommended_next_step = next_task.title
        if next_task.due_at:
            recommended_next_step = f"{recommended_next_step} ({format_datetime(next_task.due_at)})"
    elif last_interaction and last_interaction.next_action:
        recommended_next_step = last_interaction.next_action

    return {
        "version": "1.0",
        "source": "bot1_crm",
        "target": "bot2_consultation_ai",
        "created_at": datetime.now().isoformat(),
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
            "priority": company.priority,
            "priority_label": humanize_priority(company.priority),
            "source_label": company.source,
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
                "result_label": humanize_interaction_result(interaction.result) if interaction.result else None,
                "summary": interaction.summary,
                "next_action": interaction.next_action,
                "created_at": format_datetime(interaction.created_at),
            }
            for interaction in recent_interactions
        ],
        "open_tasks": [
            {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "due_at": format_datetime(task.due_at) if task.due_at else None,
                "status": task.status,
                "is_open": task.status == TaskStatus.OPEN.value,
                "priority": task.priority,
            }
            for task in open_tasks[:10]
        ],
        "sales_context": {
            "status": company.status,
            "status_label": humanize_company_status(company.status),
            "priority": company.priority,
            "priority_label": humanize_priority(company.priority),
            "last_result": last_interaction.result if last_interaction else None,
            "last_result_label": (
                humanize_interaction_result(last_interaction.result)
                if last_interaction and last_interaction.result
                else None
            ),
            "recommended_next_step": recommended_next_step,
        },
        "ai": {
            "call_prep": ai_call_prep,
            "mini_audit": mini_audit,
        },
        "manager_notes": company.notes,
        "integration_status": "draft_only",
    }
