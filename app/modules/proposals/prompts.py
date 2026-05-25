from __future__ import annotations


def build_commercial_proposal_prompt(company_context: dict, packages: list[dict]) -> str:
    package_block = "\n".join(
        [
            (
                f"- {item['title']} | цена: {item['price']}\n"
                f"  Состав: {', '.join(item['items'])}\n"
                f"  Почему выбрано: {item['reason']}"
            )
            for item in packages
        ]
    )

    return f"""
TASK: COMMERCIAL_PROPOSAL

Ты готовишь черновик коммерческого предложения от ШАРиК digital для стоматологической клиники.

Требования:
- не придумывай точные цифры и гарантии;
- используй формулировки "по имеющимся данным", "ориентировочно", "после диагностики уточняется";
- пиши уверенно, но без пафоса;
- фокус: digital-воронка стоматологии, путь пациента, доверие, заявки, запись, обработка обращений;
- объясняй, зачем каждое решение клинике;
- избегай воды;
- если данных мало, помечай гипотезы как гипотезы.

Контекст компании:
- Название: {company_context.get('name') or 'не указано'}
- Юр. название: {company_context.get('legal_name') or 'не указано'}
- Город: {company_context.get('city') or 'не указан'}
- Сайт: {company_context.get('website') or 'не указан'}
- Статус: {company_context.get('status_label') or company_context.get('status') or 'не указан'}
- Приоритет: {company_context.get('priority_label') or company_context.get('priority') or 'не указан'}
- Источник: {company_context.get('source') or 'не указан'}
- Заметки: {company_context.get('notes') or 'нет'}
- Последняя AI-подготовка: {company_context.get('ai_call_prep') or 'нет'}
- Последний мини-аудит/КП: {company_context.get('latest_proposal') or 'нет'}
- Последние касания:
{company_context.get('recent_interactions') or 'нет данных'}
- Открытые задачи:
{company_context.get('open_tasks') or 'нет'}

Выбранные пакеты:
{package_block}

Сформируй результат строго в формате:

# Коммерческое предложение

Для: {{{company_context.get('name') or 'Клиника'}}}
От: ШАРиК digital

## 1. Контекст
...

## 2. Предполагаемая проблема
...

## 3. Предлагаемое решение
...

## 4. План работ на первый месяц
Неделя 1:
Неделя 2:
Неделя 3:
Неделя 4:

## 5. Что нужно от клиента
...

## 6. Стоимость
...

## 7. Следующий шаг
...

## 8. Сообщение клиенту
...
""".strip()
