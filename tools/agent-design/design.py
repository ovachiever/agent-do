"""Image-first design rounds, with owner copy and measured verification."""
import argparse
import json
from pathlib import Path
import sys
from design_browser import Browser, DesignError


def viewport(value):
    try:
        w, h = map(int, value.lower().split('x'))
        if w > 0 and h > 0:
            return w, h
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('viewport must be positive WIDTHxHEIGHT')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='agent-do design', description=__doc__)
    commands = parser.add_subparsers(dest='verb', required=True)
    polish = commands.add_parser('polish', help='Measure live text, SVG, clipping, alignment and overflow')
    polish.add_argument('url')
    polish.add_argument('--session')
    polish.add_argument('--viewport', type=viewport, required=True)
    polish.add_argument('--config', type=Path, help='JSON with protected phrases and sourced alignment relationships')
    polish.add_argument('--out', type=Path)
    polish.add_argument('--render', type=Path)
    polish.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        browser = Browser(args.session)
        source = Path(args.url).expanduser()
        url = source.resolve().as_uri() if source.is_file() else args.url
        if args.out and args.out.exists():
            raise DesignError('audit output exists; choose a new receipt path')
        if args.render and args.render.exists():
            raise DesignError('render exists; choose a new render path')
        result = browser.polish(url, args.viewport, json.loads(args.config.read_text()) if args.config else {})
        if args.render:
            args.render.parent.mkdir(parents=True, exist_ok=True)
            browser.screenshot(args.render)
        output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x') as f:
                f.write(output)
        print(output if args.json else json.dumps({'clean':result['clean'],'complete':result['complete'],'counts':{k:len(v) for k,v in result['findings'].items()},'out':str(args.out) if args.out else None}))
        return 0 if result['clean'] else 1
    except (DesignError, OSError, ValueError) as exc:
        print(json.dumps({'success':False,'error':str(exc)}), file=sys.stderr)
        return 2
