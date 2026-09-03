import unittest, tempfile
from pathlib import Path
from cortex_upgrade.persistence import DurableStore

class TestPersistence(unittest.TestCase):
    def test_job_checksum_and_outbox(self):
        with tempfile.TemporaryDirectory() as d:
            s=DurableStore(Path(d)/"c.db")
            self.assertTrue(s.save_job("j","t","p","running",1,{"x":1},"now"))
            self.assertEqual(s.get_job("j")["payload"],{"x":1})
            self.assertTrue(s.append_outbox("e","t","forecast.completed",{"id":"j"}))
            self.assertEqual(len(s.pending_outbox()),1)
            self.assertTrue(s.mark_outbox_delivered("e"))
            self.assertEqual(s.pending_outbox(),[])

if __name__=="__main__":
    unittest.main()
