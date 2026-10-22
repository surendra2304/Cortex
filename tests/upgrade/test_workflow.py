import unittest

from cortex_upgrade.models import JobState
from cortex_upgrade.workflow import WorkflowConflict, WorkflowStateMachine


class TestWorkflow(unittest.IsolatedAsyncioTestCase):
    async def test_versioning(self):
        sm = WorkflowStateMachine()
        q = await sm.transition(0, JobState.QUEUED)
        self.assertEqual(q.version, 1)
        with self.assertRaises(WorkflowConflict):
            await sm.transition(0, JobState.RUNNING)


if __name__ == "__main__":
    unittest.main()
