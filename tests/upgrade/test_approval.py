import unittest
from uuid import uuid4
from cortex_upgrade.approval import ApprovalQueue
from cortex_upgrade.models import ToolCall, SideEffect

class TestApproval(unittest.IsolatedAsyncioTestCase):
    async def test_approval_lifecycle(self):
        q=ApprovalQueue()
        c=ToolCall(uuid4(),"crm",{},SideEffect.HIGH_IMPACT)
        a=await q.request("t","p",c)
        self.assertFalse(a.approved)
        decided=await q.decide(a.approval_id,"admin",True,"approved")
        self.assertTrue(decided.approved)

if __name__ == "__main__":
    unittest.main()
