"""Automated software-only local acceptance validation for FactoryTwin.

The harness launches the real CLI in a child process, drives only the loopback
HTTP API, restarts against the same temporary SQLite database, and verifies
recovery. It intentionally does not automate a browser or any physical-device
integration.
"""
from __future__ import annotations

import argparse
import http.client
import json
import queue
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote

_START_RE = re.compile(r"^FactoryTwin \(simulated factory\): http://127\.0\.0\.1:(\d+)$")


class AcceptanceFailure(RuntimeError):
    """Raised when the local acceptance contract is not satisfied."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def _request(port: int, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if body is None else {"Content-Type": "application/json"}
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            raise AcceptanceFailure(f"non-object response from {method} {path}")
        return response.status, data
    finally:
        connection.close()


def _get(port: int, path: str) -> dict:
    status, data = _request(port, "GET", path)
    _require(status == 200, f"GET {path} returned {status}: {data}")
    return data


def _control(port: int, action: str, station: str | None = None) -> dict:
    payload = {"action": action}
    if station is not None:
        payload["station"] = station
    status, data = _request(port, "POST", "/api/control", payload)
    _require(status == 200, f"control {action!r} returned {status}: {data}")
    return data


def _close_process_streams(process: subprocess.Popen[str]) -> None:
    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()
    if process.stdout is not None and not process.stdout.closed:
        process.stdout.close()


def _start_server(database: Path) -> tuple[subprocess.Popen[str], int]:
    process = subprocess.Popen(
        [sys.executable, "-m", "factorytwin", "--database", str(database),
         "--port", "0", "--shutdown-on-stdin"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    _require(process.stdin is not None, "server stdin pipe was not created")
    _require(process.stdout is not None, "server stdout pipe was not created")

    ready: queue.Queue[str] = queue.Queue(maxsize=1)

    def read_startup_line() -> None:
        assert process.stdout is not None
        ready.put(process.stdout.readline())

    reader = threading.Thread(target=read_startup_line, daemon=True)
    reader.start()
    try:
        line = ready.get(timeout=10).strip()
    except queue.Empty as exc:
        process.kill()
        process.wait(timeout=5)
        _close_process_streams(process)
        raise AcceptanceFailure("server did not report its loopback URL within 10 seconds") from exc

    match = _START_RE.fullmatch(line)
    if match is None:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        remainder = process.stdout.read().strip() if process.stdout is not None else ""
        _close_process_streams(process)
        detail = "\n".join(part for part in (line, remainder) if part)
        raise AcceptanceFailure(f"unexpected server startup output: {detail!r}")

    port = int(match.group(1))
    _require(0 < port <= 65535, "server reported an invalid port")
    health = _get(port, "/api/health")
    _require(health == {"status": "ok", "source": "simulation"}, "health contract mismatch")
    return process, port


def _stop_server(process: subprocess.Popen[str]) -> str:
    if process.poll() is None:
        try:
            _require(process.stdin is not None and not process.stdin.closed,
                     "server lifecycle stdin was unavailable")
            process.stdin.close()
            process.wait(timeout=10)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            process.kill()
            process.wait(timeout=5)
            _close_process_streams(process)
            raise AcceptanceFailure("server did not stop cleanly after lifecycle shutdown") from exc
    output = process.stdout.read() if process.stdout is not None else ""
    returncode = process.returncode
    _close_process_streams(process)
    _require(returncode == 0, f"server exited with code {returncode}: {output}")
    return output


def _advance_until_completed(port: int, minimum_completed: int, max_steps: int = 40) -> dict:
    snapshot = {}
    for _ in range(max_steps):
        snapshot = _get(port, "/api/snapshot")
        if snapshot.get("completed", 0) >= minimum_completed:
            return snapshot
    raise AcceptanceFailure(
        f"completed count did not reach {minimum_completed} within {max_steps} observation ticks"
    )


def _completed_workpiece(snapshot: dict) -> str:
    recent = snapshot.get("recent_workpieces")
    _require(isinstance(recent, list), "snapshot did not expose recent_workpieces")
    for item in reversed(recent):
        if isinstance(item, dict) and item.get("status") == "COMPLETED" and isinstance(item.get("id"), str):
            return item["id"]
    raise AcceptanceFailure("no completed workpiece was available in recent_workpieces")


def _genealogy(port: int, workpiece_id: str) -> dict:
    record = _get(port, f"/api/workpieces/{quote(workpiece_id, safe='')}")
    _require(record.get("id") == workpiece_id, "genealogy returned a different workpiece")
    _require(record.get("status") == "COMPLETED", "selected workpiece was not completed")
    visits = record.get("visits")
    _require(isinstance(visits, list) and visits, "completed workpiece had no genealogy visits")
    _require(all(isinstance(visit, dict) and visit.get("outcome") == "GOOD" for visit in visits),
             "default acceptance workpiece did not have all-GOOD station outcomes")
    return record


def _run(database: Path) -> dict:
    first, first_port = _start_server(database)
    try:
        running = _advance_until_completed(first_port, 4)
        _require(running.get("state") == "RUNNING", "simulator did not start in RUNNING state")
        quality = running.get("quality", {})
        _require(quality.get("good_units") == running.get("completed"),
                 "default-good quality count did not match completed count")
        workpiece_id = _completed_workpiece(running)
        _genealogy(first_port, workpiece_id)

        paused = _control(first_port, "pause")
        _require(paused.get("state") == "PAUSED", "pause did not enter PAUSED state")
        paused_completed = paused.get("completed")
        paused_tick = paused.get("tick")
        paused_step = _get(first_port, "/api/snapshot")
        _require(paused_step.get("tick") == paused_tick + 1, "paused observation did not advance tick")
        _require(paused_step.get("completed") == paused_completed,
                 "productive processing advanced while paused")

        resumed = _control(first_port, "resume")
        _require(resumed.get("state") == "RUNNING", "resume did not restore RUNNING state")

        faulted = _control(first_port, "fault", "Processing")
        _require(faulted.get("state") == "FAULT", "synthetic fault did not interlock the line")
        _require(faulted.get("fault_stations") == ["Processing"], "fault latch was not reported")
        fault_completed = faulted.get("completed")
        fault_tick = faulted.get("tick")
        blocked = _get(first_port, "/api/snapshot")
        _require(blocked.get("tick") == fault_tick + 1, "faulted observation did not advance tick")
        _require(blocked.get("completed") == fault_completed,
                 "productive processing advanced while faulted")

        still_faulted = _control(first_port, "resume")
        _require(still_faulted.get("state") == "FAULT", "resume bypassed the fault interlock")
        paused_fault = _control(first_port, "pause")
        _require(paused_fault.get("state") == "PAUSED", "pause did not take precedence over fault")
        cleared_while_paused = _control(first_port, "clear_fault")
        _require(cleared_while_paused.get("state") == "PAUSED",
                 "clear_fault incorrectly resumed an independently paused line")
        _require(cleared_while_paused.get("fault_stations") == [], "fault latch did not clear")
        resumed_after_clear = _control(first_port, "resume")
        _require(resumed_after_clear.get("state") == "RUNNING",
                 "resume after clear_fault did not restore RUNNING")

        target = int(resumed_after_clear.get("completed", 0)) + 5
        checkpoint = _advance_until_completed(first_port, target)
        checkpoint_id = _completed_workpiece(checkpoint)
        checkpoint_genealogy = _genealogy(first_port, checkpoint_id)
        checkpoint_record = {
            "tick": checkpoint["tick"],
            "completed": checkpoint["completed"],
            "good_units": checkpoint["quality"]["good_units"],
            "workpiece_id": checkpoint_id,
            "state": checkpoint["state"],
            "fault_stations": checkpoint["fault_stations"],
            "genealogy": checkpoint_genealogy,
        }
    finally:
        first_output = _stop_server(first)

    _require(database.is_file() and database.stat().st_size > 0, "SQLite database was not persisted")

    second, second_port = _start_server(database)
    try:
        recovered_genealogy = _genealogy(second_port, checkpoint_record["workpiece_id"])
        _require(recovered_genealogy == checkpoint_record["genealogy"],
                 "workpiece genealogy changed across process restart")

        recovered = _get(second_port, "/api/snapshot")
        _require(recovered.get("tick") == checkpoint_record["tick"] + 1,
                 "restart did not recover the prior tick before the next observation")
        _require(recovered.get("completed", 0) >= checkpoint_record["completed"],
                 "completed count regressed across restart")
        _require(recovered.get("quality", {}).get("good_units", 0) >= checkpoint_record["good_units"],
                 "good-unit count regressed across restart")
        _require(recovered.get("state") == "RUNNING", "recovered simulator was not RUNNING")
        _require(recovered.get("fault_stations") == [], "cleared faults returned after restart")

        continued = _advance_until_completed(second_port, checkpoint_record["completed"] + 3)
        _require(continued.get("tick", 0) > recovered.get("tick", 0),
                 "simulation did not continue after restart")
        _require(_genealogy(second_port, checkpoint_record["workpiece_id"]) == checkpoint_record["genealogy"],
                 "historical genealogy changed after continued processing")
    finally:
        second_output = _stop_server(second)

    return {
        "status": "PASS",
        "bind": "127.0.0.1",
        "first_port": first_port,
        "second_port": second_port,
        "checkpoint": checkpoint_record,
        "after_restart": {
            "tick": recovered["tick"],
            "completed": recovered["completed"],
            "good_units": recovered["quality"]["good_units"],
            "continued_tick": continued["tick"],
            "continued_completed": continued["completed"],
        },
        "clean_shutdown": bool(first_output is not None and second_output is not None),
    }


def run_acceptance(database: Path | None = None) -> dict:
    """Run the subprocess/API/restart acceptance scenario and return a JSON-safe report."""
    if database is not None:
        path = Path(database)
        path.parent.mkdir(parents=True, exist_ok=True)
        return _run(path)
    with tempfile.TemporaryDirectory(prefix="factorytwin-acceptance-") as temp:
        return _run(Path(temp) / "factorytwin.sqlite3")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FactoryTwin software-only local acceptance harness")
    parser.add_argument("--database", type=Path,
                        help="optional SQLite path to retain after the acceptance run")
    args = parser.parse_args(argv)
    try:
        report = run_acceptance(args.database)
    except AcceptanceFailure as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
