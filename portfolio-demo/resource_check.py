"""Bounded loopback regressions; run normally and with -O. No public RPC."""
import json
import socket
import threading
import time
import unittest
from urllib.request import urlopen
import server


class ResourceChecks(unittest.TestCase):
    def test_client_slots_and_header_deadline(self):
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever)
        thread.start()
        sockets = []
        baseline = threading.active_count()
        started = time.monotonic()
        try:
            for _ in range(9):
                sock = socket.create_connection(http.server_address, timeout=2)
                sockets.append(sock)
                sock.sendall(b'GET / HTTP/1.1\r\nX-Test: ')
            time.sleep(.2)
            self.assertLessEqual(threading.active_count() - baseline, 16, 'unbounded client workers')
            sockets[-1].settimeout(1)
            self.assertEqual(sockets[-1].recv(1), b'', 'ninth client must close without worker')
            def trickle():
                for _ in range(60):
                    try:
                        sockets[1].sendall(b'x')
                    except OSError:
                        break
                    time.sleep(.1)
            sender = threading.Thread(target=trickle)
            sender.start()
            start = time.monotonic()
            sockets[0].settimeout(7)
            self.assertEqual(sockets[0].recv(1), b'')
            self.assertEqual(sockets[1].recv(1), b'')
            sender.join(2)
            self.assertFalse(sender.is_alive())
            self.assertLess(time.monotonic() - start, 6)
            print(json.dumps({'header_closed_seconds': time.monotonic() - started, 'worker_cap': 8, 'timer_cap': 8}))
            for _ in range(100):
                if http.slots._value == 8:
                    break
                time.sleep(.01)
            self.assertEqual(http.slots._value, 8)
            with urlopen('http://127.0.0.1:' + str(http.server_port), timeout=2) as response:
                self.assertEqual(response.status, 200)
        finally:
            for sock in sockets:
                sock.close()
            http.shutdown()
            http.server_close()
            thread.join(3)
        self.assertFalse(thread.is_alive())


    def test_rpc_total_deadline_and_bytes(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from unittest.mock import patch
        import sys
        class RPC(BaseHTTPRequestHandler):
            mode = 'trickle'
            calls = []
            closed = threading.Event()
            def log_message(self, *args):
                pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.calls.append(payload['method'])
                self.send_response(200)
                self.end_headers()
                try:
                    if self.mode == 'stall':
                        time.sleep(2)
                        self.wfile.write(b' ')
                    elif self.mode == 'replay':
                        row = server.ROWS[len(self.calls) - 1]
                        result = row['result']
                        if row['method'] == 'eth_call' and row['params'][0]['to'] == server.portfolio.VAULTS['RockawayX'] and row['params'][0]['data'].startswith('0x07a2d13a'):
                            result = None
                        self.wfile.write(json.dumps({'id': 1, 'result': result}).encode())
                    elif self.mode == 'large':
                        self.wfile.write(json.dumps({'id': 1, 'result': 'x' * 65536}).encode())
                    else:
                        for _ in range(100):
                            self.wfile.write(b' ')
                            self.wfile.flush()
                            time.sleep(.03)
                except (BrokenPipeError, ConnectionResetError):
                    self.closed.set()
        rpc = ThreadingHTTPServer(('127.0.0.1', 0), RPC)
        thread = threading.Thread(target=rpc.serve_forever)
        thread.start()
        command = [sys.executable, '-B', '-c',
                   'import server; server.portfolio.RPC=' + repr('http://127.0.0.1:' + str(rpc.server_port)) + '; server.worker()']
        try:
            for mode in ['stall', 'trickle', 'large']:
                RPC.mode = mode
                children = []
                original_popen = server.subprocess.Popen
                def spawn(*args, **kwargs):
                    child = original_popen(*args, **kwargs)
                    children.append(child)
                    return child
                start = time.monotonic()
                with patch.object(server.subprocess, 'Popen', spawn), patch.object(server.portfolio, 'RPC', 'http://127.0.0.1:' + str(rpc.server_port)), patch.object(server, 'WORKER_COMMAND', command, create=True), patch.object(server, 'LIVE_SECONDS', 1.2, create=True):
                    server.LAST_LIVE = 0
                    with self.assertRaises(OSError):
                        server.query('balances', 'live')
                self.assertLess(time.monotonic() - start, 2.2)
                self.assertFalse(server.LOCK.locked())
                self.assertTrue(children and all(child.poll() is not None for child in children))
                print(json.dumps({'mode': mode, 'elapsed_seconds': time.monotonic() - start, 'deadline_seconds': 1.2, 'children_reaped': True}))
                if mode == 'trickle':
                    self.assertTrue(RPC.closed.wait(2), 'worker socket not reclaimed')
                if mode == 'large':
                    with patch.object(server.portfolio, 'RPC', 'http://127.0.0.1:' + str(rpc.server_port)):
                        with self.assertRaisesRegex(OSError, 'too large'):
                            server.bounded_rpc('eth_chainId', [])
            self.assertTrue(RPC.closed.wait(2), 'worker socket not reclaimed')
            RPC.mode = 'replay'
            RPC.calls = []
            with patch.object(server, 'WORKER_COMMAND', command):
                server.LAST_LIVE = 0
                result = server.query('exposure', 'live')
            self.assertEqual(result['mode'], 'live')
            self.assertEqual(result['answer']['total_usdc_raw']['value'], 'unknown')
            self.assertEqual(result['answer']['vaults']['RockawayX']['underlying_usdc_raw']['value'], 'unknown')
            self.assertEqual(result['answer']['vaults']['SharpByte']['underlying_usdc_raw']['value'], '0')
            self.assertEqual(len(RPC.calls), 17)
        finally:
            rpc.shutdown()
            rpc.server_close()
            thread.join(3)
        self.assertFalse(thread.is_alive())


if __name__ == '__main__':
    unittest.main()
