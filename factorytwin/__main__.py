"""Local-only FactoryTwin demo server with persistence, metrics and SSE."""
import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import unquote, urlsplit

from .blueprint import DEFAULT_BLUEPRINT, FactoryBlueprint
from .fault_persistence import FaultPersistentProductionLine
from .metrics import DEFAULT_METRICS_PLAN, MetricsPlan
from .persistence import PersistenceError
from .quality import DEFAULT_QUALITY_SCENARIO, QualityScenario
from .sim import ProductionLine
from .streaming import SnapshotStreamHub

ROOT = Path(__file__).resolve().parent / "web"
MAX_CONTROL_BODY_BYTES = 4096
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Content-Security-Policy", "base-uri 'none'; frame-ancestors 'none'; object-src 'none'"),
)
SIM = ProductionLine()
LOCK = Lock()
STREAM = SnapshotStreamHub()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        super().end_headers()

    def respond(self, status: int, obj: dict):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_control_json(self):
        if self.headers.get("Transfer-Encoding") is not None:
            self.respond(400, {"error": "transfer encoding not supported"})
            return None

        content_type = self.headers.get("Content-Type")
        media_type = "" if content_type is None else content_type.partition(";")[0].strip().lower()
        if media_type != "application/json":
            self.respond(415, {"error": "application/json required"})
            return None

        lengths = self.headers.get_all("Content-Length", [])
        if not lengths:
            self.respond(411, {"error": "Content-Length required"})
            return None
        if len(lengths) != 1:
            self.respond(400, {"error": "invalid request size"})
            return None

        raw_length = lengths[0]
        if not raw_length.isascii() or not raw_length.isdigit():
            self.respond(400, {"error": "invalid request size"})
            return None
        n = int(raw_length)
        if not 0 < n <= MAX_CONTROL_BODY_BYTES:
            self.respond(400, {"error": "invalid request size"})
            return None

        raw = self.rfile.read(n)
        if len(raw) != n:
            self.respond(400, {"error": "incomplete request body"})
            return None
        try:
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.respond(400, {"error": "invalid JSON"})
            return None
        if not isinstance(data, dict):
            self.respond(400, {"error": "JSON object required"})
            return None
        return data

    def _stream(self):
        raw_last_id = self.headers.get("Last-Event-ID")
        try:
            last_id = None if raw_last_id in (None, "") else int(raw_last_id)
            if last_id is not None and last_id < 0:
                raise ValueError
        except ValueError:
            return self.respond(400, {"error": "invalid Last-Event-ID"})
        with LOCK:
            current = SIM.snapshot()
        frames = STREAM.reconnect(last_id, current)
        cursor = last_id if last_id is not None else STREAM.latest_id
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            while True:
                for frame in frames:
                    payload = json.dumps(frame.data, separators=(",", ":"))
                    self.wfile.write(
                        f"id: {frame.id}\nevent: {frame.event}\ndata: {payload}\n\n".encode("utf-8"))
                    cursor = frame.id
                if frames:
                    self.wfile.flush()
                frames = STREAM.wait_after(cursor)
                if not frames:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    with LOCK:
                        current = SIM.snapshot()
                    frames = STREAM.reconnect(cursor, current)
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            return

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/snapshot":
            try:
                with LOCK:
                    snapshot = SIM.step()
                STREAM.publish(snapshot)
                self.respond(200, snapshot)
            except PersistenceError as exc:
                self.respond(503, {"error": str(exc)})
        elif path == "/api/stream":
            self._stream()
        elif path == "/api/health":
            self.respond(200, {"status": "ok", "source": "simulation"})
        elif path.startswith("/api/workpieces/"):
            workpiece_id = unquote(path.removeprefix("/api/workpieces/"))
            if "/" in workpiece_id or not workpiece_id:
                return self.respond(404, {"error": "workpiece not found"})
            try:
                with LOCK:
                    genealogy = SIM.workpiece_genealogy(workpiece_id)
                self.respond(200, genealogy)
            except ValueError:
                self.respond(404, {"error": "workpiece not found"})
        else:
            super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/control":
            return self.respond(404, {"error": "not found"})
        data = self._read_control_json()
        if data is None:
            return
        try:
            with LOCK:
                SIM.control(data.get("action", ""), data.get("station"))
                state = SIM.snapshot()
            STREAM.publish(state)
            self.respond(200, state)
        except PersistenceError as exc:
            self.respond(503, {"error": str(exc)})
        except (ValueError, TypeError) as exc:
            self.respond(400, {"error": str(exc)})


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="FactoryTwin synthetic factory simulator")
    parser.add_argument("--blueprint", type=Path, help="validated local JSON station graph")
    parser.add_argument("--quality-scenario", type=Path,
                        help="validated deterministic local JSON quality scenario")
    parser.add_argument("--database", type=Path,
                        help="optional local SQLite file for durable simulation state")
    parser.add_argument("--metrics-plan", type=Path,
                        help="optional local JSON declaration enabling synthetic OEE")
    parser.add_argument("--port", type=int, default=8766,
                        help="loopback HTTP port (default: 8766; use 0 for an ephemeral test port)")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    requested_blueprint = FactoryBlueprint.load(args.blueprint) if args.blueprint is not None else None
    requested_quality = (QualityScenario.load(args.quality_scenario)
                         if args.quality_scenario is not None else None)
    metrics_plan = (MetricsPlan.load(args.metrics_plan)
                    if args.metrics_plan is not None else DEFAULT_METRICS_PLAN)
    global SIM, STREAM
    if args.database is not None:
        SIM = FaultPersistentProductionLine.open(args.database, blueprint=requested_blueprint,
                                                 quality_scenario=requested_quality)
    else:
        SIM = ProductionLine(blueprint=requested_blueprint or DEFAULT_BLUEPRINT,
                             quality_scenario=requested_quality or DEFAULT_QUALITY_SCENARIO)
    SIM.metrics_plan = metrics_plan
    STREAM = SnapshotStreamHub()
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    actual_port = httpd.server_address[1]
    print(f"FactoryTwin (simulated factory): http://127.0.0.1:{actual_port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
