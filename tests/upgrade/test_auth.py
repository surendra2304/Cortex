import unittest
from datetime import UTC, datetime, timedelta
from cortex_upgrade.auth import CredentialManager, validate_production_secrets

class TestAuth(unittest.TestCase):
    def test_round_trip(self):
        manager = CredentialManager()
        secret = "cortex_" + "x"*40
        record = manager.create("c1","p1","t1",secret,1)
        self.assertTrue(manager.verify(secret, record))
        self.assertFalse(manager.verify(secret+"x", record))

    def test_header(self):
        self.assertEqual(CredentialManager.parse_header("Bearer abc"), "abc")
        self.assertEqual(CredentialManager.parse_header("abc"), "abc")

    def test_prod_guard(self):
        with self.assertRaises(RuntimeError):
            validate_production_secrets("production", {"CORTEX_API_KEY":"cortex_api"})

if __name__ == "__main__":
    unittest.main()
