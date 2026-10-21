import unittest

from cortex_upgrade.health import Readiness


class TestHealth(unittest.IsolatedAsyncioTestCase):
    async def test_ready(self):
        async def ok():
            return True

        good, rows = await Readiness({"db": ok}).probe()
        self.assertTrue(good)
        self.assertTrue(rows[0].ok)

    async def test_failure(self):
        async def bad():
            raise RuntimeError("down")

        good, rows = await Readiness({"db": bad}).probe()
        self.assertFalse(good)
        self.assertFalse(rows[0].ok)

    async def test_string_false_is_not_healthy(self):
        async def malformed():
            return "false"

        good, rows = await Readiness({"db": malformed}).probe()
        self.assertFalse(good)
        self.assertFalse(rows[0].ok)
        self.assertEqual(rows[0].detail, "invalid result type: str")

    async def test_truthy_integer_is_not_healthy(self):
        async def malformed():
            return 1

        good, rows = await Readiness({"db": malformed}).probe()
        self.assertFalse(good)
        self.assertFalse(rows[0].ok)
        self.assertEqual(rows[0].detail, "invalid result type: int")

    async def test_none_is_not_healthy(self):
        async def malformed():
            return None

        good, rows = await Readiness({"db": malformed}).probe()
        self.assertFalse(good)
        self.assertFalse(rows[0].ok)
        self.assertEqual(rows[0].detail, "invalid result type: NoneType")


if __name__ == "__main__":
    unittest.main()
