import unittest
from unittest.mock import patch
from cortex_upgrade.memory import ScopedMemory
from cortex_upgrade.memora_client import memora_client

class TestMemory(unittest.IsolatedAsyncioTestCase):
    async def test_scope_isolation(self):
        m=ScopedMemory()
        with patch.object(memora_client, "record_fact", return_value={"id": "cloud-memory"}):
            await m.add("t1","enterprise lead",user_id="u1")
            await m.add("t2","enterprise lead",user_id="u2")
        self.assertEqual(len(await m.search("t1","enterprise",user_id="u1")),1)
        self.assertEqual(len(await m.search("t1","enterprise",user_id="u2")),0)

    async def test_failed_cloud_write_is_not_cached_as_accepted_memory(self):
        m = ScopedMemory()
        with patch.object(memora_client, "record_fact", return_value={"status": "local_only", "cloud": False}):
            with self.assertRaisesRegex(RuntimeError, "not stored in Memora Cloud"):
                await m.add("t1", "unshared memory", user_id="u1")
        self.assertEqual(await m.search("t1", "unshared", user_id="u1"), [])

    async def test_scope_required(self):
        m = ScopedMemory()
        with self.assertRaises(ValueError):
            await m.add("t1","x")

if __name__=="__main__":
    unittest.main()
