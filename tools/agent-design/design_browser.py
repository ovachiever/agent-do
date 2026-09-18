"""Use the supported browse CLI; no separate browser or CDP implementation."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

TOOL = Path(__file__).resolve().parent
ROOT = TOOL.parent.parent


class DesignError(RuntimeError):
    pass


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

    def call(self, *args):
        data = json.loads(agent_do('browse', '--session', self.session, '--json', *args))
        if data.get('success') is False:
            raise DesignError('browse failed: ' + str(data.get('error')))
        return data

    def evaluate(self, script):
        data = self.call('eval', script)
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

    def polish(self, url, viewport, config=None):
        config=config or {}
        for frame in config.get('verified_frames',[]):
            raw=Path(frame['audit_path']).read_bytes();audit=json.loads(raw)
            if hashlib.sha256(raw).hexdigest()!=frame['audit_sha256'] or not audit.get('clean') or audit.get('html_sha256')!=frame['sha256']:
                raise DesignError('embedded frame proof does not match a passing source audit')
            if not any(v.get('clean') and (v['viewport']['width'],v['viewport']['height'])==(frame['width'],frame['height']) for v in audit['viewports']):
                raise DesignError('embedded frame viewport was not audited')
        self.open(url, viewport)
        source = (TOOL / 'polish.js').read_text()
        result = self.evaluate('(' + source + ')(' + json.dumps(config) + ')')
        result['audit_sha256'] = hashlib.sha256(source.encode()).hexdigest()
        result['session'] = self.session
        return result

    def screenshot(self, path):
        self.call('screenshot', str(Path(path).resolve()), '--full')
        if not Path(path).is_file():
            raise DesignError('browse returned without saving the render')

    def close(self):
        agent_do('browse', '--session', self.session, 'close')
