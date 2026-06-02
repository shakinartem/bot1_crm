from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from app.modules.sales_intelligence.schemas import (
    ClosingCriteriaReadiness,
    SalesMaterialScore,
    SopranoQuestionSet,
)


def build_cold_call_plan_prompt(
    company_context: dict[str, Any],
    material_score: SalesMaterialScore,
    closing_criteria: ClosingCriteriaReadiness,
    soprano_questions: SopranoQuestionSet,
) -> str:
    prompt_payload = {
        "company": company_context.get("company"),
        "niche_detected": company_context.get("niche_detected"),
        "niche_confidence": company_context.get("niche_confidence"),
        "decision_makers": company_context.get("decision_makers", [])[:3],
        "contacts": company_context.get("contacts", [])[:5],
        "recent_interactions": company_context.get("recent_interactions", [])[:5],
        "open_tasks": company_context.get("open_tasks", [])[:5],
        "latest_enrichment": company_context.get("latest_enrichment"),
        "latest_intelligence": company_context.get("latest_intelligence"),
        "latest_research": company_context.get("latest_research"),
        "latest_research_job_result": company_context.get("latest_research_job_result"),
        "scoring_context": company_context.get("scoring_context"),
        "material_score": material_score.model_dump(mode="json"),
        "closing_criteria": closing_criteria.model_dump(mode="json"),
        "soprano_questions": soprano_questions.model_dump(mode="json"),
    }
    output_contract = {
        "company_id": "integer",
        "company_name": "string",
        "niche": "string|null",
        "niche_detected": "string|null",
        "niche_confidence": "number|null",
        "generation_mode": '"ai"',
        "confidence": '"low"|"medium"|"high"',
        "created_at": "ISO-8601 datetime string",
        "call_goal": "string",
        "opener": "string",
        "reason_for_call": "string",
        "personalization_points": ["string"],
        "digital_observations": ["string"],
        "likely_pains": ["string"],
        "closing_criteria": "reuse the supplied structure shape",
        "soprano_questions": "reuse the supplied structure shape",
        "objection_preparation": [
            {
                "objection": "string",
                "response_principle": "string",
                "suggested_response": "string",
            }
        ],
        "first_offer": "string",
        "next_best_action": "string",
        "call_script_short": "string",
        "call_script_detailed": "string",
        "copyable_short_script": "string",
        "manager_checklist": ["string"],
        "risks": ["string"],
        "do_not_say": ["string"],
    }
    return "\n".join(
        [
            "ЗАДАЧА: SALES_INTELLIGENCE_COLD_CALL_PLAN",
            "",
            "Ты готовишь осторожный план cold call для digital-продажи.",
            "Используй только переданный контекст.",
            "Не выдумывай факты, метрики, бюджеты и внутренние процессы.",
            "Если данных не хватает, используй формулировки-гипотезы: возможно, вероятно, похоже, стоит проверить.",
            "Верни только валидный JSON.",
            "Не оборачивай JSON в markdown-блоки.",
            "",
            "Требования:",
            '- Установи "generation_mode" в "ai".',
            '- Все человекочитаемые тексты внутри JSON должны быть на русском языке.',
            '- Поле "copyable_short_script" должно быть коротким, простым и пригодным для копирования менеджером.',
            '- Сохрани структуру "closing_criteria" и "soprano_questions"; можно улучшать формулировки, но не схему.',
            '- Все наблюдения и боли должны опираться на контекст или быть явно обозначены как гипотеза.',
            '- Добавь практичную подготовку к возражениям и мягкий первый оффер.',
            "",
            "Контракт ответа:",
            _to_json(output_contract),
            "",
            "Контекст:",
            _to_json(prompt_payload),
        ]
    )


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default, indent=2)


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


__all__ = ["build_cold_call_plan_prompt"]
