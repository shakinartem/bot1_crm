from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.research.phone_parser import extract_phones_from_html, extract_phones_from_text, normalize_phone_ru


def main() -> None:
    assert normalize_phone_ru("+7 999 123-45-67") == "+79991234567"
    assert normalize_phone_ru("8 (999) 123-45-67") == "+79991234567"
    assert normalize_phone_ru("7 999 1234567") == "+79991234567"
    assert normalize_phone_ru("1234567890") is None

    text = "Позвоните +7(999)1234567 или tel:+79991234567, ИНН 6451001234"
    assert extract_phones_from_text(text) == ["+79991234567"]
    html = '<a href="tel:+79991234567">call</a><span>8 999 123 45 67</span>'
    assert extract_phones_from_html(html) == ["+79991234567"]
    print("smoke_phone_parser ok")


if __name__ == "__main__":
    main()
