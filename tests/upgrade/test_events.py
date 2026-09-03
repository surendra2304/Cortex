import unittest
from datetime import UTC, datetime, timedelta
from cortex_upgrade.event_ingestion import EventNormalizer, EventRejected, EventDedupeStore

class TestEvents(unittest.IsolatedAsyncioTestCase):
    def event(self, ts):
        return {"event_id":"e1","tenant_id":"t1","site_id":"s1","type":"page_view",
                "occurred_at":ts.isoformat(),"consent":{"analytics":True},"data":{"path":"/"}}
    def test_normalize(self):
        e=EventNormalizer().normalize(self.event(datetime.now(UTC)))
        self.assertEqual(e.tenant_id,"t1")
        self.assertEqual(e.occurred_at.tzinfo,UTC)
    def test_future_rejected(self):
        with self.assertRaises(EventRejected):
            EventNormalizer().normalize(self.event(datetime.now(UTC)+timedelta(seconds=2)))
    async def test_dedupe(self):
        d=EventDedupeStore()
        self.assertTrue(await d.claim("t","e"))
        self.assertFalse(await d.claim("t","e"))

if __name__ == "__main__":
    unittest.main()
