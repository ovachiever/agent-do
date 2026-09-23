"""Use the supported browse CLI; no separate browser or CDP implementation."""
import base64
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import uuid

TOOL = Path(__file__).resolve().parent
ROOT = TOOL.parent.parent


class DesignError(RuntimeError):
    pass


class PageNotReady(DesignError):
    """A failed prerequisite, with a receipt but no layout measurements."""

    def __init__(self, settle):
        super().__init__('page readiness failed: ' + settle['error'])
        self.settle = settle
        self.audit = None


def settle_options(config):
    if not isinstance(config, dict):
        raise DesignError('polish config must be a JSON object')
    options = config.get('settle', {})
    if not isinstance(options, dict) or set(options) - {'timeout_ms', 'ready_text', 'ready_js'}:
        raise DesignError('settle config accepts timeout_ms, ready_text or ready_js')
    # Same operational default as browse's context timeout; callers may override it.
    options = {'timeout_ms': 60000, **options}
    if type(options['timeout_ms']) is not int or options['timeout_ms'] <= 0:
        raise DesignError('settle timeout_ms must be a positive integer')
    for key in ('ready_text', 'ready_js'):
        if key in options and (not isinstance(options[key], str) or not options[key].strip()):
            raise DesignError(key + ' must be a nonempty string')
    if 'ready_text' in options and 'ready_js' in options:
        raise DesignError('choose ready_text or ready_js, not both')
    return options


def command(args, *, cwd=None, input=None):
    result = subprocess.run(args, cwd=cwd, input=input, text=True, capture_output=True)
    if result.returncode:
        raise DesignError(f'{Path(str(args[0])).name} failed (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}')
    return result.stdout


def agent_do(*args):
    return command([str(ROOT / 'agent-do'), *map(str, args)])


class Browser:
    def __init__(self, session=None):
        # Preserve the full UUID entropy in compact form for Unix socket paths.
        self.session = session or 'd-' + base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip('=')

    def call(self, *args, timeout=None):
        flags = ['--timeout', str(timeout)] if timeout is not None else []
        data = json.loads(agent_do('browse', '--session', self.session, '--json', *flags, *args))
        if data.get('success') is False:
            raise DesignError('browse failed: ' + str(data.get('error')))
        return data

    def evaluate(self, script, *, timeout=None):
        data = self.call('eval', script, timeout=timeout)
        value = data.get('data', data.get('result', data))
        if isinstance(value, dict) and 'result' in value:
            value = value['result']
        return value

    def open(self, url, viewport):
        self.call('open', url)
        self.call('viewport', *map(str, viewport))
        actual = self.evaluate('({width:innerWidth,height:innerHeight})')
        if (actual['width'], actual['height']) != tuple(viewport):
            raise DesignError('browse viewport did not take effect')

    def settle(self, options):
        started = time.monotonic()
        deadline = started + options['timeout_ms'] / 1000
        receipt = {**options, 'status': 'waiting', 'steps': []}

        def remaining():
            value = math.floor((deadline - time.monotonic()) * 1000)
            if value <= 0:
                raise DesignError('settle timeout expired')
            return value

        def wait(kind, *args):
            step = {'condition': kind, 'status': 'waiting'}
            receipt['steps'].append(step)
            before = time.monotonic()
            try:
                budget = remaining()
                step['timeout_ms'] = budget
                # The browser owns cancellation. The socket gets one extra second
                # to return its timeout error instead of abandoning the operation.
                self.call('wait', *args, '--timeout-ms', budget,
                          timeout=math.ceil(budget / 1000) + 1)
                remaining()
                step['status'] = 'passed'
            except (DesignError, OSError, ValueError) as error:
                step.update(status='failed', error=str(error))
                raise
            finally:
                step['elapsed_ms'] = round((time.monotonic() - before) * 1000)

        try:
            wait('networkidle', '--stable')
            predicate = None
            if 'ready_text' in options:
                predicate = '(document.body?.innerText || "").includes(' + json.dumps(options['ready_text']) + ')'
                condition = ('ready_text', '--text', options['ready_text'])
            elif 'ready_js' in options:
                # Require a true boolean; an accidental function/object is not readiness.
                predicate = '((' + options['ready_js'] + ') === true)'
                # Playwright evaluates a string expression as-is. Wrapping this
                # string in an arrow function would return a truthy function.
                condition = ('ready_js', '--fn', predicate)
            if predicate is not None:
                while True:
                    wait(*condition)
                    wait('networkidle', '--stable')
                    # The ready signal may have disappeared during a later request.
                    check = {'condition': 'ready_recheck', 'status': 'waiting'}
                    receipt['steps'].append(check)
                    before = time.monotonic()
                    try:
                        budget = remaining()
                        check['timeout_ms'] = budget
                        ready = self.evaluate(predicate, timeout=math.ceil(budget / 1000) + 1)
                        remaining()
                        check['status'] = 'passed' if ready is True else 'not_ready'
                    except (DesignError, OSError, ValueError) as error:
                        check.update(status='failed', error=str(error))
                        raise
                    finally:
                        check['elapsed_ms'] = round((time.monotonic() - before) * 1000)
                    if ready is True:
                        break
            receipt['status'] = 'ready'
        except (DesignError, OSError, ValueError) as error:
            receipt.update(status='failed', error=str(error))
            raise PageNotReady(receipt) from error
        finally:
            receipt['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        return receipt

    def polish(self, url, viewport, config=None):
        config={} if config is None else config
        options = settle_options(config)
        for frame in config.get('verified_frames',[]):
            raw=Path(frame['audit_path']).read_bytes();audit=json.loads(raw)
            if hashlib.sha256(raw).hexdigest()!=frame['audit_sha256'] or not audit.get('clean') or audit.get('html_sha256')!=frame['sha256']:
                raise DesignError('embedded frame proof does not match a passing source audit')
            if not any(v.get('clean') and (v['viewport']['width'],v['viewport']['height'])==(frame['width'],frame['height']) for v in audit['viewports']):
                raise DesignError('embedded frame viewport was not audited')
        self.open(url, viewport)
        try:
            settled = self.settle(options)
        except PageNotReady as error:
            error.audit = {'url': url, 'viewport': dict(zip(('width', 'height'), viewport)),
                           'session': self.session, 'clean': False, 'complete': False,
                           'measurement': 'not_run', 'findings': {}, 'settle': error.settle,
                           'error': str(error)}
            raise
        source = (TOOL / 'polish.js').read_text()
        result = self.evaluate('(' + source + ')(' + json.dumps(config) + ')')
        result['audit_sha256'] = hashlib.sha256(source.encode()).hexdigest()
        result['session'] = self.session
        result['settle'] = settled
        return result

    def screenshot(self, path):
        self.call('screenshot', str(Path(path).resolve()), '--full')
        if not Path(path).is_file():
            raise DesignError('browse returned without saving the render')

    def close(self):
        agent_do('browse', '--session', self.session, 'close')
