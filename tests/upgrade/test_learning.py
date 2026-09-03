import unittest
from cortex_upgrade.learning import StrategyLearner

class TestLearning(unittest.TestCase):
    def test_min_sample_guard(self):
        l=StrategyLearner(min_samples=3)
        l.observe("s",True); l.observe("s",True)
        self.assertEqual(l.disposition("s"),"hold")
        l.observe("s",True)
        self.assertEqual(l.disposition("s"),"promote")

if __name__=="__main__":
    unittest.main()
