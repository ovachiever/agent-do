"""Sanitized fake engine/probe programs for the audiobook offline suite."""
ENGINE = r'''#!INTERPRETER
import json, os, pathlib, sys, time
args = sys.argv[1:]
if args == ["--help"]:
    print("LibationCli v14.2.2")
    sys.exit(0)
native = pathlib.Path(os.environ["LIBATION_FILES_DIR"])
mode = json.loads((native / "fake.json").read_text())
with (native / "calls.jsonl").open("a") as f:
    f.write(json.dumps(args) + "\n")
verb = args[0]
if verb == 'login-external':
    assert os.isatty(0)
    print('Open this URL in your web browser and sign in:', flush=True)
    print('https://www.amazon.com/ap/signin?code_challenge=test', flush=True)
    print('Paste URL: ', end='', flush=True)
    response = sys.stdin.readline()
    assert 'SECRET_RESPONSE' in response
    mode['authenticated'] = True
    (native / 'fake.json').write_text(json.dumps(mode))
    print('SECRET_RESPONSE', flush=True)
    sys.exit(0)
if verb == 'list-accounts':
    if mode.get('no_accounts'):
        print('No accounts configured.')
    else:
        row = 'owner@example.test\thome\t' + mode.get('marketplace', 'us') + '\tyes\t'
        row += 'yes' if mode.get('authenticated', True) else 'no'
        print(row + '\t' + mode.get('also_scans', ''))
        if mode.get('multiple_accounts'):
            print(row + '\t')
    sys.exit(0)
if mode.get('failure'):
    print(mode['failure'] + ' refresh_token=SECRET_TOKEN')
    sys.exit(3)
log = native / 'Log202610.log'
if verb == 'scan':
    rows = mode.get('rows', [{'Account': 'home', 'Locale': 'us', 'AudibleProductId': 'B123', 'Title': 'Book 日本語 ; $(no)', 'LengthInMinutes': 10}])
    if not mode.get('no_logs'):
        with log.open('a') as f:
            f.write('[ERR] Failed to scan account SECRET_TOKEN\n' if mode.get('partial') else '[INF] GetAllLibraryItems: Total count ' + str(len(rows)) + '\n')
    print('Scan complete.')
    print('Total processed: ' + str(len(rows)))
    sys.exit(0)
if verb == 'export':
    rows = mode.get('export_rows', mode.get('rows', [{'Account': 'home', 'Locale': 'us', 'AudibleProductId': 'B123', 'Title': 'Book 日本語 ; $(no)', 'LengthInMinutes': 10}]))
    pathlib.Path(args[args.index('--path')+1]).write_text(json.dumps(rows))
    sys.exit(0)
if verb == 'liberate':
    book = args[1]
    settings = dict(a.split('=',1) for i,a in enumerate(args) if i and args[i-1] == '--override')
    assert settings['AudiobookshelfEnabled'] == 'false'
    assert settings['OverwriteExisting'] == 'false'
    if mode.get('sleep'):
        time.sleep(60)
    if mode.get('no_audio'):
        sys.exit(0)
    directory = pathlib.Path(settings['Books']) / book
    directory.mkdir(parents=True, exist_ok=True)
    suffix = '.mp3' if settings['DecryptToLossy'] == 'true' else '.m4b'
    (directory / (book + suffix)).write_bytes(b'bad' if mode.get('bad_audio') else b'valid audio data')
    if mode.get('failed_after_output'):
        print('ERROR: interrupted after output SECRET_TOKEN')
        sys.exit(3)
    sys.exit(0)
raise AssertionError(args)
'''
PROBE = r'''#!INTERPRETER
import json, os, pathlib, sys
path = pathlib.Path(sys.argv[-1])
if path.read_bytes().startswith(b'bad'):
    print('SECRET_TOKEN', file=sys.stderr)
    sys.exit(1)
mode = os.environ.get('PROBE_MODE', '')
if mode == 'invalid_json':
    print('not-json SECRET_TOKEN')
    sys.exit(0)
print(json.dumps({'format': {'duration': '0' if mode == 'zero' else '1' if mode == 'short' else '600', 'format_name': 'mp3' if path.suffix == '.mp3' else 'mov,mp4,m4a,3gp,3g2,mj2'}, 'streams': [] if mode == 'no_audio' else [{'codec_type': 'audio'}], 'chapters': [] if mode == 'no_chapters' else [{'id': 1}, {'id': 2}]}))
'''
DECODE = r'''#!INTERPRETER
import os, sys
print('SECRET_TOKEN', file=sys.stderr)
sys.exit(int(os.environ.get('DECODE_CODE', '0')))
'''
