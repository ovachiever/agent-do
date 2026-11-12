"""Live acceptance through agent-do browse. Run only in a coordinated browser lane."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import unittest
import uuid

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))
from design_browser import Browser, PageNotReady


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/slow':
            time.sleep(2)
            content = 'Complete.'.encode()
            kind = 'text/plain'
        else:
            scripts = {
                '/network': "fetch('/slow').then(r=>r.text()).then(text=>document.querySelector('p').textContent=text)",
                '/text': "setTimeout(()=>document.querySelector('p').textContent='Ready now.', 2500)",
                '/js': "setTimeout(()=>{document.querySelector('p').textContent='Ready now.'; window.appReady=true}, 2500)",
                '/never': '',
            }
            if self.path not in scripts:
                self.send_error(404)
                return
            content = ('<!doctype html><meta charset="utf-8"><p>Assembling</p><script>'
                       + scripts[self.path] + '</script>').encode()
            kind = 'text/html; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass


class ReadinessBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipts = TOOL.parents[1] / '.dev' / ('design-readiness-' + uuid.uuid4().hex)
        cls.receipts.mkdir(parents=True)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.browser = Browser()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
        finally:
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join()
            print('Readiness receipts: ' + str(cls.receipts))

    def audit(self, path, **settle):
        receipt = self.receipts / (self._testMethodName + '.json')
        try:
            result = self.browser.polish(self.url + path, (800, 600),
                                         {'settle': {'timeout_ms': 15000, **settle}})
        except PageNotReady as error:
            receipt.write_text(json.dumps(error.audit, indent=2) + '\n')
            raise
        receipt.write_text(json.dumps(result, indent=2) + '\n')
        return result

    def test_network_idle_waits_for_pending_fetch(self):
        result = self.audit('/network')
        self.assertEqual(result['text']['rendered'].strip(), 'Complete.')
        self.assertEqual(result['settle']['status'], 'ready')
        self.assertEqual(result['settle']['steps'][0]['condition'], 'networkidle')

    def test_delayed_text_is_measured_instead_of_skeleton(self):
        result = self.audit('/text', ready_text='Ready now.')
        self.assertEqual(result['text']['rendered'].strip(), 'Ready now.')
        self.assertNotIn('Assembling', result['text']['rendered'])
        self.assertEqual([s['condition'] for s in result['settle']['steps']],
                         ['networkidle', 'ready_text', 'networkidle', 'ready_recheck'])

    def test_delayed_boolean_predicate(self):
        result = self.audit('/js', ready_js='window.appReady === true')
        self.assertEqual(result['text']['rendered'].strip(), 'Ready now.')
        self.assertEqual(result['settle']['ready_js'], 'window.appReady === true')
        self.assertGreater(result['settle']['elapsed_ms'], 0)

    def test_missing_marker_stops_with_failed_receipt(self):
        with self.assertRaises(PageNotReady) as raised:
            self.audit('/never', ready_text='Ready now.', timeout_ms=2500)
        self.assertFalse(raised.exception.audit['complete'])
        self.assertEqual(raised.exception.audit['measurement'], 'not_run')
        self.assertEqual(raised.exception.settle['status'], 'failed')
        self.assertEqual(raised.exception.settle['steps'][-1]['condition'], 'ready_text', raised.exception.audit)

    def test_predicate_error_cannot_produce_measurements(self):
        with self.assertRaises(PageNotReady) as raised:
            self.audit('/never', ready_js='window.missing.field === true')
        self.assertEqual(raised.exception.audit['measurement'], 'not_run')
        self.assertEqual(raised.exception.settle['steps'][-1]['condition'], 'ready_js', raised.exception.audit)


if __name__ == '__main__':
    unittest.main()
