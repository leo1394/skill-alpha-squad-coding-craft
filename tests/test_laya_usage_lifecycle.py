import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from tempfile import TemporaryDirectory
import unittest

from test_token_usage import usage


SCRIPT = Path(__file__).resolve().parents[1] / "skills/alpha-squad-coding-craft/scripts/laya_usage_lifecycle.py"


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.ledger = self.home / "ledger.json"
        self.run_cli("init", "--codex-home", self.home, "--root-thread", "parent", "--root-turn", "task")

    def run_cli(self, *arguments, code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), "--ledger", str(self.ledger),
                                 *map(str, arguments)], capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def read(self):
        return json.loads(self.ledger.read_text())

    def log(self, thread, entries, parent=None, folder="sessions"):
        path = self.home / folder / (thread + ".jsonl")
        path.parent.mkdir(exist_ok=True)
        metadata = {"type": "session_meta", "payload": {"id": thread,
                    "source": {"subagent": {"thread_spawn": {"parent_thread_id": parent}}}}}
        path.write_text("".join(json.dumps(value) + "\n" for value in [metadata, *entries]))
        return path

    def register(self, attempt, role="root", root="task"):
        return self.run_cli("register", "--attempt-ref", attempt, "--decision-id", "decision-" + attempt,
                            "--role", role, "--root-turn", root)

    def bind(self, attempt, thread="parent", turn="turn", code=0):
        return self.run_cli("bind", "--attempt-ref", attempt, "--thread-id", thread,
                            "--turn-id", turn, "--verified", code=code)

    def root(self):
        self.register("root")
        self.bind("root")
        self.log("parent", [usage("parent", "p", 10)])

    def test_usage_checkpoint_produces_matching_estimate_and_zero_is_valid(self):
        self.register("root")
        self.bind("root")
        context = {"type": "turn_context", "payload": {"turn_id": "turn", "root_turn_id": "task", "model": "test-model", "effort": "medium"}}
        self.log("parent", [context, usage("parent", "p", 10, components={"input_tokens": 8, "output_tokens": 2})])
        self.run_cli("checkpoint")
        events = [item["event"] for item in self.read()["events"].values()]
        manifests = [item for item in events if item["kind"] == "run_manifest"]
        self.assertEqual(len(manifests), 1)
        manifest = manifests[0]
        self.assertEqual(manifest["payload"]["scenario"]["initial_context_tokens"], 8)
        self.assertEqual(manifest["payload"]["scenario"]["stages"], [{"context_growth_tokens": 0, "work_output_tokens": 2, "passes": 1}])
        self.assertEqual(manifest["payload"]["segments"][0]["usage_event_id"], next(item["event_id"] for item in events if item["kind"] == "usage"))
        self.run_cli("checkpoint")
        self.assertEqual(events, [item["event"] for item in self.read()["events"].values()])
        self.register("continuation", root="task-next")
        self.bind("continuation", turn="turn-next")
        context_next = {"type": "turn_context", "payload": {"turn_id": "turn-next", "root_turn_id": "task-next", "model": "test-model", "effort": "medium"}}
        self.log("parent", [context, usage("parent", "p", 10, components={"input_tokens": 8, "output_tokens": 2}), context_next,
                            usage("parent", "p-next", 5, turn="turn-next", root="task-next", components={"input_tokens": 4, "output_tokens": 1})])
        self.run_cli("checkpoint")
        latest = [item["event"] for item in self.read()["events"].values() if item["event"]["kind"] == "run_manifest" and len(item["event"]["payload"]["segments"]) == 2][0]
        self.assertEqual(latest["payload"]["run_id"], manifest["payload"]["run_id"])
        self.assertEqual(latest["payload"]["host_root_ref"], manifest["payload"]["host_root_ref"])

    def fake_laya(self, status="stored", lose_receipt=False, late_final=False):
        path = self.home / "laya"
        # Exercise the same newline MCP transport as laya mcp without any service mutation.
        path.write_text("#!" + sys.executable + "\n" + '''import json, sys
from pathlib import Path
for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    method = request["method"]
    if method == "initialize":
        result = {"protocolVersion": "2025-03-26"}
    elif method == "tools/list":
        result = {"tools": [{"name": "laya_feedback", "inputSchema": {
            "usage": {}, "aggregation": {}, "usage_stream_id": {}, "source_sequence": {}}}]}
    else:
        event = request["params"]["arguments"]
        ledger = json.loads(Path(__file__).with_name("ledger.json").read_text())
        assert ledger["events"][event["event_id"]]["event"] == event
        marker = Path(__file__).with_suffix(".flushed")
        if LATE and not marker.exists():
            with (Path(__file__).parent / "sessions/parent.jsonl").open("a") as output:
                output.write(json.dumps(FINAL) + "\\n")
            marker.touch()
        with Path(__file__).with_suffix(".sent").open("a") as output:
            output.write(json.dumps(event) + "\\n")
        if LOSE:
            sys.exit(0)
        receipt = {"status": STATUS, "event_id": event["event_id"]}
        result = {"structuredContent": receipt, "isError": False}
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
'''.replace("STATUS", repr(status)).replace("LOSE", repr(lose_receipt))
            .replace("LATE", repr(late_final))
            .replace("FINAL", repr(usage("parent", "final", 5, cumulative=15))))
        path.chmod(0o700)
        return path

    def test_root_child_dedup_and_restart_before_enqueue(self):
        self.root()
        self.register("child", "child")
        result = self.run_cli("checkpoint", code=2)
        self.assertEqual(result["incomplete_registrations"], ["child"])
        self.bind("child", "child")
        child = usage("child", "c", 20)
        self.log("child", [child, child], "parent")
        self.log("child", [child], "parent", "archived_sessions")
        result = self.run_cli("checkpoint")
        self.assertEqual(result["total_tokens"], 30)
        self.assertEqual(result["delivery"], {"prepared": 2})
        before = self.read()["events"]
        laya = self.fake_laya()
        result = self.run_cli("checkpoint", "--deliver", "--consent-confirmed", "--laya", laya)
        self.assertEqual(result["delivery"], {"stored": 2})
        self.run_cli("checkpoint", "--deliver", "--consent-confirmed", "--laya", laya)
        sent = [json.loads(line) for line in laya.with_suffix(".sent").read_text().splitlines()]
        self.assertEqual(len(sent), 2)
        self.assertEqual({event["event_id"] for event in sent}, set(before))

    def test_lost_receipt_reuses_exact_event_and_queued_is_not_stored(self):
        self.root()
        laya = self.fake_laya(lose_receipt=True)
        result = self.run_cli("checkpoint", "--deliver", "--consent-confirmed", "--laya", laya, code=2)
        self.assertTrue(result["errors"])
        self.fake_laya("queued_local")
        result = self.run_cli("checkpoint", "--deliver", "--consent-confirmed", "--laya", laya, code=2)
        self.assertEqual(result["delivery"], {"queued_local": 1})
        self.assertFalse(result["delivery_complete"])
        self.fake_laya("stored")
        result = self.run_cli("checkpoint", "--deliver", "--consent-confirmed", "--laya", laya)
        self.assertEqual(result["delivery"], {"stored": 1})
        self.assertTrue(result["delivery_complete"])
        sent = [json.loads(line) for line in laya.with_suffix(".sent").read_text().splitlines()]
        self.assertEqual(sent, [sent[0]] * 3)

    def test_disabled_consent_and_missing_permission_never_enable(self):
        self.root()
        laya = self.fake_laya("not_recorded")
        self.run_cli("checkpoint", "--deliver", "--laya", laya, code=2)
        self.assertFalse(laya.with_suffix(".sent").exists())
        result = self.run_cli("checkpoint", "--deliver", "--consent-confirmed", "--laya", laya, code=2)
        self.assertEqual(result["delivery"], {"not_recorded": 1})
        self.run_cli("checkpoint", "--deliver", "--consent-confirmed", "--laya", laya, code=2)
        self.assertEqual(len(laya.with_suffix(".sent").read_text().splitlines()), 1)

    def test_resume_separate_attempt_and_exact_root_identity(self):
        self.root()
        self.register("child", "child")
        self.bind("child", "child")
        self.register("root2", root="next")
        self.bind("root2", turn="turn2")
        self.register("child2", "child", "next")
        self.bind("child2", "child", "turn2")
        self.log("parent", [usage("parent", "p", 10), usage("parent", "p2", 7, turn="turn2", root="next")])
        self.log("child", [usage("child", "c", 20), usage("child", "c2", 8, turn="turn2", root="next")], "parent")
        self.assertEqual(self.run_cli("checkpoint")["total_tokens"], 45)
        self.assertEqual(len(self.read()["events"]), 4)
        self.bind("root", "child", code=2)
        self.bind("child", "child", "turn2", code=2)

    def test_late_final_flush_and_no_quiet_period_completion_claim(self):
        self.root()
        before = self.run_cli("finalize", "--watch-seconds", 0, code=2)
        self.assertEqual(before["finalization"]["status"], "checkpoint_only")
        def flush():
            time.sleep(0.2)
            with (self.home / "sessions/parent.jsonl").open("a") as stream:
                stream.write(json.dumps(usage("parent", "final", 5, cumulative=15)) + "\n")
        worker = threading.Thread(target=flush)
        worker.start()
        result = self.run_cli("finalize", "--watch-seconds", 2, "--poll-seconds", 0.05,
                              "--final-response-id", "final")
        worker.join()
        self.assertEqual(result["total_tokens"], 15)
        self.assertEqual(result["finalization"]["status"], "final_response_observed")

    def test_wrong_child_same_count_and_missing_root_registration_fail_coverage(self):
        self.log("parent", [usage("parent", "p", 10)])
        self.register("child", "child")
        self.bind("child", "expected")
        self.log("different", [usage("different", "c", 20)], "parent")
        result = self.run_cli("checkpoint", code=2)
        self.assertEqual(result["unregistered_root_turns"], ["task"])
        self.assertEqual(self.read()["events"], {})
        self.assertIn("binding references an unknown native segment", result["errors"])

    def test_background_watcher_captures_late_flush_and_can_resume(self):
        self.root()
        result = self.run_cli("finalize", "--background", "--watch-seconds", 0.5,
                              "--poll-seconds", 0.05)
        self.assertEqual(result["status"], "scheduled")
        with (self.home / "sessions/parent.jsonl").open("a") as stream:
            stream.write(json.dumps(usage("parent", "final", 5, cumulative=15)) + "\n")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            ledger = self.read()
            if ledger.get("checkpoint", {}).get("report", {}).get("total_tokens") == 15:
                break
            time.sleep(0.05)
        self.assertEqual(ledger["checkpoint"]["report"]["total_tokens"], 15)
        # Allow the bounded process to exit before TemporaryDirectory cleanup.
        time.sleep(0.7)
        result = self.run_cli("finalize", "--watch-seconds", 0, "--final-response-id", "final")
        self.assertEqual(result["finalization"]["status"], "final_response_observed")

    def test_final_usage_arriving_during_delivery_is_not_prematurely_finalized(self):
        self.root()
        laya = self.fake_laya(late_final=True)
        result = self.run_cli("finalize", "--watch-seconds", 0, "--final-response-id", "final",
                              "--deliver", "--consent-confirmed", "--laya", laya, code=2)
        self.assertEqual(result["total_tokens"], 10)
        self.assertEqual(result["finalization"]["status"], "checkpoint_only")
        result = self.run_cli("finalize", "--watch-seconds", 0, "--final-response-id", "final",
                              "--deliver", "--consent-confirmed", "--laya", laya)
        self.assertEqual(result["total_tokens"], 15)
        self.assertTrue(result["delivery_complete"])
        self.assertEqual(result["finalization"]["status"], "final_response_observed")


if __name__ == "__main__":
    unittest.main()
