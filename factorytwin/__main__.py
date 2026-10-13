"""Local-only demo server: python -m factorytwin [--blueprint FILE]"""
import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

from .blueprint import FactoryBlueprint
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
        if self.path == "/api/snapshot":
            with LOCK:
                snapshot = SIM.step()
            self.respond(200, snapshot)
        elif self.path == "/api/health":
            self.respond(200, {"status": "ok", "source": "simulation"})
        else:
            super().do_GET()

    def do_POST(self):
        if self.path != "/api/control":
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
    args = parser.parse_args(argv)
    global SIM
    if args.blueprint is not None:
        SIM = ProductionLine(blueprint=FactoryBlueprint.load(args.blueprint))
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
