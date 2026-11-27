from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]


class Cycle9ReleaseReadinessTests(unittest.TestCase):
    def test_prv028_restore_drill_and_tombstone_cli_exist(self):
        restore_test = (
            REPO_ROOT / "backend" / "operational-service" / "tests" / "test_operational_restore.py"
        ).read_text(encoding="utf-8")
        self.assertIn("test_restore_reapplies_erasure_tombstones_with_zero_pii_resurrection", restore_test)
        self.assertIn("reapply_erasure_tombstones", restore_test)

        cli_script = (
            REPO_ROOT / "backend" / "operational-service" / "scripts" / "reapply_erasure_tombstones.py"
        ).read_text(encoding="utf-8")
        self.assertIn("--schema", cli_script)
        self.assertIn("reapply_erasure_tombstones", cli_script)

    def test_prv029_release_readiness_documents_fk15_and_external_gates(self):
        rr = (REPO_ROOT / "RELEASE_READINESS.md").read_text(encoding="utf-8")
        self.assertIn("tenant_schema_v22", rr)
        self.assertIn("FK-15", rr)
        self.assertIn("PRV-028", rr)
        self.assertIn("PRV-029", rr)
        self.assertIn("reapply_erasure_tombstones.py", rr)
        self.assertIn("DPIA_TEMPLATE_ISO29134.md", rr)
        self.assertNotIn("GHSA-fc5q-39xc-vjpf", rr)

        deploy_readme = (REPO_ROOT / "deploy" / "README.md").read_text(encoding="utf-8")
        self.assertIn("reapply_erasure_tombstones.py", deploy_readme)


if __name__ == "__main__":
    unittest.main()
