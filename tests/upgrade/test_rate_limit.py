import unittest
from cortex_upgrade.rate_limit import AtomicSlidingWindow

class TestRateLimit(unittest.IsolatedAsyncioTestCase):
    async def test_limit(self):
        r = AtomicSlidingWindow()
        self.assertTrue((await r.consume("k",2,60)).allowed)
        self.assertTrue((await r.consume("k",2,60)).allowed)
        self.assertFalse((await r.consume("k",2,60)).allowed)

if __name__ == "__main__":
    unittest.main()
