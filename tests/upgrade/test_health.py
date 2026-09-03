import unittest
from cortex_upgrade.health import Readiness

class TestHealth(unittest.IsolatedAsyncioTestCase):
    async def test_ready(self):
        async def ok(): return True
        good,rows=await Readiness({"db":ok}).probe()
        self.assertTrue(good); self.assertTrue(rows[0].ok)

    async def test_failure(self):
        async def bad(): raise RuntimeError("down")
        good,rows=await Readiness({"db":bad}).probe()
        self.assertFalse(good); self.assertFalse(rows[0].ok)

if __name__=="__main__":
    unittest.main()
