import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import bot as bot_module
from app.api.routes import router as api_router
from app.main import app
from app.modules.crm import models, schemas, service


def main() -> None:
    assert app.title == "SHARiK Sales Intelligence Bot"
    assert bot_module.main is not None
    assert models.Company.__tablename__ == "companies"
    assert models.ContactPoint.__tablename__ == "contact_points"
    assert schemas.CompanyRead is not None
    assert service.create_company is not None
    assert api_router is not None
    print("smoke_check ok")


if __name__ == "__main__":
    main()
