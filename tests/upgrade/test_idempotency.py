import unittest

from cortex_upgrade.idempotency import IdempotencyConflict, IdempotencyStore


class TestIdempotency(unittest.IsolatedAsyncioTestCase):
    async def test_replay(self):
        store = IdempotencyStore()
        payload = {"x": 1}
        self.assertIsNone(await store.begin("k", payload))
        await store.commit("k", payload, 200, {"ok": 1})
        self.assertEqual((await store.begin("k", payload)).body, {"ok": 1})

    async def test_conflict(self):
        store = IdempotencyStore()
        await store.commit("k", {"x": 1}, 200, {})
        with self.assertRaises(IdempotencyConflict):
            await store.begin("k", {"x": 2})


if __name__ == "__main__":
    unittest.main()
