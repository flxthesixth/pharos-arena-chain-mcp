"""Bounded, no-login read-only demo. Run from any directory: python3 server.py."""
import importlib.util
from collections import deque
from http.client import HTTPException
import json
import os
import socket
import subprocess
import sys
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer as StdlibHTTPServer
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
spec = importlib.util.spec_from_file_location("portfolio", REPO / "pharos_portfolio_box3_20261110.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Portfolio source unavailable")
portfolio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portfolio)
WALLET = "0xa3a331bd8ad8122c3fce2a1ea2de4d0dde267bac"
TRACE = REPO / "evidence/portfolio-assistant/steps1-3-producer/fresh-live-rpc-trace.json"
ROWS = json.loads(TRACE.read_text())
LOCK = threading.Lock()
LAST_LIVE = 0.0
LIVE_SECONDS = 25
RPC_BYTES = 65536
WORKER_COMMAND = [sys.executable, '-B', str(ROOT / 'server.py'), '--worker']


def bounded_rpc(method, params):
    if method not in {'eth_chainId', 'eth_blockNumber', 'eth_getCode', 'eth_getBalance', 'eth_call'}:
        raise ValueError('Read-only method required')
    request = Request(portfolio.RPC, json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(), {'Content-Type': 'application/json'})
    with urlopen(request, timeout=5) as response:
        raw = response.read(RPC_BYTES + 1)
    if len(raw) > RPC_BYTES:
        raise OSError('RPC response too large')
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get('id') != 1 or 'error' in data or 'result' not in data:
            raise ValueError('RPC response invalid')
        return data['result']
    except (ValueError, RecursionError) as exc:
        raise OSError('RPC response invalid') from exc


def worker():
    try:
        result = portfolio.answer(WALLET, sys.stdin.read(241), bounded_rpc)
        print(json.dumps(result))
    except Exception:
        raise SystemExit(1)  # Parent reports only fixed, redacted unavailability.


def live_answer(question):
    # ponytail: one disposable process per live read; OS kill reclaims blocked DNS/TLS/read.
    process = subprocess.Popen(WORKER_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT)
    try:
        output, _ = process.communicate(question.encode(), timeout=LIVE_SECONDS)
    except BaseException:
        process.kill()
        process.communicate()
        raise OSError('Live read unavailable') from None
    if process.returncode or len(output) > RPC_BYTES:
        raise OSError('Live read unavailable')
    return json.loads(output)


def replay():
    rows = iter(ROWS)
    def call(method, params):
        row = next(rows)
        if (method, params) != (row["method"], row["params"]):
            raise ValueError("Recorded RPC request mismatch")
        return row["result"]
    return call


def query(question, mode):
    global LAST_LIVE
    if not isinstance(question, str) or not question.strip() or len(question) > 240:
        raise ValueError("Question must contain 1–240 characters")
    if mode not in {"recorded", "live"}:
        raise ValueError("Mode must be recorded or live")
    # Validate scope through original parser before any network access.
    result = portfolio.answer(WALLET, question, replay())
    if mode == "live":
        if not LOCK.acquire(blocking=False):
            raise BlockingIOError("Live read busy; use recorded mode or try later")
        try:
            now = time.monotonic()
            if now - LAST_LIVE < 30:
                raise BlockingIOError("Live reads limited to one per 30 seconds; recorded mode remains available")
            LAST_LIVE = now
            result = live_answer(question)
        finally:
            LOCK.release()
    return {"mode": mode, "provenance": "Saved RPC trace; original Python parser executes per question. Not a fresh network read." if mode == "recorded" else "Fresh fixed-endpoint RPC reads; unavailable fields stay unknown. Block number pinned, block-hash finality not verified.", "answer": result}


class ThreadingHTTPServer(StdlibHTTPServer):
    request_queue_size = 8
    daemon_threads = False

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(8)
        self.admitted = deque()
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        # ponytail: one process, 32 admissions per rolling 10 seconds; shared budget if scaled.
        now = time.monotonic()
        while self.admitted and self.admitted[0] <= now - 10:
            self.admitted.popleft()
        if len(self.admitted) >= 32:
            self.shutdown_request(request)
            return
        self.admitted.append(now)  # Charge even incomplete/invalid requests before thread creation.
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        pass  # Do not expose client addresses, questions or local paths on stderr.


class HeaderReader:
    def __init__(self, stream):
        self.stream = stream
        self.remaining = 8192

    def readline(self, size):
        line = self.stream.readline(min(size, self.remaining + 1))
        self.remaining -= len(line)
        if self.remaining < 0:
            raise HTTPException('Aggregate headers exceed 8192 bytes')
        return line


class Handler(BaseHTTPRequestHandler):
    timeout = 5

    def parse_request(self):
        stream = self.rfile
        self.rfile = HeaderReader(stream)
        try:
            valid = super().parse_request()
        finally:
            self.rfile = stream
        if not valid:
            return False
        self.close_connection = True  # One request per admission; no pipelining/keepalive bypass.
        if ('Transfer-Encoding' in self.headers or 'Expect' in self.headers or
                self.headers.get_all('Content-Length', []) not in ([], ['0'])):
            self.send(400, b'{"error":"Request bodies and transfer encodings forbidden"}', 'application/json')
            return False
        return True

    def setup(self):
        super().setup()
        self.arm_deadline(5)

    def arm_deadline(self, seconds):
        if hasattr(self, 'timer'):
            self.timer.cancel()
            self.timer.join()
        def close():
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.timer = threading.Timer(seconds, close)
        self.timer.start()

    def finish(self):
        try:
            super().finish()
        finally:
            self.timer.cancel()
            self.timer.join()

    server_version = "PortfolioDemo"
    sys_version = ""

    def log_message(self, *args):
        pass  # No question, IP, or local path logging.

    def send(self, status, body, content_type):
        self.arm_deadline(5)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.arm_deadline(30)
        if len(self.path) > 2048:
            return self.send(414, b'{"error":"URL too long"}', "application/json")
        url = urlsplit(self.path)
        if url.path in {"/", "/app.js", "/style.css"} and not url.query:
            filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[url.path]
            kind = {"/": "text/html", "/app.js": "text/javascript", "/style.css": "text/css"}[url.path]
            return self.send(200, (ROOT / "public" / filename).read_bytes(), kind + "; charset=utf-8")
        status, data = 404, {"error": "Not found"}
        if url.path == "/api/answer":
            args = parse_qs(url.query, keep_blank_values=True)
            try:
                if set(args) != {"question", "mode"} or any(len(v) != 1 for v in args.values()):
                    raise ValueError("Exactly one question and mode required")
                data = query(args["question"][0], args["mode"][0])
                status = 200
            except ValueError as exc:
                status, data = 400, {"error": str(exc)}
            except BlockingIOError as exc:
                status, data = 429, {"error": str(exc)}
            except (OSError, TypeError, KeyError, StopIteration):
                status, data = 503, {"error": "RPC or evidence unavailable; no values guessed. Try recorded mode."}
        self.send(status, json.dumps(data).encode(), "application/json; charset=utf-8")

    def do_POST(self):
        self.send(405, b'{"error":"Read-only GET routes only"}', "application/json")


if __name__ == "__main__":
    if sys.argv[1:] == ['--worker']:
        worker()
        raise SystemExit(0)
    # ponytail: one live read at a time, one process; shared quota store if scaling beyond free demo.
    ThreadingHTTPServer((os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8765"))), Handler).serve_forever()
