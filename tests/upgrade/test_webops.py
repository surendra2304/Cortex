import unittest
from cortex_upgrade.webops import normalize_url, detect_rage_clicks, detect_exit_intent, p99

class TestWebOps(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_url("HTTPS://EXAMPLE.COM"),"https://example.com/")
    def test_rage_click(self):
        self.assertTrue(detect_rage_clicks([100,500,1200,1900]))
    def test_exit(self):
        self.assertTrue(detect_exit_intent(790,800))
    def test_p99(self):
        self.assertEqual(p99([1,2,3,4]),4)

if __name__=="__main__":
    unittest.main()
