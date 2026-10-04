import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/alpha-squad-coding-craft/scripts"
SCRIPT = SCRIPTS / "prepare_laya_scenario.py"
SCHEMA = Path(os.environ.get(
    "LAYA_FEEDBACK_SCHEMA",
    ROOT.parent / "oh-my-laya/contracts/feedback.schema.json",
))
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("laya_scenario", SCRIPT)
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)


def segment(thread, turn, total, count, checkpoint):
    return {
        "thread_id": thread,
        "turn_id": turn,
        "root_turn_id": "root-turn",
        "total_tokens": total,
        "response_count": count,
        "checkpoint": checkpoint,
        "usage_stream_id": producer.canonical_hash([thread, turn]),
    }


def report():
    segments = [
        segment("parent", "parent-turn", 25, 1, "checkpoint:parent"),
        segment("child", "child-turn", 75, 3, "checkpoint:child"),
    ]
    for item in segments:
        item["usage_stream_id"] = "codex-native:" + item["usage_stream_id"]
    return {
        "status": "ok",
        "total_tokens": 100,
        "response_count": 4,
        "root_thread_id": "parent",
        "root_turn_ids": ["root-turn"],
        "segments": segments,
        "source": producer.NATIVE_SOURCE,
        "errors": [],
    }


def native_report():
    value = report()
    value["segments"][0]["native_components"] = {
        "status": "available",
        "input_tokens": 20,
        "output_tokens": 5,
        "min_input_tokens": 20,
        "max_input_tokens": 20,
        "checkpoint": "components:parent",
    }
    value["segments"][1]["native_components"] = {
        "status": "available",
        "input_tokens": 60,
        "output_tokens": 15,
        "min_input_tokens": 15,
        "max_input_tokens": 25,
        "checkpoint": "components:child",
    }
    return value


def bindings():
    return [
        {
            "thread_id": "parent", "turn_id": "parent-turn",
            "root_turn_id": "root-turn", "decision_id": "decision-parent",
            "attempt_ref": "attempt-parent", "configuration_scope_confirmed": True,
        },
        {
            "thread_id": "child", "turn_id": "child-turn",
            "root_turn_id": "root-turn", "decision_id": "decision-child",
            "attempt_ref": "attempt-child", "configuration_scope_confirmed": True,
        },
    ]


def plan():
    return {
        "run_id": "run-1",
        "observed_at": "2026-10-04T12:30:00+08:00",
        "orchestrator": {
            "model": "gpt-example", "reasoning_effort": "high",
            "source": "host", "reference": "host:model-observation:1",
        },
        "meter_identity": "codex-native-token-meter",
        "initial_context_text": "abcd界",
        "stages": [
            {
                "thread_id": "parent", "turn_id": "parent-turn",
                "root_turn_id": "root-turn", "context_text": "abcdefgh",
                "work_output_text": "结果", "passes": 2,
            },
            {
                "thread_id": "child", "turn_id": "child-turn",
                "root_turn_id": "root-turn", "context_text": "abcd界",
                "work_output_text": "done", "passes": 1,
            },
        ],
    }


def native_plan():
    value = plan()
    del value["initial_context_text"]
    value["input_mode"] = producer.NATIVE_INPUT_MODE
    for stage in value["stages"]:
        del stage["context_text"]
        del stage["work_output_text"]
    return value


class LayaScenarioTests(unittest.TestCase):
    def test_native_envelope_derives_numeric_scenario_without_text(self):
        value = native_plan()
        self.assertNotIn("initial_context_text", value)
        self.assertTrue(all(set(stage) == {
            "thread_id", "turn_id", "root_turn_id", "passes",
        } for stage in value["stages"]))

        first = producer.prepare(native_report(), bindings(), value)
        second = producer.prepare(native_report(), list(reversed(bindings())), value)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ok")
        manifest = first["events"][-1]
        self.assertEqual(manifest["payload"]["scenario"], {
            "orchestrator_model": "gpt-example",
            "reasoning_effort": "high",
            "initial_context_tokens": 15,
            "stages": [
                {"context_growth_tokens": 5, "work_output_tokens": 5, "passes": 2},
                {"context_growth_tokens": 10, "work_output_tokens": 15, "passes": 1},
            ],
            "input_source": producer.NATIVE_INPUT_SOURCE,
        })
        self.assertLessEqual(len(producer.NATIVE_INPUT_SOURCE), 512)
        self.assertIn("range-sensitivity scenario", producer.NATIVE_INPUT_SOURCE)
        self.assertIn("explicit hypothetical", producer.NATIVE_INPUT_SOURCE)
        self.assertIn("not initial/final observed context", producer.NATIVE_INPUT_SOURCE)
        self.assertEqual(manifest["payload"]["coverage"]["evidence_refs"], [
            "host:model-observation:1", "checkpoint:parent", "checkpoint:child",
            "components:parent", "components:child",
        ])
        self.assertNotIn("context_text", json.dumps(first))
        self.assertNotIn("work_output_text", json.dumps(first))

    def test_native_usage_event_ids_match_usage_producer(self):
        scenario = producer.prepare(native_report(), bindings(), native_plan())
        usage = producer.make_event
        segments = producer.checked_segments(native_report())
        expected = [
            usage(binding, segments[tuple(binding[field] for field in (
                "thread_id", "turn_id", "root_turn_id"))])["event_id"]
            for binding in bindings()
        ]
        self.assertEqual([event["event_id"] for event in scenario["events"][:-1]],
                         expected)

    def test_native_stage_order_controls_events_and_derived_stages(self):
        value = native_plan()
        value["stages"].reverse()
        result = producer.prepare(native_report(), bindings(), value)
        self.assertEqual(result["status"], "ok")
        self.assertEqual([event["decision_id"] for event in result["events"][:-1]],
                         ["decision-child", "decision-parent"])
        self.assertEqual(result["events"][-1]["payload"]["scenario"]["stages"], [
            {"context_growth_tokens": 10, "work_output_tokens": 15, "passes": 1},
            {"context_growth_tokens": 5, "work_output_tokens": 5, "passes": 2},
        ])

    def test_native_manifest_id_is_stable_and_covers_component_checkpoint(self):
        first = producer.prepare(native_report(), bindings(), native_plan())
        repeated = producer.prepare(native_report(), bindings(), native_plan())
        changed_report = native_report()
        changed_report["segments"][0]["native_components"]["checkpoint"] = (
            "components:parent:new")
        changed = producer.prepare(changed_report, bindings(), native_plan())
        self.assertEqual(first["events"][-1]["event_id"],
                         repeated["events"][-1]["event_id"])
        self.assertNotEqual(first["events"][-1]["event_id"],
                            changed["events"][-1]["event_id"])
        self.assertEqual([event["event_id"] for event in first["events"][:-1]],
                         [event["event_id"] for event in changed["events"][:-1]])

    def test_native_components_must_be_available_and_checksummed(self):
        cases = []
        absent = native_report()
        del absent["segments"][0]["native_components"]
        cases.append(absent)
        unavailable = native_report()
        unavailable["segments"][0]["native_components"] = {
            "status": "unavailable", "reason": "legacy",
        }
        cases.append(unavailable)
        for checkpoint in ("", "x" * 513, None):
            checksumless = native_report()
            checksumless["segments"][0]["native_components"]["checkpoint"] = checkpoint
            cases.append(checksumless)
        for value in cases:
            with self.subTest(value=value):
                result = producer.prepare(value, bindings(), native_plan())
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["events"], [])

    def test_native_counts_reject_fraction_bool_overflow_sums_and_bounds(self):
        cases = []
        for field, invalid in (("input_tokens", 20.0), ("output_tokens", True),
                               ("min_input_tokens", 1.5),
                               ("max_input_tokens", False)):
            value = native_report()
            value["segments"][0]["native_components"][field] = invalid
            cases.append(value)
        inconsistent_sum = native_report()
        inconsistent_sum["segments"][0]["native_components"]["output_tokens"] = 4
        cases.append(inconsistent_sum)
        reversed_bounds = native_report()
        reversed_bounds["segments"][1]["native_components"]["min_input_tokens"] = 26
        cases.append(reversed_bounds)
        excessive_max = native_report()
        excessive_max["segments"][1]["native_components"]["max_input_tokens"] = 61
        cases.append(excessive_max)
        implausible_count = native_report()
        implausible_count["segments"][1]["native_components"]["min_input_tokens"] = 21
        cases.append(implausible_count)
        overflow = native_report()
        component = overflow["segments"][1]["native_components"]
        component["output_tokens"] = producer.MAX_SCENARIO_VALUE + 1
        overflow["segments"][1]["total_tokens"] = (
            component["input_tokens"] + component["output_tokens"])
        overflow["total_tokens"] = sum(
            segment["total_tokens"] for segment in overflow["segments"])
        cases.append(overflow)

        for value in cases:
            with self.subTest(value=value):
                result = producer.prepare(value, bindings(), native_plan())
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["events"], [])

    def test_native_single_response_requires_exact_extrema(self):
        for minimum, maximum in ((0, 20), (19, 20), (20, 21)):
            value = native_report()
            component = value["segments"][0]["native_components"]
            component["min_input_tokens"] = minimum
            component["max_input_tokens"] = maximum
            with self.subTest(minimum=minimum, maximum=maximum):
                result = producer.prepare(value, bindings(), native_plan())
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["events"], [])

    def test_native_multi_response_accepts_zero_and_nonmonotonic_extrema(self):
        value = native_report()
        component = value["segments"][1]["native_components"]
        component["input_tokens"] = 15
        component["output_tokens"] = 60
        component["min_input_tokens"] = 0
        component["max_input_tokens"] = 10
        result = producer.prepare(value, bindings(), native_plan())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["events"][-1]["payload"]["scenario"], {
            "orchestrator_model": "gpt-example",
            "reasoning_effort": "high",
            "initial_context_tokens": 0,
            "stages": [
                {"context_growth_tokens": 20, "work_output_tokens": 5, "passes": 2},
                {"context_growth_tokens": 10, "work_output_tokens": 60, "passes": 1},
            ],
            "input_source": producer.NATIVE_INPUT_SOURCE,
        })

    def test_valid_plan_emits_schema_valid_stable_events_without_raw_text(self):
        first = producer.prepare(report(), bindings(), plan())
        second = producer.prepare(report(), bindings(), plan())
        reversed_bindings = producer.prepare(report(), list(reversed(bindings())), plan())
        self.assertEqual(first, second)
        self.assertEqual(first, reversed_bindings)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["unbound_segments"], 0)
        self.assertEqual([event["kind"] for event in first["events"]],
                         ["usage", "usage", "run_manifest"])
        encoded = json.dumps(first, ensure_ascii=False)
        for raw_text in ("abcd界", "abcdefgh", "结果"):
            self.assertNotIn(raw_text, encoded)

        manifest = first["events"][-1]
        self.assertEqual(manifest["decision_id"], "decision-parent")
        self.assertEqual(manifest["attempt_ref"], "attempt-parent")
        self.assertEqual(manifest["payload"]["mode"], "laya")
        self.assertEqual(manifest["payload"]["coverage"], {
            "status": "partial",
            "evidence_refs": [
                "host:model-observation:1", "checkpoint:parent", "checkpoint:child",
            ],
        })
        self.assertEqual(manifest["payload"]["scenario"], {
            "orchestrator_model": "gpt-example",
            "reasoning_effort": "high",
            "initial_context_tokens": 2,
            "stages": [
                {"context_growth_tokens": 2, "work_output_tokens": 2, "passes": 2},
                {"context_growth_tokens": 2, "work_output_tokens": 1, "passes": 1},
            ],
            "input_source": producer.INPUT_SOURCE,
        })
        usage_ids = [event["event_id"] for event in first["events"][:-1]]
        self.assertEqual(
            manifest["payload"]["terminal_checkpoint"],
            "events:" + producer.canonical_hash(sorted(usage_ids)),
        )
        self.assertLessEqual(len(json.dumps(
            manifest, ensure_ascii=False, separators=(",", ":"),
            sort_keys=True).encode("utf-8")), producer.MAX_MANIFEST_BYTES)

    def test_malformed_boolean_oversize_and_null_inputs_fail_closed(self):
        malformed = []
        boolean_passes = plan()
        boolean_passes["stages"][0]["passes"] = True
        malformed.append(boolean_passes)
        too_many_stages = plan()
        too_many_stages["stages"] = [
            copy.deepcopy(too_many_stages["stages"][0]) for unused in range(129)]
        malformed.append(too_many_stages)
        oversized_text = plan()
        oversized_text["initial_context_text"] = "x" * (producer.MAX_TEXT_BYTES + 1)
        malformed.append(oversized_text)
        oversized_model = plan()
        oversized_model["orchestrator"]["model"] = "m" * 257
        malformed.append(oversized_model)
        oversized_reference = plan()
        oversized_reference["orchestrator"]["reference"] = "r" * 513
        malformed.append(oversized_reference)
        null_model = plan()
        null_model["orchestrator"]["model"] = None
        malformed.append(null_model)
        null_effort = plan()
        null_effort["orchestrator"]["reasoning_effort"] = None
        malformed.append(null_effort)
        null_context = plan()
        null_context["stages"][0]["context_text"] = None
        malformed.append(null_context)
        no_timezone = plan()
        no_timezone["observed_at"] = "2026-10-04T12:30:00"
        malformed.append(no_timezone)
        for timestamp in ("2026-10-04T12:30:00+00:99", "2026-10-04T12:30:00+00:60",
                          "20261004T123000Z", "2026-W40-7T12:30:00Z", "2026-10-04x12:30:00Z"):
            invalid_time = plan()
            invalid_time["observed_at"] = timestamp
            malformed.append(invalid_time)
        wrong_source = plan()
        wrong_source["orchestrator"]["source"] = "agent"
        malformed.append(wrong_source)

        for value in malformed:
            with self.subTest(value=value):
                result = producer.prepare(report(), bindings(), value)
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["events"], [])

    def test_omitted_extra_and_duplicate_stage_mappings_fail_closed(self):
        omitted = plan()
        omitted["stages"] = omitted["stages"][:1]
        extra = plan()
        extra["stages"].append({
            "thread_id": "extra", "turn_id": "extra-turn",
            "root_turn_id": "root-turn", "context_text": "x",
            "work_output_text": "y", "passes": 1,
        })
        duplicate = plan()
        duplicate["stages"][1]["thread_id"] = "parent"
        duplicate["stages"][1]["turn_id"] = "parent-turn"
        unmatched = plan()
        unmatched["stages"][1]["turn_id"] = "unknown-turn"
        cases = (
            (bindings(), omitted),
            (bindings(), extra),
            (bindings(), duplicate),
            (bindings(), unmatched),
        )
        for bound, value in cases:
            with self.subTest(plan=value):
                result = producer.prepare(report(), bound, value)
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["events"], [])

    def test_unbound_native_segment_is_reported_and_excluded(self):
        child_binding = bindings()[1:]
        child_plan = plan()
        child_plan["stages"] = child_plan["stages"][1:]
        result = producer.prepare(report(), child_binding, child_plan)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["unbound_segments"], 1)
        self.assertEqual([event["kind"] for event in result["events"]],
                         ["usage", "run_manifest"])
        manifest = result["events"][-1]
        self.assertEqual(manifest["decision_id"], "decision-child")
        self.assertEqual(manifest["payload"]["coverage"]["status"], "partial")
        self.assertEqual(manifest["payload"]["segments"], [{
            "decision_id": "decision-child",
            "attempt_ref": "attempt-child",
            "usage_event_id": result["events"][0]["event_id"],
        }])

    @unittest.skipUnless(SCHEMA.exists(), "live Laya feedback schema is unavailable")
    def test_events_validate_against_live_schema(self):
        validator = jsonschema.Draft202012Validator(
            json.loads(SCHEMA.read_text(encoding="utf-8")),
            format_checker=jsonschema.FormatChecker(),
        )
        result = producer.prepare(report(), bindings(), plan())
        self.assertEqual(result["status"], "ok")
        for event in result["events"]:
            validator.validate(event)


if __name__ == "__main__":
    unittest.main()
