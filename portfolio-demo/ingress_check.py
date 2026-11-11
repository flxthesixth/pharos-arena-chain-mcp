"""Raw loopback ingress regressions; no provider, browser or public RPC."""
import socket
import threading
import unittest
from unittest.mock import patch
import server


class IngressChecks(unittest.TestCase):
    def setUp(self):
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())

    def raw(self, headers=b'', path=b'/', method=b'GET', tail=b'', host=b'demo.onrender.com'):
        with socket.create_connection(self.http.server_address, timeout=2) as sock:
            sock.settimeout(2)
            sock.sendall(method + b' ' + path + b' HTTP/1.1\r\nHost: ' + host + b'\r\n' + headers + b'\r\n' + tail)
            data = b''
            try:
                while True:
                    part = sock.recv(65536)
                    if not part:
                        break
                    data += part
            except ConnectionResetError:
                pass  # Rejection may reset connection containing unread body bytes.
            return data

    def test_body_framing_before_all_routes(self):
        with patch.object(server, 'query', side_effect=AssertionError('query reached')) as query:
            for path, method in [(b'/', b'GET'), (b'/app.js', b'GET'), (b'/style.css', b'GET'), (b'/api/answer?question=balances&mode=live', b'GET'), (b'/missing', b'GET'), (b'/', b'POST'), (b'/', b'OPTIONS')]:
                for headers in [b'Content-Length: 1\r\n', b'Transfer-Encoding: chunked\r\n', b'Content-Length: 0\r\nContent-Length: 0\r\n']:
                    with self.subTest(path=path, method=method, headers=headers):
                        self.assertIn(b' 400 ', self.raw(headers, path, method).split(b'\r\n')[0])
            self.assertEqual(query.call_count, 0)
        for header in [b'Content-Length: -1\r\n', b'Content-Length: nope\r\n', b'Content-Length: +0\r\n', b'Transfer-Encoding:\r\n', b'Expect: 100-continue\r\n', b'Content-Length: 0\r\nTransfer-Encoding: chunked\r\n']:
            with self.subTest(header=header):
                self.assertIn(b' 400 ', self.raw(header).split(b'\r\n')[0])
        response = self.raw(b'Content-Length: 0\r\n', tail=b'GET /missing HTTP/1.1\r\n\r\n')
        self.assertIn(b' 200 ', response.split(b'\r\n')[0])
        self.assertEqual(response.count(b'HTTP/1.0 '), 1)

    def test_aggregate_headers(self):
        # Each line legal under stdlib limits; aggregate exceeds 8192 bytes.
        with patch.object(server, 'query', side_effect=AssertionError('query reached')):
            for headers in [b'X: ' + b'x' * 8192 + b'\r\n', (b'X: ' + b'x' * 1000 + b'\r\n') * 9, b'X: ok\r\n' + (b' ' + b'x' * 1000 + b'\r\n') * 9]:
                with self.subTest(length=len(headers)):
                    self.assertIn(b' 431 ', self.raw(headers).split(b'\r\n')[0])
        self.assertIn(b' 200 ', self.raw(b'X: ' + b'x' * 8000 + b'\r\n').split(b'\r\n')[0])

    def test_global_budget_precedes_work_and_ignores_host(self):
        # Fixed clock proves boundary without a ten-second sleep.
        with patch.object(server.time, 'monotonic', return_value=100):
            for i in range(32):
                self.assertIn(b' 200 ', self.raw(host=b'demo.onrender.com' if i % 2 else b'custom.example').split(b'\r\n')[0])
            with patch.object(server.Handler, 'setup', side_effect=AssertionError('handler created')) as setup, patch.object(server, 'query', side_effect=AssertionError('query reached')) as query:
                for path, method in [(b'/', b'GET'), (b'/app.js', b'GET'), (b'/style.css', b'GET'), (b'/missing', b'OPTIONS'), (b'/api/answer?question=balances&mode=live', b'GET')]:
                    self.assertEqual(self.raw(path=path, method=method, host=b'demo.onrender.com'), b'')
                self.assertEqual(setup.call_count, 0)
                self.assertEqual(query.call_count, 0)
        with patch.object(server.time, 'monotonic', return_value=109.999):
            self.assertEqual(self.raw(), b'')
        with patch.object(server.time, 'monotonic', return_value=110):
            self.assertIn(b' 200 ', self.raw().split(b'\r\n')[0])
        self.assertEqual(self.http.slots._value, 8)


if __name__ == '__main__':
    unittest.main()
