#!/usr/bin/env python3
"""Durable, explicit Codex task usage registration and Laya MCP delivery."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

from collect_token_usage import collect, records
from prepare_laya_usage import prepare
from prepare_laya_usage import canonical_hash
from prepare_laya_scenario import prepare as prepare_scenario


IDENTITY = ("thread_id", "turn_id", "root_turn_id")
TERMINAL = {"stored", "not_recorded", "rejected", "conflict", "quarantined"}


def save(path, value):
    """A private atomic snapshot: events reach disk before any network operation."""
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def load(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("version") != 1:
        raise ValueError("unsupported lifecycle ledger")
    return value


class MCP:
    """Native newline-delimited MCP stdio; never writes a Laya database."""
    def __init__(self, executable, timeout):
        self.timeout = timeout
        self.sequence = 0
        self.process = subprocess.Popen([executable, "mcp"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.lines.put(line)
        finally:
            self.lines.put(None)

    def send(self, method, params, identity=None):
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if identity is not None:
            message["id"] = identity
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def call(self, method, params):
        self.sequence += 1
        self.send(method, params, self.sequence)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                line = self.lines.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise ValueError("Laya MCP response timed out") from None
            if line is None:
                raise ValueError("Laya MCP exited before receipt")
            value = json.loads(line)
            if value.get("id") != self.sequence:
                continue
            if "error" in value:
                raise ValueError("Laya MCP returned a protocol error")
            return value["result"]

    def ready(self):
        result = self.call("initialize", {"protocolVersion": "2025-03-26",
                                          "capabilities": {}, "clientInfo": {
                                              "name": "squad-usage", "version": "1"}})
        if result.get("protocolVersion") != "2025-03-26":
            raise ValueError("unsupported MCP protocol version")
        self.send("notifications/initialized", {})
        tools = self.call("tools/list", {}).get("tools", [])
        tool = next((item for item in tools if item.get("name") == "laya_feedback"), None)
        schema = json.dumps(tool.get("inputSchema", {})) if tool else ""
        if not all('"' + field + '"' in schema for field in (
                "usage", "aggregation", "usage_stream_id", "source_sequence")):
            raise ValueError("Laya feedback schema lacks native cumulative usage support")

    def feedback(self, event):
        result = self.call("tools/call", {"name": "laya_feedback", "arguments": event})
        if result.get("isError"):
            raise ValueError("Laya feedback tool returned an error")
        receipt = result.get("structuredContent")
        if not isinstance(receipt, dict):
            texts = [item["text"] for item in result.get("content", [])
                     if item.get("type") == "text"]
            receipt = json.loads(texts[0]) if len(texts) == 1 else None
        if (not isinstance(receipt, dict) or receipt.get("event_id") != event["event_id"]
                or receipt.get("status") not in TERMINAL | {"queued_local", "not_saved"}):
            raise ValueError("Laya feedback receipt is ambiguous or mismatched")
        return receipt

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process.stdout.close()


def delivery(path, ledger, executable, timeout):
    pending = [item for item in ledger["events"].values()
               if item.get("receipt", {}).get("status") not in TERMINAL]
    if not pending:
        return
    client = None
    try:
        client = MCP(executable, timeout)
        client.ready()
        ledger.pop("delivery_error", None)
        for item in pending:
            try:
                receipt = client.feedback(item["event"])
                item["receipt"] = receipt
                item.setdefault("receipts", []).append(receipt)
                item.pop("delivery_error", None)
            except (OSError, ValueError, KeyError) as error:
                item["delivery_error"] = str(error)
                save(path, ledger)
                break
            save(path, ledger)
            if receipt["status"] == "not_recorded":
                break
    except (OSError, ValueError, KeyError) as error:
        ledger["delivery_error"] = str(error)
        save(path, ledger)
    finally:
        if client is not None:
            client.close()


def scenario_checkpoint(ledger, report, bindings):
    """Same native checkpoint; unsplit response passes are a declared assumption."""
    pairs = set()
    root_turns = {item["turn_id"] for item in bindings if item["thread_id"] == ledger["root_thread_id"]}
    seen = set()
    for folder in ("sessions", "archived_sessions"):
        for path in (Path(ledger["codex_home"]) / folder).rglob("*.jsonl"):
            iterator = records(path)
            first = next(iterator, {})
            if first.get("type") != "session_meta" or first.get("payload", {}).get("id") != ledger["root_thread_id"]:
                continue
            for record in iterator:
                payload = record.get("payload", {})
                if record.get("type") == "turn_context" and payload.get("turn_id") in root_turns:
                    if not payload.get("model") or not payload.get("effort"):
                        return {"status": "unavailable", "events": [], "errors": ["Root model/effort unavailable"]}
                    pairs.add((payload["model"], payload["effort"]))
                    seen.add(payload["turn_id"])
    if len(pairs) != 1 or seen != root_turns:
        return {"status": "unavailable", "events": [], "errors": ["Root model configuration incomplete or mixed"]}
    model, effort = next(iter(pairs))
    scope = canonical_hash([ledger["root_thread_id"], [ledger["root_turn_ids"][0]]])
    by_identity = {(s["thread_id"], s["turn_id"], s["root_turn_id"]): s for s in report["segments"]}
    plan = {"input_mode": "native-envelope-v1", "run_id": "codex-lifecycle:" + scope,
            "observed_at": report["checkpoint"], "meter_identity": "codex-native-total-tokens",
            "orchestrator": {"model": model, "reasoning_effort": effort, "source": "host",
                             "reference": "codex-root:" + scope},
            "stages": [{**{key: b[key] for key in IDENTITY},
                        "passes": by_identity[tuple(b[key] for key in IDENTITY)]["response_count"]}
                       for b in bindings]}
    result = prepare_scenario(report, bindings, plan)
    if result["status"] == "ok":
        manifest = result["events"][-1]
        manifest["payload"]["host_root_ref"] = "codex-root:" + scope
        manifest["payload"]["scenario"]["input_source"] += "; lifecycle-snapshot-v1; unsplit passes assumed equal observed response count"
        manifest.pop("event_id")
        manifest["event_id"] = "manifest-" + canonical_hash(manifest)
    return result


def checkpoint(path, ledger, args):
    registrations = ledger["registrations"]
    bindings = [item["binding"] for item in registrations.values() if "binding" in item]
    children = {item["thread_id"] for item in bindings
                if item["thread_id"] != ledger["root_thread_id"]}
    report = collect(Path(ledger["codex_home"]), ledger["root_thread_id"],
                     set(ledger["root_turn_ids"]), len(children))
    incomplete = [key for key, item in registrations.items() if "binding" not in item]
    result = prepare(report, bindings)
    missing_roots = [root for root in ledger["root_turn_ids"] if not any(
        item["thread_id"] == ledger["root_thread_id"] and item["root_turn_id"] == root
        for item in bindings)]
    coverage = {"report": report, "preparation": {
        key: value for key, value in result.items() if key != "events"},
        "incomplete_registrations": incomplete, "unregistered_root_turns": missing_roots}
    ledger["checkpoint"] = coverage
    if result["status"] == "ok" and not result.get("unbound_segments") and not incomplete and not missing_roots:
        try:
            estimate = scenario_checkpoint(ledger, report, bindings)
        except (OSError, ValueError, KeyError) as error:
            estimate = {"status": "unavailable", "events": [], "errors": [str(error)]}
        coverage["estimate"] = {key: value for key, value in estimate.items() if key != "events"}
        if estimate["status"] == "ok":
            result["events"] = estimate["events"]
    for event in result["events"]:
        ledger["events"].setdefault(event["event_id"], {"event": event})
    # This commit is also the recovery point if the process dies before enqueue.
    save(path, ledger)
    if args.deliver:
        delivery(path, ledger, args.laya, args.timeout)
    return summary(ledger)


def summary(ledger):
    checkpoint = ledger.get("checkpoint", {})
    report = checkpoint.get("report", {})
    preparation = checkpoint.get("preparation", {})
    incomplete = checkpoint.get("incomplete_registrations", [])
    roots = checkpoint.get("unregistered_root_turns", [])
    complete = (report.get("status") == "ok" and preparation.get("status") == "ok"
                and not preparation.get("unbound_segments") and not incomplete and not roots)
    counts = {}
    for item in ledger["events"].values():
        status = item.get("receipt", {}).get("status", "prepared")
        counts[status] = counts.get(status, 0) + 1
    return {"status": "ok" if complete else "incomplete", "coverage_complete": complete,
            "delivery_complete": bool(ledger["events"]) and complete
            and set(counts) == {"stored"},
            "total_tokens": report.get("total_tokens"), "delivery": counts,
            "estimate": checkpoint.get("estimate", {"status": "unavailable", "errors": ["Usage coverage incomplete"]}),
            "incomplete_registrations": incomplete, "unregistered_root_turns": roots,
            "unbound_segments": preparation.get("unbound_segments"),
            "errors": report.get("errors", []) + preparation.get("errors", [])
            + ([ledger["delivery_error"]] if ledger.get("delivery_error") else [])
            + [item["delivery_error"] for item in ledger["events"].values()
               if item.get("delivery_error")],
            "finalization": ledger.get("finalization", {"status": "not_requested"})}


def final_responses_seen(ledger, response_ids):
    """Match explicit final response IDs in root usage metadata only."""
    found = set()
    roots = set()
    home = Path(ledger["codex_home"])
    for folder in (home / "sessions", home / "archived_sessions"):
        for path in folder.rglob("*.jsonl"):
            try:
                iterator = records(path)
                first = next(iterator, {})
                if (first.get("type") != "session_meta"
                        or first.get("payload", {}).get("id") != ledger["root_thread_id"]):
                    continue
                for record in iterator:
                    payload = record.get("payload", {})
                    if (record.get("type") == "token_usage_record"
                            and payload.get("thread_id") == ledger["root_thread_id"]
                            and payload.get("root_turn_id") in ledger["root_turn_ids"]
                            and payload.get("response_id") in response_ids):
                        found.add(payload["response_id"])
                        roots.add(payload["root_turn_id"])
            except (OSError, ValueError, AttributeError):
                continue
    return (bool(response_ids) and found == set(response_ids)
            and roots == set(ledger["root_turn_ids"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "register", "bind", "checkpoint", "finalize", "status"])
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--root-thread")
    parser.add_argument("--root-turn")
    parser.add_argument("--attempt-ref")
    parser.add_argument("--decision-id")
    parser.add_argument("--role", choices=["root", "child"])
    parser.add_argument("--thread-id")
    parser.add_argument("--turn-id")
    parser.add_argument("--verified", action="store_true")
    parser.add_argument("--deliver", action="store_true")
    parser.add_argument("--consent-confirmed", action="store_true")
    parser.add_argument("--laya", default="laya")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--watch-seconds", type=float, default=30)
    parser.add_argument("--poll-seconds", type=float, default=2)
    parser.add_argument("--final-response-id", action="append", default=[])
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()
    try:
        if args.deliver and not args.consent_confirmed:
            raise ValueError("delivery requires separately verified recording consent; never enables recording")
        if not (0 < args.timeout <= 60 and 0 <= args.watch_seconds <= 600
                and 0 < args.poll_seconds <= 60):
            raise ValueError("invalid bounded timeout/watch/poll interval")
        if args.background:
            if args.command != "finalize":
                raise ValueError("background is only supported for bounded finalize")
            with locked(args.ledger):
                ledger = load(args.ledger)
                ledger["finalization"] = {"status": "scheduled", "watch_seconds": args.watch_seconds}
                save(args.ledger, ledger)
            command = [sys.executable, str(Path(__file__).resolve())]
            command.extend(value for value in sys.argv[1:] if value != "--background")
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       start_new_session=True)
            print(json.dumps({"status": "scheduled", "pid": process.pid,
                              "ledger": str(args.ledger.resolve())}))
            return 0
        if args.command in {"checkpoint", "finalize"}:
            deadline = time.monotonic() + (args.watch_seconds if args.command == "finalize" else 0)
            while True:
                with locked(args.ledger):
                    ledger = load(args.ledger)
                    # Observe the terminal usage before collecting its checkpoint.
                    # Delivery can take time; checking after it could acknowledge
                    # a final response absent from the persisted/sent snapshot.
                    flushed = (args.command == "finalize"
                               and final_responses_seen(ledger, args.final_response_id))
                    result = checkpoint(args.ledger, ledger, args)
                    if args.command == "finalize":
                        ledger["finalization"] = {
                            "status": "final_response_observed" if flushed else "checkpoint_only",
                            "final_response_ids": args.final_response_id,
                            "reason": None if flushed else "Exact root final response usage not yet verified",
                        }
                        save(args.ledger, ledger)
                        result = summary(ledger)
                    else:
                        flushed = False
                if flushed or time.monotonic() >= deadline:
                    break
                time.sleep(min(args.poll_seconds, max(0, deadline - time.monotonic())))
            print(json.dumps(result, indent=2))
            successful = (result["status"] == "ok"
                          and (not args.deliver or result["delivery_complete"])
                          and (args.command != "finalize" or flushed))
            return 0 if successful else 2
        with locked(args.ledger):
            if args.command == "init":
                if not all([args.codex_home, args.root_thread, args.root_turn]):
                    raise ValueError("init requires codex-home, root-thread and root-turn")
                ledger = {"version": 1, "codex_home": str(args.codex_home.resolve()),
                          "root_thread_id": args.root_thread, "root_turn_ids": [args.root_turn],
                          "registrations": {}, "events": {}}
                if args.ledger.exists():
                    existing = load(args.ledger)
                    if any(existing[field] != ledger[field] for field in (
                            "codex_home", "root_thread_id")) or args.root_turn not in existing["root_turn_ids"]:
                        raise ValueError("existing ledger belongs to a different task; use a fresh path")
                    ledger = existing
            else:
                ledger = load(args.ledger)
            if args.command == "register":
                if not all([args.attempt_ref, args.decision_id, args.root_turn, args.role]):
                    raise ValueError("register requires attempt-ref, decision-id, root-turn and role")
                value = {"decision_id": args.decision_id, "root_turn_id": args.root_turn,
                         "role": args.role}
                existing = ledger["registrations"].get(args.attempt_ref)
                if existing and any(existing[field] != value[field] for field in value):
                    raise ValueError("attempt registration is immutable; resumed turns need new attempts")
                ledger["registrations"].setdefault(args.attempt_ref, value)
                if args.root_turn not in ledger["root_turn_ids"]:
                    if args.role != "root":
                        raise ValueError("register the verified root continuation before its children")
                    ledger["root_turn_ids"].append(args.root_turn)
            if args.command == "bind":
                if not all([args.verified, args.thread_id, args.turn_id, args.attempt_ref]):
                    raise ValueError("bind requires verified whole-turn configuration and native identities")
                item = ledger["registrations"][args.attempt_ref]
                if (item["role"] == "root") != (args.thread_id == ledger["root_thread_id"]):
                    raise ValueError("root/child thread identity does not match registration")
                binding = {"thread_id": args.thread_id, "turn_id": args.turn_id,
                           "root_turn_id": item["root_turn_id"], "decision_id": item["decision_id"],
                           "attempt_ref": args.attempt_ref, "configuration_scope_confirmed": True}
                if item.get("binding", binding) != binding:
                    raise ValueError("native binding is immutable; resumed turns need new attempts")
                for other in ledger["registrations"].values():
                    prior = other.get("binding")
                    if prior and prior != binding and all(prior[key] == binding[key] for key in IDENTITY):
                        raise ValueError("native segment already bound to another attempt")
                item["binding"] = binding
            if args.command != "status":
                save(args.ledger, ledger)
            print(json.dumps(summary(ledger), indent=2))
            return 0
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "unavailable", "errors": [str(error)]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
