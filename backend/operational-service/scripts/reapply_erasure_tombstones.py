"""Post-restore backup reconciliation CLI: reapplies public.privacy_erasure_tombstones (PRV-019)."""

import argparse
import json
import sys

from app.core.database import SessionLocal
from app.services.privacy_case_service import reapply_erasure_tombstones


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reapply privacy erasure tombstones after backup restore")
    parser.add_argument("--schema", default=None, help="Optional single tenant schema_name to reconcile")
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        result = reapply_erasure_tombstones(db, schema_name=args.schema)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
