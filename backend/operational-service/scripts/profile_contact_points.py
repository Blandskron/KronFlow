"""Count normalization coverage and duplicate contact points in a one-tenant CSV."""

import argparse
import csv
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

from app.services.contact_points import normalize_email, normalize_phone


NORMALIZERS = {"email": normalize_email, "phone": normalize_phone}


def profile_contacts(rows: Iterable[dict[str, str]]) -> dict:
    totals = {kind: Counter() for kind in NORMALIZERS}
    values = {kind: Counter() for kind in NORMALIZERS}
    contacts = 0
    for row in rows:
        if set(row) != NORMALIZERS.keys() or any(value is None for value in row.values()):
            raise ValueError("Each row must contain exactly two fields")
        contacts += 1
        for kind, normalize in NORMALIZERS.items():
            raw = row[kind]
            canonical = normalize(raw)
            if canonical is not None:
                values[kind][canonical] += 1
            else:
                totals[kind]["unresolved" if raw.strip() else "missing"] += 1

    return {
        "contacts": contacts,
        **{
            kind: {
                "missing": totals[kind]["missing"],
                "unresolved": totals[kind]["unresolved"],
                "normalized": contacts - totals[kind]["missing"] - totals[kind]["unresolved"],
                "duplicate_values": sum(count > 1 for count in values[kind].values()),
                "contacts_with_duplicates": sum(count for count in values[kind].values() if count > 1),
            }
            for kind in NORMALIZERS
        },
    }


def plan_contact_backfill(rows: Iterable[dict[str, str]]) -> dict:
    """Classify points without emitting addresses or assigning a shared value to a contact."""
    contact_ids = set()
    owners = {kind: defaultdict(list) for kind in NORMALIZERS}
    unresolved = {kind: [] for kind in NORMALIZERS}
    for row in rows:
        if set(row) != {"contact_id", *NORMALIZERS} or any(value is None for value in row.values()):
            raise ValueError("Each row must contain a contact ID, email and phone")
        raw_id = row["contact_id"].strip()
        if not raw_id.isascii() or not raw_id.isdecimal() or len(raw_id) > 19:
            raise ValueError("Expected a positive bigint contact ID")
        contact_id = int(raw_id)
        if not 1 <= contact_id <= 9223372036854775807 or contact_id in contact_ids:
            raise ValueError("Expected a unique positive bigint contact ID")
        contact_ids.add(contact_id)
        for kind, normalize in NORMALIZERS.items():
            raw = row[kind]
            canonical = normalize(raw)
            if canonical is not None:
                owners[kind][canonical].append(contact_id)
            elif raw.strip():
                unresolved[kind].append(contact_id)

    return {
        "contacts": len(contact_ids),
        "points": {
            kind: {
                "eligible": sorted(ids[0] for ids in owners[kind].values() if len(ids) == 1),
                "collisions": sorted(sorted(ids) for ids in owners[kind].values() if len(ids) > 1),
                "unresolved": sorted(unresolved[kind]),
            }
            for kind in NORMALIZERS
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="UTF-8 CSV, one row per contact")
    parser.add_argument("--plan", action="store_true", help="Classify backfill candidates using contact_id, email and phone")
    args = parser.parse_args()
    fields = ["contact_id", "email", "phone"] if args.plan else ["email", "phone"]
    try:
        with args.csv_file.open(encoding="utf-8-sig", newline="") as file:
            rows = csv.DictReader(file, strict=True)
            if sorted(rows.fieldnames or []) != sorted(fields):
                raise ValueError("Unexpected headers")
            report = plan_contact_backfill(rows) if args.plan else profile_contacts(rows)
    except (OSError, csv.Error, ValueError):
        parser.exit(2, f"Could not profile input. Check UTF-8, row shape and columns: {', '.join(fields)}.\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
