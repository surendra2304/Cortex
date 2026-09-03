import unittest
from unittest.mock import patch
from cortex_upgrade.models import Principal, ToolCall, SideEffect
from cortex_upgrade.policy import PolicyEngine
from uuid import uuid4

class TestPolicy(unittest.TestCase):
    def test_tool_approval(self):
        p = Principal("p","t",scopes=frozenset({"email"}))
        c = ToolCall(uuid4(),"email",{},SideEffect.SENSITIVE,frozenset({"email"}))
        self.assertFalse(PolicyEngine().authorize_tool(p,c,False).allowed)
        self.assertTrue(PolicyEngine().authorize_tool(p,c,True).allowed)

    @patch("cortex_upgrade.policy.socket.getaddrinfo", return_value=[(2,1,6,"",("127.0.0.1",0))])
    def test_private_ip_blocked(self,_):
        self.assertFalse(_safe(PolicyEngine))

def _safe(cls):
    try:
        cls.validate_url("https://example.com")
    except Exception:
        return False
    return True

if __name__ == "__main__":
    unittest.main()
