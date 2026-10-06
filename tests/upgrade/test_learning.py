import unittest

from cortex_upgrade.learning import StrategyLearner


class TestLearning(unittest.TestCase):
    def test_min_sample_guard(self):
        learner = StrategyLearner(min_samples=3)
        learner.observe("s", True)
        learner.observe("s", True)
        self.assertEqual(learner.disposition("s"), "hold")
        learner.observe("s", True)
        self.assertEqual(learner.disposition("s"), "promote")


if __name__ == "__main__":
    unittest.main()
