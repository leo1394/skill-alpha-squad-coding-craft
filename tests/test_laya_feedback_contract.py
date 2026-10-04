import copy
import json
from pathlib import Path
import re
import unittest

import jsonschema


REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "skills/alpha-squad-coding-craft/references/laya-feedback.md"
)


def load_schema():
    text = REFERENCE.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- laya-feedback-schema:start -->\s*```json\s*(.*?)\s*```\s*"
        r"<!-- laya-feedback-schema:end -->",
        text,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("portable Laya feedback schema block is missing")
    schema = json.loads(match.group(1))
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def observation(source, verified=False):
    return {
        "source": source,
        "verified": verified,
        "observed_at": "2026-09-25T10:00:00Z",
        "reference": "ref:1",
    }


def assignment_event():
    pair = {
        "model": "model-a",
        "reasoning_effort": "high",
        "model_observation": observation("laya"),
    }
    return {
        "protocol_version": 1,
        "event_id": "event-1",
        "decision_id": "decision-1",
        "attempt_ref": "attempt-1",
        "kind": "assignment",
        "source": {"host": "codex", "role": "orchestrator", "actor_type": "agent"},
        "payload": {
            "recommended": pair,
            "selected": None,
            "requested": None,
            "effective": None,
            "reason": "No spawn has occurred",
            "evidence_refs": [],
        },
    }


def score(phase="initial"):
    value = {
        "rubric_version": "laya-feedback-v1",
        "dimension": "outcome_quality",
        "value": None,
        "reason": "Evidence is incomplete",
        "evidence_refs": [],
        "phase": phase,
        "source_sequence": 1,
        "observed_at": "2026-09-25T10:01:00Z",
    }
    if phase == "revision":
        value["supersedes_event_id"] = "event-previous"
    return value


class LayaFeedbackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = jsonschema.Draft202012Validator(load_schema())

    def assert_valid(self, event):
        self.validator.validate(event)

    def assert_invalid(self, event):
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(event)

    def test_unknown_effective_assignment_is_null(self):
        self.assert_valid(assignment_event())

    def test_effective_assignment_requires_verified_host_observation(self):
        event = assignment_event()
        event["payload"]["effective"] = {
            "model": "model-a",
            "reasoning_effort": "high",
            "model_observation": observation("spawn_request"),
        }
        self.assert_invalid(event)

        event["payload"]["effective"]["model_observation"] = observation("host", True)
        self.assert_valid(event)

    def test_requested_cannot_stand_in_for_unverified_effective(self):
        event = assignment_event()
        requested = {
            "model": "model-a",
            "reasoning_effort": "high",
            "model_observation": observation("spawn_request"),
        }
        event["payload"]["requested"] = requested
        event["payload"]["effective"] = copy.deepcopy(requested)
        self.assert_invalid(event)

    def test_score_domain_and_revision_chain(self):
        event = assignment_event()
        event["kind"] = "review"
        event["source"]["role"] = "reviewer"
        event["payload"] = {"scores": [score()]}
        self.assert_valid(event)

        event["payload"]["scores"][0]["value"] = 3
        self.assert_invalid(event)

        event["payload"]["scores"] = [score("revision")]
        self.assert_valid(event)
        del event["payload"]["scores"][0]["supersedes_event_id"]
        self.assert_invalid(event)

    def test_envelope_rejects_unknown_fields_and_actor_types(self):
        event = assignment_event()
        event["unexpected"] = True
        self.assert_invalid(event)
        del event["unexpected"]
        event["source"]["actor_type"] = "human"
        self.assert_invalid(event)


if __name__ == "__main__":
    unittest.main()
