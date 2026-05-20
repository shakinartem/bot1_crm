from app.modules.crm.models import Company


def build_cold_call_prompt(company: Company) -> str:
    decision_makers = "\n".join(
        f"- {dm.full_name}, {dm.role or 'роль не указана'}, телефон: {dm.phone or 'нет'}, Telegram: {dm.telegram or 'нет'}"
        for dm in company.decision_makers
    ) or "ЛПР пока не указаны."
    interactions = "\n".join(
        f"- {item.created_at:%Y-%m-%d}: {item.type}, результат: {item.result or 'нет'}, кратко: {item.summary or 'нет'}"
        for item in company.interactions[:10]
    ) or "Истории касаний пока нет."

    return f"""
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

Формула продаж:
1. ФВ — финансовая возможность.
2. ОП — осознанная потребность.
3. Д — доверие.
4. ЛПР — лицо принимающее решение.
5. ЗС — здесь и сейчас.

Для выявления потребности используй СОПРАНО:
С — ситуация, О — опыт, П — принципы, Р — решения, А — аналоги, Н — нежелательное, О — ограничения.

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

Пиши по-русски, практично, без воды. Не выдумывай факты, если данных нет: помечай их как гипотезы.
""".strip()
