import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/alpha-squad-coding-craft/scripts/prepare_laya_usage.py"
spec = importlib.util.spec_from_file_location("laya_usage", SCRIPT)
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)


def segment(thread, turn, root, total, count, checkpoint):
    return {
        "thread_id": thread,
        "turn_id": turn,
        "root_turn_id": root,
        "total_tokens": total,
        "response_count": count,
        "checkpoint": checkpoint,
        "usage_stream_id": producer.expected_stream_id(thread, turn),
    }


def report():
    segments = [
        segment("parent", "root-turn", "root", 10, 1, "sha256:parent"),
        segment("child", "child-turn", "root", 40, 2, "sha256:child"),
    ]
    return {
        "status": "ok",
        "total_tokens": 50,
        "response_count": 3,
        "root_thread_id": "parent",
        "root_turn_ids": ["root"],
        "segments": segments,
        "source": producer.NATIVE_SOURCE,
        "errors": [],
    }


def binding(thread, turn, attempt="attempt-1", decision="decision-1"):
    return {
        "thread_id": thread,
        "turn_id": turn,
        "root_turn_id": "root",
        "decision_id": decision,
        "attempt_ref": attempt,
        "configuration_scope_confirmed": True,
    }


class LayaUsageTests(unittest.TestCase):
    def test_exact_confirmed_segment_produces_attempt_event(self):
        result = producer.prepare(report(), [binding("child", "child-turn")])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["unbound_segments"], 1)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual(event["kind"], "usage")
        self.assertEqual(event["source"], {
            "host": "codex", "role": "orchestrator", "actor_type": "agent"})
        self.assertEqual(event["payload"], {
            "total_tokens": 40,
            "source": producer.NATIVE_SOURCE,
            "source_verified": True,
            "scope": "attempt",
            "checkpoint": "sha256:child",
            "parent_scope": None,
            "overlap_status": "non_overlapping",
            "aggregation": "cumulative",
            "usage_stream_id": report()["segments"][1]["usage_stream_id"],
            "source_sequence": 2,
        })

    def test_reruns_and_binding_order_have_stable_event_ids(self):
        bindings = [binding("parent", "root-turn", "attempt-parent", "decision-parent"),
                    binding("child", "child-turn", "attempt-child", "decision-child")]
        first = producer.prepare(report(), bindings)
        second = producer.prepare(report(), list(reversed(bindings)))
        self.assertEqual(first, second)

        grown = report()
        grown["segments"][1]["total_tokens"] = 45
        grown["segments"][1]["response_count"] = 3
        grown["segments"][1]["checkpoint"] = "sha256:child-grown"
        grown["total_tokens"] = 55
        grown["response_count"] = 4
        changed = producer.prepare(grown, bindings)
        first_ids = {event["attempt_ref"]: event["event_id"] for event in first["events"]}
        changed_ids = {event["attempt_ref"]: event["event_id"] for event in changed["events"]}
        self.assertEqual(first_ids["attempt-parent"], changed_ids["attempt-parent"])
        self.assertNotEqual(first_ids["attempt-child"], changed_ids["attempt-child"])

    def test_duplicate_or_mixed_bindings_fail_closed(self):
        duplicate = binding("child", "child-turn")
        cases = [
            [duplicate, copy.deepcopy(duplicate)],
            [binding("parent", "root-turn", "same"),
             binding("child", "child-turn", "same")],
        ]
        for bindings in cases:
            with self.subTest(bindings=bindings):
                result = producer.prepare(report(), bindings)
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["events"], [])

    def test_unknown_unconfirmed_and_incomplete_bindings_fail_closed(self):
        unknown = binding("missing", "turn")
        unconfirmed = binding("child", "child-turn")
        unconfirmed["configuration_scope_confirmed"] = False
        incomplete = binding("child", "child-turn")
        del incomplete["decision_id"]
        for value in ([unknown], [unconfirmed], [incomplete]):
            with self.subTest(binding=value):
                self.assertEqual(producer.prepare(report(), value)["events"], [])

    def test_unavailable_or_malformed_report_cannot_produce_events(self):
        unavailable = report()
        unavailable["status"] = "unavailable"
        malformed_total = report()
        malformed_total["segments"][1]["total_tokens"] = True
        wrong_sum = report()
        wrong_sum["total_tokens"] = 51
        duplicate_stream = report()
        duplicate_stream["segments"][1]["usage_stream_id"] = duplicate_stream["segments"][0]["usage_stream_id"]
        wrong_roots = report()
        wrong_roots["root_turn_ids"] = ["other"]
        wrong_source = report()
        wrong_source["source"] = "estimated usage"
        missing_root = report()
        del missing_root["root_thread_id"]
        overflow = report()
        overflow["segments"][1]["total_tokens"] = producer.MAX_UINT64 + 1
        overflow["total_tokens"] = producer.MAX_UINT64 + 11
        for value in (unavailable, malformed_total, wrong_sum,
                      duplicate_stream, wrong_roots, wrong_source,
                      missing_root, overflow):
            with self.subTest(report=value):
                result = producer.prepare(value, [binding("child", "child-turn")])
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["events"], [])

    def test_cli_emits_json_and_exit_status(self):
        with TemporaryDirectory() as folder:
            report_path = Path(folder) / "report.json"
            bindings_path = Path(folder) / "bindings.json"
            report_path.write_text(json.dumps(report()), encoding="utf-8")
            bindings_path.write_text(json.dumps([
                binding("child", "child-turn")]), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--report", str(report_path),
                 "--bindings", str(bindings_path)],
                capture_output=True, check=False, text=True,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["unbound_segments"], 1)


if __name__ == "__main__":
    unittest.main()
