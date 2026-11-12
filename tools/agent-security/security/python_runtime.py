"""Explicit isolated CPython observation; upstream versions are not vendor patch status."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace

from .model import now
from .scan import run

PROBE = '''import sys,json
v=sys.version_info
print(json.dumps({"implementation":sys.implementation.name,"version":"%d.%d.%d"%v[:3],"releaselevel":v.releaselevel,"serial":v.serial,"executable":sys.executable,"platform":sys.platform}))'''


def canonical_cpe(parts):
    """NVD historically used python:python for the CPython reference runtime."""
    parts = parts[:]
    if [p.lower() for p in parts[2:4]] == ['a', 'python'] and parts[4].lower() in {'python', 'cpython'}:
        parts[2:5] = ['a', 'python', 'cpython']
    return parts


def is_cpython(parts):
    return canonical_cpe(parts)[2:5] == ['a', 'python', 'cpython']


def probe(args):
    executable = shutil.which(args.python or sys.executable)
    if not executable:
        raise ValueError('Python executable not found; select --python PATH with --local-python')
    executable = str(Path(executable).absolute())
    # -I ignores PYTHONPATH/PYTHONSTARTUP and excludes the checkout from sys.path;
    # -S skips sitecustomize/usercustomize and installed .pth execution.
    result = run([executable, '-I', '-S', '-c', PROBE],
                 SimpleNamespace(scan_timeout=args.probe_timeout, max_bytes=args.max_bytes))
    if result.returncode != 0:
        raise ValueError('Python runtime probe failed; raw diagnostics are not persisted')
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Python probe returned invalid JSON; raw diagnostics are not persisted') from exc
    if (not isinstance(value, dict) or set(value) != {'implementation', 'version', 'releaselevel', 'serial', 'executable', 'platform'}
            or any(not isinstance(value.get(k), str) or not value[k] for k in ('implementation', 'version', 'releaselevel', 'executable', 'platform'))
            or not re.fullmatch(r'\d+\.\d+\.\d+', value['version'])
            or value['releaselevel'] not in {'alpha', 'beta', 'candidate', 'final'}
            or not isinstance(value['serial'], int) or isinstance(value['serial'], bool) or value['serial'] < 0):
        raise ValueError('Python probe returned unsupported identity fields')
    component = {'id': 'local-python', 'python': value,
                 'identity_source': 'cpython_implementation_mapping' if value['implementation'] == 'cpython' else 'unmapped_python_implementation',
                 'evidence': {'kind': 'local_python_probe', 'source': executable, 'observed_at': now(),
                              'verification': 'observed_local_process'},
                 'build_provenance': 'caller_verified_upstream' if args.python_upstream else 'vendor_patches_unknown'}
    # Never round an alpha/beta/RC interpreter up to the final release.
    if value['implementation'] == 'cpython' and value['releaselevel'] == 'final':
        component['cpe'] = 'cpe:2.3:a:python:cpython:' + value['version'] + ':*:*:*:*:*:*:*'
    return component
