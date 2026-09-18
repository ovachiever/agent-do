"""Image-first design rounds, with owner copy and measured verification."""
import argparse
import json
from pathlib import Path
import sys
from design_browser import Browser, DesignError
from design_contract import compile_contract, prompts
from design_state import Round
from design_imagine import imagine
from design_measure import measure


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
    brief = commands.add_parser('brief', help='Freeze approved copy and node-tagged facts; emit exact, half and open image prompts')
    brief.add_argument('--copy', type=Path, required=True)
    brief.add_argument('--facts', type=Path, required=True)
    brief.add_argument('--round', type=Path, required=True)
    brief.add_argument('--dry-run', action='store_true')
    brief.add_argument('--json', action='store_true')
    image = commands.add_parser('imagine', help='Generate every requested image using refreshed strongest-model authority')
    image.add_argument('--round', type=Path, required=True)
    image.add_argument('--per-level', type=int, default=2, help='Generations per prompt level; owner trial default is 2')
    image.add_argument('--size', help='Portrait WIDTHxHEIGHT within current provider limits; defaults to maximum published area')
    image.add_argument('--dry-run', action='store_true')
    image.add_argument('--retry-uncertain', action='store_true', help='Explicitly issue replacements for requests whose outcome was lost')
    image.add_argument('--json', action='store_true')
    measurement = commands.add_parser('measure', help='Measure selected image pixels and OCR geometry; retain unknown fields as null')
    measurement.add_argument('--round', type=Path, required=True)
    measurement.add_argument('--regions', type=Path, help='Optional sourced image-pixel region annotations keyed by selected image ID')
    measurement.add_argument('--selected', action='store_true', help='Only owner-selected images are ever measured')
    measurement.add_argument('--dry-run', action='store_true')
    measurement.add_argument('--json', action='store_true')
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
        if args.verb == 'measure':
            with Round(args.round) as record:
                result=measure(record,json.loads(args.regions.read_text()) if args.regions else None,args.dry_run)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        if args.verb == 'imagine':
            with Round(args.round) as record:
                result=imagine(record,args.per_level,args.size,args.dry_run,args.retry_uncertain)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        if args.verb == 'brief':
            copy=args.copy.read_text();facts=json.loads(args.facts.read_text())
            if args.dry_run:
                contract=compile_contract(copy,facts,str(args.facts.resolve()))
                result={'dry_run':True,'round':str(args.round),'paragraphs':len(contract['paragraphs']),
                        'nodes':len(contract['nodes']),'levels':list(prompts(copy,contract)),'paid_requests':0}
            else:
                with Round(args.round,create=True) as record:
                    result=record.initialize(copy,facts,str(args.facts.resolve()))
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        browser = Browser(args.session)
        source = Path(args.url).expanduser()
        url = source.resolve().as_uri() if source.is_file() else args.url
        if args.out and args.out.exists():
            raise DesignError('audit output exists; choose a new receipt path')
        if args.render and args.render.exists():
            raise DesignError('render exists; choose a new render path')
        try:
            result = browser.polish(url, args.viewport, json.loads(args.config.read_text()) if args.config else {})
            if args.render:
                args.render.parent.mkdir(parents=True, exist_ok=True)
                browser.screenshot(args.render)
        finally:
            if not args.session:browser.close()
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
