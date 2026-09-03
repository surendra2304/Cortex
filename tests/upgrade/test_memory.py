import unittest
from cortex_upgrade.memory import ScopedMemory

class TestMemory(unittest.IsolatedAsyncioTestCase):
    async def test_scope_isolation(self):
        m=ScopedMemory()
        await m.add("t1","enterprise lead",user_id="u1")
        await m.add("t2","enterprise lead",user_id="u2")
        self.assertEqual(len(await m.search("t1","enterprise",user_id="u1")),1)
        self.assertEqual(len(await m.search("t1","enterprise",user_id="u2")),0)

    async def test_scope_required(self):
        m = ScopedMemory()
        with self.assertRaises(ValueError):
            await m.add("t1","x")

if __name__=="__main__":
    unittest.main()
