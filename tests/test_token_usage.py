import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/alpha-squad-coding-craft/scripts/collect_token_usage.py"
spec = importlib.util.spec_from_file_location("usage_collector", SCRIPT)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def usage(thread, response, total, *, turn="turn", root="task", cumulative=None,
          timestamp="2026-09-23T10:00:00Z", components=None,
          cumulative_components=None):
    native_usage = {"total_tokens": total}
    if components is not None:
        native_usage.update(components)
    turn_usage = {"total_tokens": total if cumulative is None else cumulative}
    if components is not None:
        native_cumulative = components if cumulative_components is None else cumulative_components
        for key in ("input_tokens", "output_tokens"):
            if key in native_cumulative:
                turn_usage[key] = native_cumulative[key]
    return {"type": "token_usage_record", "timestamp": timestamp, "payload": {
        "thread_id": thread, "turn_id": turn, "root_turn_id": root,
        "response_id": response, "usage": native_usage,
        "turn_token_usage": turn_usage,
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
        self.assertEqual(result["response_count"], 3)
        self.assertEqual(
            {(item["thread_id"], item["total_tokens"]) for item in result["segments"]},
            {("parent", 100), ("child", 50), ("nested", 20)},
        )
        self.assertNotIn("task", result["segments"])

    def test_duplicate_snapshots_and_archived_copy_not_added(self):
        events = [usage("parent", "one", 10), usage("parent", "two", 20, cumulative=30)]
        self.log("parent", events + [events[-1]])
        self.log("parent", events, folder="archived_sessions")
        self.assertEqual(self.collect()["total_tokens"], 30)

    def test_resumed_child_and_multiple_roots(self):
        self.log("parent", [usage("parent", "p", 10), usage("parent", "p2", 20, turn="t2", root="next")])
        self.log("child", [usage("child", "a", 5), usage("child", "b", 7, turn="t2", root="next")], "parent")
        self.assertEqual(self.collect(1)["total_tokens"], 15)
        result = self.collect(1, ["task", "next"])
        self.assertEqual(result["total_tokens"], 42)
        self.assertEqual(
            {(item["thread_id"], item["turn_id"], item["root_turn_id"])
             for item in result["segments"]},
            {("parent", "turn", "task"), ("parent", "t2", "next"),
             ("child", "turn", "task"), ("child", "t2", "next")},
        )

    def test_missing_child_does_not_return_partial_total(self):
        self.log("parent", [usage("parent", "p", 10)])
        result = self.collect(1)
        self.assertIsNone(result["total_tokens"])
        self.assertIsNone(result["response_count"])
        self.assertEqual(result["segments"], [])

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

    def test_segment_checkpoint_ignores_order_duplicates_and_timestamps(self):
        first = usage("parent", "one", 10, cumulative=10,
                      timestamp="2026-09-23T10:00:02Z")
        second = usage("parent", "two", 20, cumulative=30,
                       timestamp="2026-09-23T10:00:01Z")
        self.log("parent", [second, first, second])
        original = self.collect()
        self.log("parent", [first, second])
        repeated = self.collect()
        self.assertEqual(original["segments"][0]["checkpoint"],
                         repeated["segments"][0]["checkpoint"])
        self.assertEqual(original["segments"][0]["usage_stream_id"],
                         repeated["segments"][0]["usage_stream_id"])
        self.assertEqual(original["segments"][0]["response_count"], 2)

    def test_segment_checkpoint_changes_when_native_usage_grows(self):
        self.log("parent", [usage("parent", "one", 10)])
        first = self.collect()["segments"][0]
        self.log("parent", [usage("parent", "one", 10),
                            usage("parent", "two", 5, cumulative=15)])
        grown = self.collect()["segments"][0]
        self.assertNotEqual(first["checkpoint"], grown["checkpoint"])
        self.assertEqual(first["usage_stream_id"], grown["usage_stream_id"])
        self.assertEqual(grown["response_count"], 2)

    def test_native_components_are_aggregated_without_optional_subsets(self):
        self.log("parent", [
            usage("parent", "one", 10, cumulative=10, components={
                "input_tokens": 7, "output_tokens": 3,
                "cached_input_tokens": 5,
            }),
            usage("parent", "two", 20, cumulative=30, components={
                "input_tokens": 11, "output_tokens": 9,
                "reasoning_output_tokens": 4,
                "optional_metadata": {"message": "must not leak"},
            }, cumulative_components={"input_tokens": 18, "output_tokens": 12}),
        ])
        segment = self.collect()["segments"][0]
        self.assertEqual(segment["native_components"], {
            "status": "available",
            "input_tokens": 18,
            "output_tokens": 12,
            "min_input_tokens": 7,
            "max_input_tokens": 11,
            "checkpoint": collector.digest([
                ("one", 7, 3),
                ("two", 11, 9),
            ]),
        })
        self.assertEqual(segment["checkpoint"], collector.digest([
            ("one", 10),
            ("two", 20),
        ]))
        self.assertNotIn("must not leak", json.dumps(segment))

    def test_legacy_usage_leaves_only_native_components_unavailable(self):
        self.log("parent", [usage("parent", "one", 10)])
        result = self.collect()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_tokens"], 10)
        self.assertEqual(result["segments"][0]["native_components"], {
            "status": "unavailable",
            "reason": "missing native component counts",
        })

    def test_invalid_native_components_do_not_invalidate_trusted_total(self):
        for value in (True, -1, collector.MAX_UINT64 + 1):
            with self.subTest(value=value):
                self.log("parent", [usage("parent", "one", 10, components={
                    "input_tokens": value, "output_tokens": 0,
                }, cumulative_components={"input_tokens": 10, "output_tokens": 0})])
                result = self.collect()
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["total_tokens"], 10)
                self.assertEqual(result["segments"][0]["native_components"], {
                    "status": "unavailable",
                    "reason": "invalid native component counts",
                })

    def test_mismatched_native_components_do_not_invalidate_trusted_total(self):
        self.log("parent", [usage("parent", "one", 10, components={
            "input_tokens": 4, "output_tokens": 5,
        }, cumulative_components={"input_tokens": 10, "output_tokens": 0})])
        result = self.collect()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_tokens"], 10)
        self.assertEqual(result["segments"][0]["native_components"], {
            "status": "unavailable",
            "reason": "native component counts do not match total_tokens",
        })

    def test_missing_native_component_checksum_only_components_unavailable(self):
        event = usage("parent", "one", 10, components={
            "input_tokens": 7, "output_tokens": 3,
        })
        event["payload"]["turn_token_usage"] = {"total_tokens": 10}
        self.log("parent", [event])
        result = self.collect()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_tokens"], 10)
        self.assertEqual(result["segments"][0]["native_components"], {
            "status": "unavailable",
            "reason": "missing or invalid native component checksum",
        })

    def test_native_component_sum_must_match_turn_counters(self):
        self.log("parent", [usage("parent", "one", 10, components={
            "input_tokens": 7, "output_tokens": 3,
        }, cumulative_components={"input_tokens": 8, "output_tokens": 2})])
        result = self.collect()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_tokens"], 10)
        self.assertEqual(result["segments"][0]["native_components"], {
            "status": "unavailable",
            "reason": "response component sums do not match native turn counters",
        })

    def test_conflicting_duplicate_native_components_are_unavailable(self):
        self.log("parent", [
            usage("parent", "one", 10, components={
                "input_tokens": 7, "output_tokens": 3,
            }, cumulative_components={"input_tokens": 10, "output_tokens": 0}),
            usage("parent", "one", 10, components={
                "input_tokens": 6, "output_tokens": 4,
            }, cumulative_components={"input_tokens": 10, "output_tokens": 0}),
        ])
        result = self.collect()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_tokens"], 10)
        self.assertEqual(result["segments"][0]["native_components"], {
            "status": "unavailable",
            "reason": "conflicting duplicate native component counts",
        })

    def test_native_component_checkpoint_ignores_order_and_archived_duplicates(self):
        first = usage("parent", "one", 10, cumulative=10, components={
            "input_tokens": 7, "output_tokens": 3,
        })
        second = usage("parent", "two", 20, cumulative=30, components={
            "input_tokens": 11, "output_tokens": 9,
        }, cumulative_components={"input_tokens": 18, "output_tokens": 12})
        self.log("parent", [second, first, second])
        self.log("parent", [first, second], folder="archived_sessions")
        original = self.collect()["segments"][0]
        self.log("parent", [first, second])
        repeated = self.collect()["segments"][0]
        self.assertEqual(original["native_components"], repeated["native_components"])
        self.assertEqual(original["checkpoint"], repeated["checkpoint"])
        self.assertEqual(original["usage_stream_id"], repeated["usage_stream_id"])

    def test_conflicting_session_parent_identity_fails_closed(self):
        self.log("parent", [usage("parent", "p", 10)])
        child = [usage("child", "c", 5)]
        self.log("child", child, "parent")
        self.log("child", child, "other", folder="archived_sessions")
        result = self.collect(1)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["segments"], [])
        self.assertIn("conflicting session parent identity", result["errors"])

    def test_unhashable_session_parent_identity_fails_closed(self):
        self.log("parent", [usage("parent", "p", 10)], parent=[])
        result = self.collect()
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["segments"], [])
        self.assertIn("invalid session parent identity", result["errors"])

    def test_one_native_turn_cannot_belong_to_multiple_root_turns(self):
        self.log("parent", [
            usage("parent", "one", 5, root="task", cumulative=12),
            usage("parent", "two", 7, root="next", cumulative=12),
        ])
        result = self.collect(roots=["task", "next"])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["segments"], [])
        self.assertIn("native turn belongs to multiple root turns", result["errors"])


if __name__ == "__main__":
    unittest.main()
