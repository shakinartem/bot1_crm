from __future__ import annotations

from app.modules.enrichment.schemas import WebsiteAnalysis


def build_enrichment_summary_prompt(
    company_context: dict,
    analysis: WebsiteAnalysis,
    hypotheses: list[str],
) -> str:
    return f"""
TASK: ENRICHMENT_SUMMARY

Ты sales intelligence ассистент SHARiK digital.
Подготовь осторожное резюме digital-присутствия стоматологической клиники на основе быстрой внешней проверки сайта.

Правила:
- не выдумывай данные
- не делай жёстких выводов, если данных мало
- не обещай рост заявок
- не давай медицинских советов
- формулируй выводы как гипотезы и наблюдения
- фокусируйся на пути пациента до записи: сайт, формы, мессенджеры, доверие, отзывы, карты, соцсети

Компания:
- Название: {company_context.get('name') or 'не указано'}
- Город: {company_context.get('city') or 'не указан'}
- Сайт: {company_context.get('website') or 'не указан'}
- Источник: {company_context.get('source') or 'не указан'}
- Статус: {company_context.get('status') or 'не указан'}

Быстрые сигналы:
- Заголовок: {analysis.page_title or 'не обнаружен'}
- Meta description: {analysis.meta_description or 'не обнаружена'}
- Онлайн-запись: {'да' if analysis.signals.has_online_booking else 'нет'}
- Форма / callback: {'да' if analysis.signals.has_callback_form else 'нет'}
- Цены: {'да' if analysis.signals.has_prices else 'нет'}
- Врачи: {'да' if analysis.signals.has_doctors_page else 'нет'}
- Отзывы: {'да' if analysis.signals.has_reviews_section else 'нет'}
- Контакты: {'да' if analysis.signals.has_contacts_page or analysis.detected_contacts.phones or analysis.detected_contacts.emails else 'нет'}
- Соцсети: {'да' if analysis.signals.has_social_links else 'нет'}
- Мессенджеры: {'да' if analysis.signals.has_messenger_links else 'нет'}
- Карты / площадки: {', '.join(key for key, value in analysis.detected_maps.items() if value) or 'не обнаружены'}

Контакты:
- Телефоны: {', '.join(analysis.detected_contacts.phones) or 'не обнаружены'}
- Emails: {', '.join(analysis.detected_contacts.emails) or 'не обнаружены'}

Гипотезы:
{chr(10).join(f"- {item}" for item in hypotheses) or '- явных гипотез не сформировано'}

Верни результат строго в формате:

# Быстрое резюме digital-присутствия

## Что видно снаружи
...

## Возможные слабые места
...

## Что спросить на звонке
...

## Что можно предложить как первый шаг
...

## Осторожные гипотезы
...
""".strip()


def build_fallback_enrichment_summary(
    company_context: dict,
    analysis: WebsiteAnalysis,
    hypotheses: list[str],
) -> str:
    visible = []
    if analysis.page_title:
        visible.append(f"заголовок страницы: {analysis.page_title}")
    if analysis.detected_contacts.phones:
        visible.append("на сайте есть телефон")
    if analysis.signals.has_social_links:
        visible.append("обнаружены ссылки на соцсети")
    if analysis.detected_maps:
        platforms = [key for key, values in analysis.detected_maps.items() if values]
        if platforms:
            visible.append(f"обнаружены площадки: {', '.join(platforms)}")

    first_step = "Начать с короткой диагностики пути пациента до записи."
    if not analysis.signals.has_online_booking and not analysis.signals.has_callback_form:
        first_step = "Начать с разбора точки входа: онлайн-запись, форма заявки или быстрый способ задать вопрос."
    elif not analysis.signals.has_reviews_section:
        first_step = "Начать с усиления доверия: отзывы, карточки на картах и блоки врачей."

    questions = [
        "Как сейчас клиника принимает обращения с сайта и мессенджеров?",
        "Есть ли отдельный сценарий для первичного пациента до записи?",
    ]
    if not analysis.signals.has_prices:
        questions.append("Насколько осознанно клиника раскрывает стоимость или диапазоны цен перед первым обращением?")

    return "\n".join(
        [
            "# Быстрое резюме digital-присутствия",
            "",
            "## Что видно снаружи",
            f"По доступным данным можно предположить следующее: {', '.join(visible) or 'данных немного, сайт стоит проверить глубже на звонке'}.",
            "",
            "## Возможные слабые места",
            *(f"- {item}" for item in hypotheses[:5]),
            "",
            "## Что спросить на звонке",
            *(f"- {item}" for item in questions[:4]),
            "",
            "## Что можно предложить как первый шаг",
            first_step,
            "",
            "## Осторожные гипотезы",
            *(f"- {item}" for item in hypotheses[:5]),
        ]
    )
