import unittest

from cortex_upgrade.models import FailureKind
from cortex_upgrade.provider import Provider


class TestProvider(unittest.IsolatedAsyncioTestCase):
    async def test_timeout(self):
        async def f(**kwargs):
            raise TimeoutError()

        result = await Provider("p", f).call()
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure"], FailureKind.TIMEOUT.value)

    async def test_success(self):
        async def f(**kwargs):
            return 7

        result = await Provider("p", f).call()
        self.assertTrue(result["ok"])
        self.assertEqual(result["output"], 7)


if __name__ == "__main__":
    unittest.main()
