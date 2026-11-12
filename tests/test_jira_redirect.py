#!/usr/bin/env python3
"""Ensure authenticated Jira requests cannot redirect credentials off-origin."""
import http.server
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/agent-jira'))
from jira_ops import JiraClient


class RedirectTest(unittest.TestCase):
    def test_cross_origin_rejected_and_same_origin_allowed(self):
        received = []

        class Destination(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get('Authorization'))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')

            def log_message(self, *args):
                pass

        dest = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Destination)

        class Source(Destination):
            def do_GET(self):
                if self.path == '/safe':
                    return super().do_GET()
                self.send_response(302)
                self.send_header('Location', '/safe' if self.path == '/same' else
                                 f'http://127.0.0.1:{dest.server_port}/stolen')
                self.end_headers()

        source = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Source)
        for server in (dest, source):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        client = JiraClient(f'http://127.0.0.1:{source.server_port}', 'test@example.com', 'test-token')
        base = f'http://127.0.0.1:{source.server_port}'
        self.assertEqual(client.request('GET', base + '/same'), {})
        self.assertTrue(received.pop().startswith('Basic '))
        result = client.request('GET', base + '/cross', suppress_errors=True)
        self.assertEqual(result['status'], 302)
        self.assertEqual(received, [])


if __name__ == '__main__':
    unittest.main()
