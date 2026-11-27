"""PRV-001 / QG-0: Validate 1:1 parity between IAM Django models and compliance/data_inventory.yaml."""

from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_PATH = REPO_ROOT / "compliance" / "data_inventory.yaml"
OWNED_APP_LABELS = {"accounts", "audit", "contact", "iam_sessions", "rbac", "security", "tenants"}
REQUIRED_PII_FIELDS = {"category", "sensitivity", "legal_basis", "retention", "export_action", "erase_action"}


class AuthPiiInventoryParityTests(SimpleTestCase):
    def test_auth_models_match_declarative_pii_inventory(self):
        self.assertTrue(INVENTORY_PATH.exists(), f"Missing declarative PII inventory: {INVENTORY_PATH}")
        data = yaml.safe_load(INVENTORY_PATH.read_text(encoding="utf-8"))
        allowed = data["allowed_values"]
        service_tables = data["services"]["auth-service"]["tables"]

        owned_models = [
            model
            for model in apps.get_models()
            if model._meta.app_label in OWNED_APP_LABELS and model.__module__.startswith("apps.")
        ]
        owned_models.append(get_user_model())
        model_map = {model._meta.db_table: model for model in owned_models}

        missing_tables = sorted(set(model_map.keys()) - set(service_tables.keys()))
        extra_tables = sorted(set(service_tables.keys()) - set(model_map.keys()))
        self.assertEqual(missing_tables, [], f"IAM tables missing from compliance/data_inventory.yaml: {missing_tables}")
        self.assertEqual(extra_tables, [], f"Stale IAM tables in compliance/data_inventory.yaml: {extra_tables}")

        for table_name in sorted(model_map.keys()):
            model = model_map[table_name]
            entry = service_tables[table_name]
            self.assertIn(entry.get("owner_role"), allowed["owner_roles"], f"Invalid owner_role on {table_name}")
            self.assertIsInstance(entry.get("contains_pii"), bool, f"contains_pii must be bool on {table_name}")
            self.assertTrue(entry.get("retention_policy"), f"Missing retention_policy on {table_name}")

            pii_cols = entry.get("pii_columns") or {}
            non_pii_cols = set(entry.get("non_pii_columns") or [])
            overlap = set(pii_cols.keys()) & non_pii_cols
            self.assertEqual(overlap, set(), f"Columns declared as both PII and non-PII in {table_name}: {overlap}")

            if entry["contains_pii"]:
                self.assertTrue(pii_cols, f"{table_name} has contains_pii=true but empty pii_columns")
            else:
                self.assertEqual(pii_cols, {}, f"{table_name} has contains_pii=false but non-empty pii_columns")

            actual_cols = {field.column for field in model._meta.concrete_fields}
            declared_cols = set(pii_cols.keys()) | non_pii_cols
            missing_cols = sorted(actual_cols - declared_cols)
            extra_cols = sorted(declared_cols - actual_cols)
            self.assertEqual(missing_cols, [], f"Unclassified columns in {table_name}: {missing_cols}")
            self.assertEqual(extra_cols, [], f"Stale columns in {table_name}: {extra_cols}")

            for col_name, meta in pii_cols.items():
                self.assertEqual(
                    set(meta.keys()),
                    REQUIRED_PII_FIELDS,
                    f"Column {table_name}.{col_name} must declare exactly {sorted(REQUIRED_PII_FIELDS)}",
                )
                self.assertIn(meta["category"], allowed["categories"], f"Invalid category on {table_name}.{col_name}")
                self.assertIn(meta["sensitivity"], allowed["sensitivities"], f"Invalid sensitivity on {table_name}.{col_name}")
                self.assertIn(meta["legal_basis"], allowed["legal_bases"], f"Invalid legal_basis on {table_name}.{col_name}")
                self.assertIn(meta["export_action"], allowed["export_actions"], f"Invalid export_action on {table_name}.{col_name}")
                self.assertIn(meta["erase_action"], allowed["erase_actions"], f"Invalid erase_action on {table_name}.{col_name}")
                self.assertTrue(str(meta["retention"]).strip(), f"Empty retention on {table_name}.{col_name}")
