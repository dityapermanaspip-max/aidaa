"""Apply AIDAA SQL files with the same database settings as the API.

The script loads the repository `.env` through `app.core.config`, so it never
duplicates connection details and never prints the password. A file is executed
in one transaction; `--dry-run` rolls the whole thing back.

AIDAA has no single schema file, so `--file` is required. Run the base files
(aidaa_iam_permission ... aidaa_execution) first, then the patches by number,
then the seeds a file needs (patch 10 before seed_locations_indonesia.sql).
Do NOT rerun patch 03 after patch 10.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.core.config import DB_NAME, DB_HOST, DB_USER  # noqa: E402
from app.core.database import engine  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="SQL file to apply (base file, patch by number, or seed; required)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="execute everything in one transaction and roll it back",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the confirmation prompt",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.file if args.file.is_absolute() else Path.cwd() / args.file
    if not path.is_file():
        print(f"SQL file not found: {path}", file=sys.stderr)
        return 2

    sql = path.read_text(encoding="utf-8")
    mode = "dry run (rollback)" if args.dry_run else "apply"
    print(f"Target: {DB_USER}@{DB_HOST}/{DB_NAME}")
    print(f"File  : {path}")
    print(f"Mode  : {mode}")

    if not args.yes:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled.")
            return 1

    with engine.connect() as conn:
        trans = conn.begin()
        # No bind parameters in these files (psql-style scripts), so execute through the DBAPI cursor
        # WITHOUT arguments. SQLAlchemy always passes an empty mapping, which would make psycopg2 treat
        # any literal % in the file (LIKE 'PROV-%', a comment) as a placeholder and fail; omittting the
        # argument also matches psql's multiple-statement behavior.
        cursor = conn.connection.cursor()
        try:
            cursor.execute(sql)
            if args.dry_run:
                trans.rollback()
                print("Dry run succeeded; rolled back.")
            else:
                trans.commit()
                print("SQL applied.")
        except Exception:
            trans.rollback()
            raise
        finally:
            cursor.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
