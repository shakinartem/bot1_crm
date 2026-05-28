from __future__ import annotations

from app.modules.crm.models import Company
from app.modules.enrichment.schemas import Bot2EnrichmentContextRead
from app.modules.intelligence.schemas import Bot2IntelligenceContextRead


def build_cold_call_prompt(
    company: Company,
    enrichment: Bot2EnrichmentContextRead | None = None,
    intelligence: Bot2IntelligenceContextRead | None = None,
) -> str:
    decision_makers = "\n".join(
        f"- {dm.full_name}, {dm.role or 'роль не указана'}, телефон: {dm.phone or 'нет'}, Telegram: {dm.telegram or 'нет'}"
        for dm in company.decision_makers
    ) or "ЛПР пока не указаны."
    interactions = "\n".join(
        f"- {item.created_at:%Y-%m-%d}: {item.type}, результат: {item.result or 'нет'}, кратко: {item.summary or 'нет'}"
        for item in company.interactions[:10]
    ) or "Истории касаний пока нет."

    enrichment_block = "Исследование сайта пока не проводилось."
    if enrichment:
        social_names = ", ".join(key for key, value in enrichment.detected_socials.items() if value) or "не обнаружены"
        map_names = ", ".join(key for key, value in enrichment.detected_maps.items() if value) or "не обнаружены"
        hypothesis_lines = "\n".join(f"- {item}" for item in enrichment.hypotheses[:5]) or "- нет"
        enrichment_block = (
            f"- Статус research: {enrichment.status or 'нет'}\n"
            f"- Сайт: {enrichment.website_url or company.website or 'не указан'}\n"
            f"- Сигналы: запись {'да' if enrichment.signals.has_online_booking else 'нет'}, "
            f"callback {'да' if enrichment.signals.has_callback_form else 'нет'}, "
            f"отзывы {'да' if enrichment.signals.has_reviews_section else 'нет'}, "
            f"врачи {'да' if enrichment.signals.has_doctors_page else 'нет'}, "
            f"мессенджеры {'да' if enrichment.signals.has_messenger_links else 'нет'}\n"
            f"- Соцсети: {social_names}\n"
            f"- Карты/площадки: {map_names}\n"
            f"- AI-резюме: {enrichment.ai_summary or 'нет'}\n"
            f"- Гипотезы:\n{hypothesis_lines}"
        )

    intelligence_block = "INN-first intelligence пока не проводился."
    if intelligence:
        social_bits = []
        if intelligence.parsed_socials.vk_links:
            social_bits.append("VK")
        if intelligence.parsed_socials.telegram_links:
            social_bits.append("Telegram")
        if intelligence.parsed_socials.instagram_links:
            social_bits.append("Instagram")
        intelligence_block = (
            f"- Статус intelligence: {intelligence.status or 'нет'}\n"
            f"- ИНН: {intelligence.inn or company.inn or 'не указан'}\n"
            f"- Юрлицо: {intelligence.legal_name or company.legal_name or 'не указано'}\n"
            f"- ОГРН: {intelligence.ogrn or 'не указан'}\n"
            f"- Адрес: {intelligence.legal_address or company.address or 'не указан'}\n"
            f"- Сайт: {intelligence.website_url or company.website or 'не найден'}\n"
            f"- Confidence сайта: {intelligence.website_confidence or 0:.0f}\n"
            f"- Контакты с сайта: телефоны {', '.join(intelligence.parsed_contacts.phones[:3]) or 'не найдены'}; "
            f"email {', '.join(intelligence.parsed_contacts.emails[:3]) or 'не найдены'}\n"
            f"- Соцсети: {', '.join(social_bits) or 'не найдены'}\n"
            f"- Сигналы: запись {'да' if intelligence.parsed_signals.has_online_booking else 'нет'}, "
            f"форма {'да' if intelligence.parsed_signals.has_callback_form else 'нет'}, "
            f"отзывы {'да' if intelligence.parsed_signals.has_reviews_section else 'нет'}, "
            f"врачи {'да' if intelligence.parsed_signals.has_doctors_page else 'нет'}\n"
            f"- AI-резюме: {intelligence.ai_summary or 'нет'}\n"
            f"- Гипотезы:\n" + ("\n".join(f"- {item}" for item in intelligence.hypotheses[:5]) or "- нет")
        )

    return f"""
TASK: COLD_CALL_PREP

Ты sales intelligence ассистент агентства ШАРиК digital.
Подготовь менеджера к холодному звонку в стоматологическую клинику.

Данные клиники:
- Название: {company.name}
- Юридическое название: {company.legal_name or "не указано"}
- ИНН: {company.inn or "не указан"}
- Город: {company.city or "не указан"}
- Регион: {company.region or "не указан"}
- Адрес: {company.address or "не указан"}
- Телефон: {company.phone or "не указан"}
- Сайт: {company.website or "не указан"}
- Социальные ссылки: {company.social_links or company.other_socials or "не указаны"}
- Карты: {company.maps_url or "не указаны"}
- Рейтинг: {company.rating or "не указан"}
- Отзывы: {company.reviews_count or "не указаны"}
- Источник: {company.source or "не указан"}
- Статус: {company.status}
- Приоритет: {company.priority}
- Заметки: {company.notes or "нет"}

ЛПР:
{decision_makers}

История касаний:
{interactions}

Research сайта / digital-присутствия:
{enrichment_block}

INN-first intelligence:
{intelligence_block}

Формула продаж:
1. ФВ — финансовая возможность.
2. ОП — осознанная потребность.
3. Д — доверие.
4. ЛПР — лицо, принимающее решение.
5. ЗС — здесь и сейчас.

Для выявления потребности используй СОПРАНО:
С — ситуация, О — опыт, П — принципы, Р — решения, А — аналогии, Н — нежелательное, О — ограничения.

Сгенерируй строго по разделам:
1. Краткое резюме клиники.
2. Возможные боли.
3. Что проверить перед звонком.
4. Скрипт первого звонка.
5. 5 персонализированных заходов.
6. Возможные возражения.
7. Ответы на возражения.
8. Что предложить как первый шаг.
9. Короткий текст сообщения после звонка.
10. Следующее действие.

Пиши по-русски, практично, без воды. Не выдумывай факты, если данных нет: помечай их как гипотезы. Учитывай и website research, и intelligence при вопросах о записи, доверии, юрданных, контактах, мессенджерах, отзывах и пути пациента до записи.
""".strip()


def build_mini_audit_prompt(company_context: dict) -> str:
    return f"""
TASK: MINI_AUDIT

Ты эксперт ШАРиК digital. Подготовь осторожный и полезный черновик мини-аудита / КП
для стоматологической клиники. ШАРиК digital не просто ведет соцсети, а ищет, где
клиника теряет пациентов: реклама, сайт, квизы/формы, мессенджеры, администраторы,
аналитика, повторные касания, отзывы, контент, карты, путь пациента до записи.

Тон:
- экспертный;
- спокойный;
- без агрессивных обещаний;
- без фейковых цифр;
- с фокусом на диагностику и рост записи.

Если данных мало, обязательно используй осторожные формулировки:
- "По имеющимся данным можно предположить..."
- "Для точной оценки нужно проверить..."
- "На консультации стоит уточнить..."

Контекст компании:
- Название: {company_context.get('name') or 'не указано'}
- Город: {company_context.get('city') or 'не указан'}
- Сайт: {company_context.get('website') or 'не указан'}
- Статус продажи: {company_context.get('status_label') or company_context.get('status') or 'не указан'}
- Источник: {company_context.get('source') or 'не указан'}
- Заметки: {company_context.get('notes') or 'нет'}
- История касаний:
{company_context.get('recent_interactions') or 'нет данных'}

Сформируй результат строго в формате:

# Мини-аудит digital-присутствия

Клиника:
Город:
Сайт:
Статус продажи:

## 1. Что видно по текущей упаковке
...

## 2. Где клиника может терять пациентов
- реклама
- сайт
- формы заявки
- мессенджеры
- администраторы
- повторные касания
- отзывы/карты

## 3. Что можно улучшить быстро
...

## 4. Что предложить на первом этапе
...

## 5. Мягкий текст для клиента
...

## 6. Следующий шаг
...
""".strip()


def build_fallback_mini_audit(company_context: dict) -> str:
    return (
        "# Мини-аудит digital-присутствия\n\n"
        f"Клиника: {company_context.get('name') or 'не указано'}\n"
        f"Город: {company_context.get('city') or 'не указан'}\n"
        f"Сайт: {company_context.get('website') or 'не указан'}\n"
        f"Статус продажи: {company_context.get('status_label') or company_context.get('status') or 'не указан'}\n\n"
        "## 1. Что видно по текущей упаковке\n"
        "По имеющимся данным можно предположить, что клинике нужен короткий аудит пути пациента от первого касания до записи. "
        "Для точной оценки стоит проверить сайт, отзывы, карты, мессенджеры и скорость реакции администраторов.\n\n"
        "## 2. Где клиника может терять пациентов\n"
        "- реклама может приводить нецелевой трафик\n"
        "- сайт может терять заявки на формах и мобильной версии\n"
        "- мессенджеры и звонки могут обрабатываться без единого сценария\n"
        "- повторные касания и возврат пациентов могут быть не систематизированы\n"
        "- отзывы и карточки на картах могут использоваться не в полную силу\n\n"
        "## 3. Что можно улучшить быстро\n"
        "На первом этапе стоит проверить точки входа: сайт, кнопки записи, контакты, формы, WhatsApp/Telegram, а также то, "
        "как клиника отвечает на входящие обращения.\n\n"
        "## 4. Что предложить на первом этапе\n"
        "Можно предложить диагностическую консультацию, мини-аудит сайта и рекламы, а также разбор пути пациента до записи.\n\n"
        "## 5. Мягкий текст для клиента\n"
        "По имеющимся данным можно предположить несколько точек роста, но для точной оценки важно посмотреть, где именно "
        "теряются обращения и как клиника доводит пациента до записи.\n\n"
        "## 6. Следующий шаг\n"
        "Назначить консультацию и собрать дополнительные данные: доступы к сайту, рекламе, аналитике и текущим скриптам обработки обращений."
    )


def build_daily_digest_recommendation_prompt(summary: dict) -> str:
    return f"""
TASK: DAILY_DIGEST_RECOMMENDATION

Ты sales lead assistant агентства ШАРиК digital.
На основе краткого дайджеста дня предложи 3 главных действия менеджеру по стоматологическим клиникам.

Не выдумывай данные, не обещай результаты, пиши коротко и по делу.
Фокус: продажи, follow-up, заинтересованные лиды, КП, консультации, возврат лидов без касаний.

Сводка:
- Просроченные задачи: {summary.get('overdue_tasks', 0)}
- Задачи на сегодня: {summary.get('today_tasks', 0)}
- Горячие лиды: {summary.get('hot_leads', 0)}
- Давно без касаний: {summary.get('stale_leads', 0)}
- Вчера касаний: {summary.get('yesterday_interactions', 0)}
- Вчера интерес: {summary.get('yesterday_interested', 0)}
- Вчера консультаций: {summary.get('yesterday_consultations', 0)}
- Вчера КП: {summary.get('yesterday_proposals', 0)}
- Вчера отказов: {summary.get('yesterday_rejections', 0)}

Верни ответ максимум в 3 коротких пунктах на русском языке.
""".strip()
