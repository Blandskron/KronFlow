from pathlib import Path
import unittest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]


class Cycle8ComplianceAsCodeTests(unittest.TestCase):
    def test_validate_workflow_enforces_privacy_gates_and_sbom(self):
        workflow_path = REPO_ROOT / ".github" / "workflows" / "validate.yml"
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        jobs = workflow.get("jobs", {})

        # PRV-026: dedicated privacy-compliance quality gate job
        self.assertIn("privacy-compliance", jobs)
        privacy_steps = " ".join(
            str(step.get("run", "")) for step in jobs["privacy-compliance"].get("steps", [])
        )
        self.assertIn("test_pii_inventory_parity", privacy_steps)
        self.assertIn("test_pii_scrubber", privacy_steps)
        self.assertIn("test_cycle2_security_foundations", privacy_steps)
        self.assertIn("apps.audit.tests", privacy_steps)

        # PRV-027: CycloneDX SBOM generation in web and whatsapp-lab jobs
        web_steps = " ".join(str(step.get("run", "")) for step in jobs["web"].get("steps", []))
        self.assertIn("npm sbom --package-lock-only --sbom-format cyclonedx", web_steps)

        wa_steps = " ".join(str(step.get("run", "")) for step in jobs["whatsapp-lab"].get("steps", []))
        self.assertIn("npm sbom --package-lock-only --sbom-format cyclonedx", wa_steps)

        # Security gates remain active without bypasses
        self.assertIn("secrets", jobs)
        self.assertIn("python", jobs)

    def test_picomatch_temporary_exception_retired(self):
        script_text = (REPO_ROOT / ".github" / "scripts" / "check-dev-audit.mjs").read_text(encoding="utf-8")
        self.assertNotIn("GHSA-fc5q-39xc-vjpf", script_text)
        self.assertNotIn("picomatch", script_text)
        self.assertIn("new Map()", script_text)


if __name__ == "__main__":
    unittest.main()
