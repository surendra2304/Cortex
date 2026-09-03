import unittest
from cortex_upgrade.provider import Provider
from cortex_upgrade.models import FailureKind
from cortex_upgrade.circuit import CircuitBreaker

class TestProvider(unittest.IsolatedAsyncioTestCase):
    async def test_timeout(self):
        async def f(**kwargs): raise TimeoutError()
        r=await Provider("p",f).call()
        self.assertFalse(r["ok"]); self.assertEqual(r["failure"],FailureKind.TIMEOUT.value)
    async def test_success(self):
        async def f(**kwargs): return 7
        r=await Provider("p",f).call()
        self.assertTrue(r["ok"]); self.assertEqual(r["output"],7)

if __name__=="__main__":
    unittest.main()
