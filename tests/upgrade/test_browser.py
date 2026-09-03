import unittest
from unittest.mock import patch
from cortex_upgrade.browser import BrowserGuard, BrowserPolicy, BrowserSession
from cortex_upgrade.policy import PolicyDenied

class TestBrowser(unittest.IsolatedAsyncioTestCase):
    @patch("cortex_upgrade.policy.socket.getaddrinfo", return_value=[(2,1,6,"",("93.184.216.34",0))])
    async def test_allowlisted_navigation(self,_):
        s=BrowserSession(BrowserGuard(BrowserPolicy(frozenset({"example.com"}))))
        await s.navigate("https://example.com/")
        self.assertEqual(len(s.guard.history),1)
    @patch("cortex_upgrade.policy.socket.getaddrinfo", return_value=[(2,1,6,"",("93.184.216.34",0))])
    async def test_unapproved_host(self,_):
        s=BrowserSession(BrowserGuard(BrowserPolicy(frozenset({"example.com"}))))
        with self.assertRaises(PolicyDenied):
            await s.navigate("https://other.com/")

if __name__ == "__main__":
    unittest.main()
