import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/alpha-squad-coding-craft/scripts/collect_token_usage.py"
spec = importlib.util.spec_from_file_location("usage_collector", SCRIPT)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def usage(thread, response, total, *, turn="turn", root="task", cumulative=None):
    return {"type": "token_usage_record", "timestamp": "2026-09-23T10:00:00Z", "payload": {
        "thread_id": thread, "turn_id": turn, "root_turn_id": root,
        "response_id": response, "usage": {"total_tokens": total},
        "turn_token_usage": {"total_tokens": total if cumulative is None else cumulative},
    }}


class TokenUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def log(self, thread, entries, parent=None, folder="sessions"):
        path = self.home / folder / f"{thread}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {"type": "session_meta", "payload": {"id": thread, "source": {
            "subagent": {"thread_spawn": {"parent_thread_id": parent}}
        }}}
        path.write_text("".join(json.dumps(item) + "\n" for item in [meta, *entries]))
        return path

    def collect(self, count=0, roots=None):
        return collector.collect(self.home, "parent", set(roots or ["task"]), count)

    def test_root_children_nested_and_unrelated(self):
        self.log("parent", [usage("parent", "p", 100), usage("parent", "old", 900, root="old")])
        self.log("child", [usage("child", "c", 50)], "parent")
        self.log("nested", [usage("nested", "n", 20)], "child")
        self.log("other", [usage("other", "o", 999)])
        result = self.collect(2)
        self.assertEqual(result["total_tokens"], 170)
        self.assertEqual(result["subagent_tokens"], 70)

    def test_duplicate_snapshots_and_archived_copy_not_added(self):
        events = [usage("parent", "one", 10), usage("parent", "two", 20, cumulative=30)]
        self.log("parent", events + [events[-1]])
        self.log("parent", events, folder="archived_sessions")
        self.assertEqual(self.collect()["total_tokens"], 30)

    def test_resumed_child_and_multiple_roots(self):
        self.log("parent", [usage("parent", "p", 10), usage("parent", "p2", 20, turn="t2", root="next")])
        self.log("child", [usage("child", "a", 5), usage("child", "b", 7, turn="t2", root="next")], "parent")
        self.assertEqual(self.collect(1)["total_tokens"], 15)
        self.assertEqual(self.collect(1, ["task", "next"])["total_tokens"], 42)

    def test_missing_child_does_not_return_partial_total(self):
        self.log("parent", [usage("parent", "p", 10)])
        self.assertIsNone(self.collect(1)["total_tokens"])

    def test_conflicts_and_missing_responses_fail_closed(self):
        self.log("parent", [usage("parent", "p", 10), usage("parent", "p", 11)])
        self.assertEqual(self.collect()["status"], "unavailable")
        self.log("parent", [usage("parent", "p", 10, cumulative=30)])
        self.assertIsNone(self.collect()["total_tokens"])

    def test_invalid_counts_and_legacy_logs_not_estimated(self):
        for value in (None, True, -1, "10"):
            self.log("parent", [usage("parent", "p", value)])
            self.assertIsNone(self.collect()["total_tokens"])
        self.log("parent", [{"type": "event_msg", "payload": {"type": "token_count"}}])
        self.assertIsNone(self.collect()["total_tokens"])

    def test_partial_tail_and_malformed_complete_record(self):
        path = self.log("parent", [usage("parent", "p", 10)])
        with path.open("a") as stream:
            stream.write('{"unfinished"')
        self.assertEqual(self.collect()["total_tokens"], 10)
        with path.open("a") as stream:
            stream.write("\n")
        self.assertIsNone(self.collect()["total_tokens"])


if __name__ == "__main__":
    unittest.main()
