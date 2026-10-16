"""
csat_gui.py: Local web interface for CSAT.

Runs a small HTTP server on 127.0.0.1 (standard library only) and opens the
browser. All scoring and reporting is done by csat_core; the page in web/
only renders it. Sessions are plain YAML files in the working directory.
"""

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import csat_core as core

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


class State:
    def __init__(self, workdir, path=None):
        self.workdir = Path(workdir).resolve()
        self.lock = threading.Lock()
        self.path = None
        self.session = core.new_session()
        if path:
            self.open(path, allow_absolute=True)

    def resolve(self, name):
        """Session files live in the working directory: no path traversal."""
        name = os.path.basename(str(name or "").strip())
        if not name:
            raise ValueError("Empty file name")
        if not name.lower().endswith((".yaml", ".yml")):
            name += ".yaml"
        return self.workdir / name

    def open(self, name, allow_absolute=False):
        p = Path(name)
        p = p.resolve() if allow_absolute and p.exists() else self.resolve(name)
        self.session = core.load_session(p)
        self.path = p

    def files(self):
        out = []
        for p in sorted(self.workdir.glob("*.y*ml"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                s = core.load_session(p)
            except Exception:
                continue
            out.append({"name": p.name, "case_id": s["meta"]["case_id"], "ioc": s["meta"]["ioc"],
                        "updated": s["meta"]["updated"]})
        return out

    def payload(self):
        return {
            "path": self.path.name if self.path else None,
            "workdir": str(self.workdir),
            "session": self.session,
            "analysis": core.analyze(self.session),
            "constants": {
                "consistency": core.CONSISTENCY, "reliability": core.RELIABILITY,
                "tlp": core.TLP_LEVELS, "confidence": core.CONFIDENCE_LEVELS,
                "da_areas": core.DA_AREAS,
            },
        }


def make_handler(state, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "CSAT"

        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _guard(self):
            # Block DNS-rebinding / cross-site requests to the local server.
            if self.headers.get("Host") not in allowed_hosts:
                self._send(403, {"error": "forbidden host"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin.split("//", 1)[-1] not in allowed_hosts:
                self._send(403, {"error": "forbidden origin"})
                return False
            return True

        def _json(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if not self._guard():
                return
            url = urlparse(self.path)
            if url.path in STATIC:
                name, ctype = STATIC[url.path]
                return self._send(200, (WEB_DIR / name).read_bytes(), ctype)
            with state.lock:
                if url.path == "/api/state":
                    return self._send(200, state.payload())
                if url.path == "/api/files":
                    return self._send(200, state.files())
                if url.path == "/api/report.md":
                    dl = "download" in parse_qs(url.query)
                    hdr = {"Content-Disposition": 'attachment; filename="{}"'.format(
                        core.report_filename(state.session))} if dl else None
                    return self._send(200, core.generate_report(state.session),
                                      "text/markdown; charset=utf-8", hdr)
                if url.path == "/api/report.html":
                    return self._send(200, core.report_html(state.session), "text/html; charset=utf-8")
                if url.path == "/api/session.yaml":
                    name = state.path.name if state.path else "session.yaml"
                    return self._send(200, core.dump_session(state.session), "application/x-yaml; charset=utf-8",
                                      {"Content-Disposition": f'attachment; filename="{name}"'})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._guard():
                return
            url = urlparse(self.path)
            try:
                body = self._json()
                with state.lock:
                    if url.path == "/api/update":
                        # Live edit: normalise, re-analyse, autosave if a file is attached
                        state.session = core.normalize(body.get("session") or {})
                        saved = False
                        if state.path:
                            core.save_session(state.session, state.path)
                            saved = True
                        return self._send(200, {"analysis": core.analyze(state.session), "saved": saved,
                                                "path": state.path.name if state.path else None})
                    if url.path == "/api/save":
                        if body.get("name"):
                            state.path = state.resolve(body["name"])
                        if not state.path:
                            cid = state.session["meta"]["case_id"] or "cti"
                            state.path = state.resolve("session_" + "".join(
                                ch if ch.isalnum() or ch in "-_." else "_" for ch in cid))
                        core.save_session(state.session, state.path)
                        return self._send(200, state.payload())
                    if url.path == "/api/open":
                        state.open(body["name"])
                        return self._send(200, state.payload())
                    if url.path == "/api/import":
                        state.session = core.load_session_text(body["text"])
                        state.path = state.resolve(body["name"]) if body.get("name") else None
                        if state.path and state.path.exists():
                            state.path = None  # never overwrite silently; user saves explicitly
                        return self._send(200, state.payload())
                    if url.path == "/api/new":
                        state.session = core.new_session()
                        state.path = None
                        return self._send(200, state.payload())
                    if url.path == "/api/report/save":
                        p = state.workdir / core.report_filename(state.session)
                        p.write_text(core.generate_report(state.session), encoding="utf-8")
                        return self._send(200, {"file": p.name})
            except Exception as e:  # report to the UI instead of dropping the connection
                return self._send(400, {"error": str(e)})
            self._send(404, {"error": "not found"})

    return Handler


def run(workdir=".", path=None, port=8765, open_browser=True):
    state = State(workdir, path)
    server = None
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), make_handler(state, p))
            port = p
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("No free port found")
    url = f"http://127.0.0.1:{port}/"
    print(f"\n  CSAT is running → {url}", flush=True)
    print(f"  Sessions folder: {state.workdir}")
    print("  Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Bye.")
    finally:
        server.server_close()
