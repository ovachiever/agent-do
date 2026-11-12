"""Readiness orchestration/CLI tests with explicit transport fixtures, no browser."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1]
ROOT = TOOL.parents[1]
sys.path.insert(0, str(TOOL))
import design
from design_browser import Browser, DesignError, PageNotReady, settle_options


class Clock:
    now = 0

    def __call__(self):
        return self.now


class TransportFixture(Browser):
    """Exercises production orchestration, never supplies live acceptance evidence."""

    def __init__(self, *, failure=None, checks=(True,), step_ms=25):
        super().__init__('readiness-unit-fixture')
        self.clock = Clock()
        self.calls = []
        self.failure = failure
        self.checks = iter(checks)
        self.step_ms = step_ms
        self.measured = False
        self.closed = False

    def call(self, *args, timeout=None):
        self.calls.append((args, timeout))
        self.clock.now += self.step_ms / 1000
        if args[0] == 'wait':
            if args[1] == self.failure:
                raise DesignError('native wait timeout')
            return {'success': True, 'data': {'waited': True}}
        if args[0] == 'eval':
            if args[1] == '({width:innerWidth,height:innerHeight})':
                value = {'width': 800, 'height': 600}
            elif args[1].startswith('(/* Mechanical layout audit.'):
                self.measured = True
                value = {'clean': True, 'complete': True, 'findings': {}}
            else:
                value = next(self.checks)
            return {'success': True, 'data': {'result': value}}
        return {'success': True}

    def close(self):
        self.closed = True

    def polish_fixture(self, options=None):
        with patch('design_browser.time.monotonic', self.clock):
            return self.polish('https://fixture.invalid', (800, 600), {'settle': options or {}})


class SettleTests(unittest.TestCase):
    def test_default_waits_for_network_before_measurement(self):
        browser = TransportFixture()
        result = browser.polish_fixture()
        self.assertTrue(browser.measured)
        self.assertEqual(result['settle']['status'], 'ready')
        self.assertEqual(result['settle']['elapsed_ms'], 25)
        self.assertEqual([s['condition'] for s in result['settle']['steps']], ['networkidle'])
        self.assertLess(next(i for i, c in enumerate(browser.calls) if c[0][0] == 'wait'), len(browser.calls) - 1)

    def test_text_readiness_survives_second_network_wait(self):
        browser = TransportFixture()
        result = browser.polish_fixture({'ready_text': 'Done "loading"\nnow', 'timeout_ms': 2000})
        waits = [args for args, _ in browser.calls if args[0] == 'wait']
        self.assertEqual([w[1] for w in waits], ['--stable', '--text', '--stable'])
        self.assertEqual(waits[1][2], 'Done "loading"\nnow')
        self.assertTrue(all(a[-1] > b[-1] for a, b in zip(waits, waits[1:])))
        self.assertTrue(all(s['status'] == 'passed' for s in result['settle']['steps']))

    def test_javascript_requires_boolean_and_rechecks_readiness(self):
        browser = TransportFixture(checks=(False, True))
        result = browser.polish_fixture({'ready_js': 'window.ready === true'})
        waits = [args for args, _ in browser.calls if args[0] == 'wait']
        self.assertEqual([w[1] for w in waits], ['--stable', '--fn', '--stable', '--fn', '--stable'])
        self.assertEqual(waits[1][2], '((window.ready === true) === true)')
        checks = [s for s in result['settle']['steps'] if s['condition'] == 'ready_recheck']
        self.assertEqual([s['status'] for s in checks], ['not_ready', 'passed'])
        self.assertEqual(result['settle']['ready_js'], 'window.ready === true')
        self.assertTrue(browser.measured)

    def test_network_failure_blocks_measurement_and_records_wait(self):
        browser = TransportFixture(failure='--stable')
        with self.assertRaises(PageNotReady) as raised:
            browser.polish_fixture()
        self.assertFalse(browser.measured)
        audit = raised.exception.audit
        self.assertFalse(audit['clean'])
        self.assertFalse(audit['complete'])
        self.assertEqual(audit['measurement'], 'not_run')
        self.assertEqual(audit['settle']['steps'][0]['status'], 'failed')
        self.assertEqual(audit['settle']['elapsed_ms'], 25)

    def test_missing_ready_signal_blocks_measurement(self):
        for flag, options in [('--text', {'ready_text': 'Ready'}), ('--fn', {'ready_js': 'false'})]:
            with self.subTest(flag=flag):
                browser = TransportFixture(failure=flag)
                with self.assertRaises(PageNotReady) as raised:
                    browser.polish_fixture(options)
                self.assertFalse(browser.measured)
                self.assertEqual(raised.exception.settle['steps'][-1]['status'], 'failed')

    def test_all_waits_share_one_deadline(self):
        browser = TransportFixture(step_ms=40)
        with self.assertRaises(PageNotReady) as raised:
            browser.polish_fixture({'ready_text': 'Ready', 'timeout_ms': 100})
        self.assertFalse(browser.measured)
        self.assertIn('timeout expired', str(raised.exception))
        self.assertEqual(raised.exception.settle['elapsed_ms'], 120)

    def test_invalid_config_never_opens_browser(self):
        for config in [[], {'settle': []}, {'settle': {'ready_text': ''}},
                       {'settle': {'ready_js': '  '}}, {'settle': {'timeout_ms': 0}},
                       {'settle': {'timeout_ms': True}}, {'settle': {'timeout_ms': 1.5}},
                       {'settle': {'ready_text': 'Ready', 'ready_js': 'true'}},
                       {'settle': {'unknown': True}}]:
            with self.subTest(config=config):
                browser = TransportFixture()
                with self.assertRaises(DesignError):
                    browser.polish('https://fixture.invalid', (800, 600), config)
                self.assertEqual(browser.calls, [])

    def test_native_wait_timeout_gets_transport_response_allowance(self):
        with patch('design_browser.agent_do', return_value='{"success":true}') as cli:
            Browser('fixture').call('wait', '--stable', '--timeout-ms', 1000, timeout=2)
        cli.assert_called_once_with('browse', '--session', 'fixture', '--json', '--timeout', '2', 'wait', '--stable', '--timeout-ms', 1000)


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = design.main(['polish', 'https://fixture.invalid', '--viewport', '800x600', *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_dry_run_validates_without_constructing_browser(self):
        with patch.object(design, 'Browser') as browser:
            code, output, _ = self.invoke('--dry-run', '--ready-text', 'Ready', '--settle-timeout-ms', '1234')
        self.assertEqual(code, 0)
        browser.assert_not_called()
        self.assertEqual(json.loads(output)['settle'], {'ready_text': 'Ready', 'timeout_ms': 1234})

    def test_invalid_timeout_dry_run_fails_without_browser(self):
        with patch.object(design, 'Browser') as browser:
            code, _, error = self.invoke('--dry-run', '--settle-timeout-ms', '0')
        self.assertEqual(code, 2)
        self.assertIn('positive integer', error)
        browser.assert_not_called()

    def test_cli_overrides_config_ready_kind(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.dev') as tmp:
            config = Path(tmp) / 'config.json'
            config.write_text(json.dumps({'settle': {'ready_js': 'window.ready', 'timeout_ms': 4567}}))
            code, output, _ = self.invoke('--dry-run', '--config', str(config), '--ready-text', 'Ready')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['settle'], {'ready_text': 'Ready', 'timeout_ms': 4567})

    def test_failed_wait_saves_receipt_without_render_and_closes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.dev') as tmp:
            browser = TransportFixture(failure='--text')
            audit, render = Path(tmp) / 'audit.json', Path(tmp) / 'render.png'
            with patch.object(design, 'Browser', return_value=browser), patch('design_browser.time.monotonic', browser.clock):
                code, output, _ = self.invoke('--ready-text', 'Ready', '--out', str(audit), '--render', str(render), '--json')
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(audit.read_text()), json.loads(output))
            self.assertFalse(render.exists())
            self.assertFalse(browser.measured)
            self.assertTrue(browser.closed)

    def test_close_failure_does_not_erase_failed_wait_receipt(self):
        browser = TransportFixture(failure='--stable')
        with patch.object(design, 'Browser', return_value=browser), patch('design_browser.time.monotonic', browser.clock), patch.object(browser, 'close', side_effect=DesignError('close failed')):
            code, output, _ = self.invoke('--json')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['cleanup_error'], 'close failed')

    def test_existing_receipt_refused_without_browser(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.dev') as tmp:
            audit = Path(tmp) / 'audit.json'
            audit.write_text('original')
            with patch.object(design, 'Browser') as browser:
                code, _, _ = self.invoke('--out', str(audit))
            self.assertEqual(audit.read_text(), 'original')
        self.assertEqual(code, 2)
        browser.assert_not_called()

    def test_successful_audit_has_readiness_in_summary(self):
        browser = TransportFixture()
        with patch.object(design, 'Browser', return_value=browser), patch('design_browser.time.monotonic', browser.clock):
            code, output, _ = self.invoke('--session', 'fixture')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['settle']['status'], 'ready')
        self.assertFalse(browser.closed)


class WaitCommandTests(unittest.TestCase):
    def build(self, *args):
        # Source definitions only. No main(), daemon preflight, or browser call.
        script = 'source <(sed \'$d\' "$1"); shift; build_wait_cmd "$@"'
        return subprocess.run(['bash', '-c', script, 'fixture', str(ROOT / 'tools/agent-browse/agent-browse'), *args],
                              capture_output=True, text=True, env=os.environ.copy())

    def test_wait_conditions_are_json_encoded_and_bounded(self):
        cases = [('--text', 'Ready "now"\\next\nline', 'text'),
                 ('--fn', '() => window.ready === "yes"', 'expression'),
                 ('--url', '**/ready?value="yes"', 'url')]
        for flag, value, field in cases:
            with self.subTest(flag=flag):
                result = self.build(flag, value, '--timeout-ms', '1234')
                self.assertEqual(result.returncode, 0, result.stderr)
                command = json.loads(result.stdout)
                self.assertEqual(command[field], value)
                self.assertEqual(command['timeout'], 1234)
                self.assertEqual(command['action'], 'waitforfunction' if flag == '--fn' else 'wait')

    def test_network_selector_and_duration(self):
        for args, expected in [(('--stable', '--timeout-ms', '2345'), {'state': 'networkidle', 'timeout': 2345}),
                               (('[data-ready="yes"]',), {'selector': '[data-ready="yes"]'}),
                               (('20',), {'timeout': 20})]:
            result = self.build(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            command = json.loads(result.stdout)
            for key, value in expected.items():
                self.assertEqual(command[key], value)

    def test_invalid_waits_are_refused(self):
        for args in [(), ('--text',), ('--fn', ''), ('--stable', '--timeout-ms', '0'),
                     ('--stable', '--timeout-ms', 'NaN'), ('--unknown',), ('10', '--timeout-ms', '20')]:
            with self.subTest(args=args):
                result = self.build(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    (ROOT / '.dev').mkdir(exist_ok=True)
    unittest.main()
