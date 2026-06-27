from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_website_quality.db")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")

from app.modules.enrichment.analyzer import analyze_website_html, compute_website_score  # noqa: E402


HTML_SNIPPET = """
<html>
<head>
    <title>Стоматология «Улыбка» — Москва</title>
    <meta name="description" content="Стоматология в Москве. Онлайн-запись, цены, отзывы." />
</head>
<body>
    <nav><a href="/contacts">Контакты</a><a href="https://t.me/ulydka_bot">Telegram</a></nav>
    <h1>Стоматология Улыбка</h1>
    <p>Телефон: +7 (495) 123-45-67</p>
    <p><a href="https://wa.me/79991234567">WhatsApp</a></p>
    <p>Цены на имплантацию и брекеты. <a href=\"/book\">Онлайн-запись</a>.</p>
    <section id="reviews">Отзывы</section>
    <section id="doctors">Врачи</section>
    <script>console.log('x');</script>
</body>
</html>
"""


def run() -> None:
    analysis = analyze_website_html(HTML_SNIPPET, "https://ulydka.ru")
    assert analysis.page_title, "missing page title"
    assert analysis.detected_contacts.phones, "missing phones"
    assert analysis.detected_contacts.emails or analysis.detected_contacts.telegram_links, "missing messengers"
    assert analysis.signals.has_prices
    assert analysis.signals.has_doctors_page
    assert analysis.signals.has_reviews_section
    assert analysis.signals.has_contacts_page
    assert analysis.signals.has_online_booking or "запись" in analysis.raw_text_excerpt.lower()
    assert analysis.signals.has_social_links
    assert analysis.signals.has_messenger_links

    score = compute_website_score("https://ulydka.ru", analysis.signals, len(HTML_SNIPPET))
    assert 0 <= score <= 100, score
    assert score > 50, f"unexpected low score: {score}"

    low = analyze_website_html("<html><head><title>t</title></head><body>x</body></html>", "http://bad.local")
    low_score = compute_website_score("http://bad.local", low.signals, 10)
    assert low_score < 50, low_score

    print("smoke_website_quality ok")


if __name__ == "__main__":
    run()