import unittest
from cortex_upgrade.idempotency import IdempotencyStore, IdempotencyConflict

class TestIdempotency(unittest.IsolatedAsyncioTestCase):
    async def test_replay(self):
        s=IdempotencyStore(); p={"x":1}
        self.assertIsNone(await s.begin("k",p))
        await s.commit("k",p,200,{"ok":1})
        self.assertEqual((await s.begin("k",p)).body,{"ok":1})
    async def test_conflict(self):
        s=IdempotencyStore(); await s.commit("k",{"x":1},200,{})
        with self.assertRaises(IdempotencyConflict): await s.begin("k",{"x":2})

if __name__ == "__main__":
    unittest.main()
