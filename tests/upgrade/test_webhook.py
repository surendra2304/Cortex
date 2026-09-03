import unittest, time
from cortex_upgrade.webhook import verify_hmac, verify_timestamp, canonical_json
import hmac, hashlib

class TestWebhook(unittest.TestCase):
    def test_signature(self):
        body=b'{"a":1}'; secret="x"*32
        sig=hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
        self.assertTrue(verify_hmac(body,sig,secret).ok)
        self.assertFalse(verify_hmac(body,sig+"x",secret).ok)
    def test_replay(self):
        self.assertFalse(verify_timestamp(int(time.time())-1000,int(time.time())).ok)

if __name__=="__main__":
    unittest.main()
