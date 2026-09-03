import unittest
from uuid import uuid4
from cortex_upgrade.models import Principal, ToolCall, SideEffect, FailureKind
from cortex_upgrade.toolbus import ToolBus, ToolRegistry, ToolSpec
from cortex_upgrade.policy import PolicyEngine

async def handler(args): return {"id":args["id"]}
async def verify(args,out): return out["id"] == args["id"]

class TestToolBus(unittest.IsolatedAsyncioTestCase):
    async def test_verified_tool(self):
        r=ToolRegistry()
        r.register(ToolSpec("read","1",SideEffect.READ,frozenset({"read"}),handler,verify))
        bus=ToolBus(r,PolicyEngine())
        p=Principal("p","t",scopes=frozenset({"read"}))
        c=ToolCall(uuid4(),"read",{"id":7},SideEffect.READ,frozenset({"read"}),False)
        result=await bus.execute(p,c)
        self.assertTrue(result.ok); self.assertTrue(result.verified)
    async def test_denied_scope(self):
        r=ToolRegistry()
        r.register(ToolSpec("read","1",SideEffect.READ,frozenset({"read"}),handler,verify))
        bus=ToolBus(r,PolicyEngine())
        p=Principal("p","t",scopes=frozenset())
        c=ToolCall(uuid4(),"read",{"id":7},SideEffect.READ,frozenset({"read"}),False)
        result=await bus.execute(p,c)
        self.assertFalse(result.ok); self.assertEqual(result.failure,FailureKind.POLICY)

if __name__ == "__main__":
    unittest.main()
