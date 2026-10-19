import unittest
from unittest.mock import patch
import experiment_wait as w


class WaitTests(unittest.TestCase):
    def test_exited_is_not_experiment_success(self):
        with patch.object(w, "process_identity", return_value=None):
            result = w.wait_for_processes({123: "start"})
        self.assertEqual(result["status"], "processes_exited")
        self.assertIsNone(result["experiment_success"])

    def test_pid_reuse_is_not_old_job(self):
        with patch.object(w, "process_identity", return_value="new"):
            self.assertEqual(w.wait_for_processes({123: "old"})["pending_pids"], [])

    def test_timeout_keeps_job_pending_without_touching_it(self):
        with patch.object(w, "process_identity", return_value="same"), \
                patch.object(w.time, "monotonic", side_effect=[0, 0, 600]), \
                patch.object(w.time, "sleep") as sleep:
            result = w.wait_for_processes({123: "same"}, timeout=600)
        self.assertEqual(result["status"], "pending")
        sleep.assert_called_once_with(15)

    def test_waits_for_all_jobs(self):
        with patch.object(w, "process_identity", side_effect=[None, "live", None, None]), \
                patch.object(w.time, "sleep"):
            result = w.wait_for_processes({123: "done", 456: "live"})
        self.assertEqual(result["status"], "processes_exited")

    def test_invalid_arguments(self):
        for identities, timeout, interval in [({}, 1, 1), ({1: "x"}, 0, 1), ({1: "x"}, 1, 0)]:
            with self.assertRaises(ValueError):
                w.wait_for_processes(identities, timeout, interval)


if __name__ == "__main__":
    unittest.main()
