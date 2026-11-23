import unittest

from app.services.contact_points import normalize_email, normalize_phone
from scripts.profile_contact_points import plan_contact_backfill, profile_contacts


class ContactPointTests(unittest.TestCase):
    def test_email_preserves_the_local_part_and_lowercases_the_domain(self):
        self.assertEqual(normalize_email(" A.B+tag@EXAMPLE.TEST "), "A.B+tag@example.test")
        for value in (None, "", "a..b@example.test", "a@-example.test", "a@localhost", "ü@example.test"):
            with self.subTest(value=value):
                self.assertIsNone(normalize_email(value))

    def test_phone_requires_an_explicit_international_prefix(self):
        self.assertEqual(normalize_phone(" +56 (9) 1234-5678 "), "+56912345678")
        self.assertEqual(normalize_phone("+1(555)123-4567"), "+15551234567")
        self.assertEqual(normalize_phone("+123456789012345"), "+123456789012345")
        for value in (None, "", "56912345678", "0056912345678", "+0123", "+1234567890123456",
                      "+44 (0) 1234", "+1 555 x2", "+١٢٣", "+12 (3 4567"):
            with self.subTest(value=value):
                self.assertIsNone(normalize_phone(value))

    def test_profile_counts_duplicate_values_and_rows_without_returning_values(self):
        rows = [
            {"email": "A+tag@EXAMPLE.TEST", "phone": "+56 (9) 1234-5678"},
            {"email": "A+tag@example.test", "phone": "+56912345678"},
            {"email": "a+tag@example.test", "phone": "56912345678"},
            {"email": "incomplete@example", "phone": ""},
            {"email": " ", "phone": "+56 9 1234 5678"},
        ]
        expected = {
            "contacts": 5,
            "email": {"missing": 1, "unresolved": 1, "normalized": 3,
                      "duplicate_values": 1, "contacts_with_duplicates": 2},
            "phone": {"missing": 1, "unresolved": 1, "normalized": 3,
                      "duplicate_values": 1, "contacts_with_duplicates": 3},
        }
        self.assertEqual(profile_contacts(rows), expected)
        self.assertEqual(profile_contacts(reversed(rows)), expected)

    def test_profile_rejects_unexpected_columns(self):
        with self.assertRaises(ValueError):
            profile_contacts([{"email": "a@example.test", "phone": "", "name": "Synthetic"}])

    def test_plan_quarantines_colliding_points_and_preserves_independent_ones(self):
        rows = [
            {"contact_id": "91", "email": "A@EXAMPLE.TEST", "phone": "+56 (9) 1234-5678"},
            {"contact_id": "10", "email": "A@example.test", "phone": "912345678"},
            {"contact_id": "72", "email": "a@example.test", "phone": "+56912345678"},
            {"contact_id": "42", "email": "", "phone": "+12025550138"},
        ]
        expected = {
            "contacts": 4,
            "points": {
                "email": {"eligible": [72], "collisions": [[10, 91]], "unresolved": []},
                "phone": {"eligible": [42], "collisions": [[72, 91]], "unresolved": [10]},
            },
        }
        self.assertEqual(plan_contact_backfill(rows), expected)
        self.assertEqual(plan_contact_backfill(reversed(rows)), expected)
        for contact_id in ("091", "0", "9223372036854775808", "abc"):
            with self.subTest(contact_id=contact_id), self.assertRaises(ValueError):
                plan_contact_backfill(rows + [rows[0] | {"contact_id": contact_id}])
