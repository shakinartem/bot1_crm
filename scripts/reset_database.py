from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")

from app.database import async_session_factory  # noqa: E402
from app.modules.admin_reset.service import reset_database  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset CRM/all_data database state.")
    parser.add_argument("--mode", choices=["crm_only", "all_data"], default="crm_only")
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--keep-users", dest="keep_users", action="store_true", default=True)
    parser.add_argument("--drop-users", dest="keep_users", action="store_false")
    parser.add_argument("--clear-debug-files", dest="clear_debug_files", action="store_true")
    parser.add_argument("--no-clear-debug-files", dest="clear_debug_files", action="store_false")
    parser.set_defaults(clear_debug_files=None)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    expected_confirmation = "RESET ALL DATA" if args.mode == "all_data" else "RESET CRM"
    if args.confirmation != expected_confirmation:
        raise SystemExit(f"Invalid confirmation phrase. Expected: {expected_confirmation}")

    async with async_session_factory() as session:
        result = await reset_database(
            session,
            mode=args.mode,
            keep_users=args.keep_users,
            clear_debug_files=args.clear_debug_files,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
