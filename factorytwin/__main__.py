"""Local-only demo server: python -m factorytwin [--blueprint FILE] [--quality-scenario FILE]"""
import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import unquote, urlsplit

from .blueprint import DEFAULT_BLUEPRINT, FactoryBlueprint
from .quality import DEFAULT_QUALITY_SCENARIO, QualityScenario
from .sim import ProductionLine

ROOT = Path(__file__).resolve().parents[1] / "web"
SIM = ProductionLine()
LOCK = Lock()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def respond(self, status: int, obj: dict):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/snapshot":
            with LOCK:
                snapshot = SIM.step()
            self.respond(200, snapshot)
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
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= 4096:
                return self.respond(400, {"error": "invalid request size"})
            data = json.loads(self.rfile.read(n))
            if not isinstance(data, dict):
                return self.respond(400, {"error": "JSON object required"})
            with LOCK:
                SIM.control(data.get("action", ""), data.get("station"))
                state = SIM.snapshot()
            self.respond(200, state)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.respond(400, {"error": str(exc)})


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="FactoryTwin synthetic factory simulator")
    parser.add_argument("--blueprint", type=Path, help="validated local JSON station graph")
    parser.add_argument("--quality-scenario", type=Path,
                        help="validated deterministic local JSON quality scenario")
    args = parser.parse_args(argv)
    blueprint = FactoryBlueprint.load(args.blueprint) if args.blueprint is not None else DEFAULT_BLUEPRINT
    quality = (QualityScenario.load(args.quality_scenario)
               if args.quality_scenario is not None else DEFAULT_QUALITY_SCENARIO)
    global SIM
    SIM = ProductionLine(blueprint=blueprint, quality_scenario=quality)
    httpd = ThreadingHTTPServer(("127.0.0.1", 8766), Handler)
    print("FactoryTwin (simulated factory): http://127.0.0.1:8766")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
