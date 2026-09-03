import unittest
from cortex_upgrade.audit import AuditLog

class TestAudit(unittest.IsolatedAsyncioTestCase):
    async def test_secret_redaction_and_scope(self):
        a=AuditLog()
        await a.append("t1","p1","r","tool.call","x","ok",metadata={"api_key":"secret","value":1})
        await a.append("t2","p2","r","tool.call","y","ok")
        rows=await a.query("t1")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].metadata["api_key"],"[REDACTED]")

if __name__=="__main__":
    unittest.main()
