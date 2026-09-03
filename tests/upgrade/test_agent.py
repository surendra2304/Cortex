import unittest
from cortex_upgrade.agent_runtime import BoundedAgent
from cortex_upgrade.models import JobState

class TestAgent(unittest.IsolatedAsyncioTestCase):
    async def test_success(self):
        calls=[]
        async def step(i):
            calls.append(i)
            return "done" if i==2 else None
        r=await BoundedAgent(5).run(step)
        self.assertEqual(r.state,JobState.SUCCEEDED)
        self.assertEqual(r.steps,2)
    async def test_exhaustion(self):
        async def step(i): return None
        r=await BoundedAgent(2).run(step)
        self.assertEqual(r.state,JobState.FAILED)

if __name__=="__main__":
    unittest.main()
