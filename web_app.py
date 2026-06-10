import argparse
import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from web_simulation import IMAGE_DIR, ROOT_DIR, list_character_catalog, run_web_batch_simulation, run_web_simulation


STATIC_DIR = ROOT_DIR / "web_static"


def safe_print(message):
    try:
        print(message, flush=True)
    except Exception:
        pass


class SimulatorWebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/characters":
            self._send_json(200, list_character_catalog())
            return

        if path == "/":
            self._send_static(STATIC_DIR / "index.html")
            return

        if path in {"/batch", "/batch/"}:
            self._send_static(STATIC_DIR / "batch.html")
            return

        if path.startswith("/static/"):
            relative = unquote(path.removeprefix("/static/"))
            self._send_static(STATIC_DIR / relative)
            return

        if path.startswith("/images/"):
            relative = unquote(path.removeprefix("/images/"))
            self._send_file(IMAGE_DIR / relative, IMAGE_DIR)
            return

        self._send_json(404, {"status": "error", "error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/simulate", "/api/simulate-batch"}:
            self._send_json(404, {"status": "error", "error": "Not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > 2 * 1024 * 1024:
                raise ValueError("Request body is too large")
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body) if body else {}
            if parsed.path == "/api/simulate-batch":
                result = run_web_batch_simulation(payload)
            else:
                result = run_web_simulation(payload)
            self._send_json(200, result)
        except Exception as exc:
            self._send_json(
                400,
                {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

    def log_message(self, format, *args):
        safe_print(f"[web] {self.address_string()} - {format % args}")

    def _send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_static(self, path):
        self._send_file(path, STATIC_DIR)

    def _send_file(self, path, root):
        path = path.resolve()
        safe_root = root.resolve()
        if path != safe_root and safe_root not in path.parents:
            self._send_json(403, {"status": "error", "error": "Forbidden"})
            return
        if not path.exists() or not path.is_file():
            self._send_json(404, {"status": "error", "error": "Not found"})
            return

        content = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    parser = argparse.ArgumentParser(description="Run the local simulator web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), SimulatorWebHandler)
    url = f"http://{args.host}:{args.port}"
    safe_print(f"Simulator web UI: {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        (ROOT_DIR / "web_server_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
