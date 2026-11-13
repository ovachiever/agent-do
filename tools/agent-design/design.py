"""Image-first design rounds, with owner copy and measured verification."""
import argparse
import json
from pathlib import Path
import sys
from design_browser import Browser, DesignError, PageNotReady, settle_options
from design_contract import compile_contract, prompts, validate_prompts
from design_state import Round
from design_imagine import imagine
from design_measure import measure
from design_reproduce import reproduce
from design_ballot import prepare_ballot,import_ruling


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
    image.add_argument('--size', help='WIDTHxHEIGHT within current provider limits; defaults to maximum area at the brief aspect ratio')
    image.add_argument('--dry-run', action='store_true')
    image.add_argument('--retry-uncertain', action='store_true', help='Explicitly issue replacements for requests whose outcome was lost')
    image.add_argument('--json', action='store_true')
    measurement = commands.add_parser('measure', help='Measure selected image pixels and OCR geometry; retain unknown fields as null')
    measurement.add_argument('--round', type=Path, required=True)
    measurement.add_argument('--regions', type=Path, help='Optional sourced image-pixel region annotations keyed by selected image ID')
    measurement.add_argument('--selected', action='store_true', help='Only owner-selected images are ever measured')
    measurement.add_argument('--dry-run', action='store_true')
    measurement.add_argument('--json', action='store_true')
    builder = commands.add_parser('reproduce', help='Build each chosen image with the strongest vision model; repair until live checks pass')
    builder.add_argument('--round', type=Path, required=True)
    builder.add_argument('--selected', action='store_true', help='Only owner-selected images are ever built')
    builder.add_argument('--dry-run', action='store_true')
    builder.add_argument('--retry-uncertain', action='store_true')
    builder.add_argument('--json', action='store_true')
    ballot = commands.add_parser('ballot', help='Hand a blind image/page ballot to Claude; import its verbatim Artifact readback')
    ballot.add_argument('kind', choices=('images','pages'))
    ballot.add_argument('--round', type=Path, required=True)
    ballot.add_argument('--claude-session')
    ballot.add_argument('--prepare-only', action='store_true', help='Build and audit the publication payload without notifying a peer')
    ballot.add_argument('--publish', action='store_true', help='Prepare and hand off to Claude; this tool returns ballot pending')
    ballot.add_argument('--submitted', type=Path, help='Exact HTML returned by Claude Artifact read')
    ballot.add_argument('--receipt', type=Path, help='Claude read receipt with URL, version, hashes and explicit selection evidence')
    ballot.add_argument('--dry-run', action='store_true')
    ballot.add_argument('--json', action='store_true')
    polish = commands.add_parser('polish', help='Measure live text, SVG, clipping, alignment and overflow')
    polish.add_argument('url')
    polish.add_argument('--session')
    polish.add_argument('--viewport', type=viewport, required=True)
    polish.add_argument('--config', type=Path, help='JSON with protected phrases and sourced alignment relationships')
    ready = polish.add_mutually_exclusive_group()
    ready.add_argument('--ready-text', help='Literal rendered text that must appear before measurement')
    ready.add_argument('--ready-js', help='Read-only JavaScript boolean expression that must become true')
    polish.add_argument('--settle-timeout-ms', type=int, help='Total readiness wait budget in milliseconds (default: 60000)')
    polish.add_argument('--out', type=Path)
    polish.add_argument('--render', type=Path)
    polish.add_argument('--json', action='store_true')
    polish.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.verb == 'ballot':
            if bool(args.submitted)!=bool(args.receipt):raise DesignError('--submitted and --receipt are required together')
            if args.publish and args.submitted:raise DesignError('choose handoff or ruling import, not both')
            with Round(args.round) as record:
                result=import_ruling(record,args.kind,args.submitted,args.receipt,args.dry_run) if args.submitted else prepare_ballot(record,args.kind,args.claude_session,args.dry_run,prepare_only=args.prepare_only)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        if args.verb == 'reproduce':
            with Round(args.round) as record:
                result=reproduce(record,args.dry_run,args.retry_uncertain)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        if args.verb == 'measure':
            with Round(args.round) as record:
                result=measure(record,json.loads(args.regions.read_text()) if args.regions else None,args.dry_run)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        if args.verb == 'imagine':
            with Round(args.round) as record:
                result=imagine(record,args.per_level,args.size,args.dry_run,args.retry_uncertain)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        if args.verb == 'brief':
            copy=args.copy.read_text();raw_facts=args.facts.read_text();facts=json.loads(raw_facts)
            if args.dry_run:
                contract=compile_contract(copy,facts,str(args.facts.resolve()))
                result={'dry_run':True,'round':str(args.round),'paragraphs':len(contract['paragraphs']),
                        'nodes':len(contract['nodes']),'levels':list(prompts(copy,contract)),'prompt_characters':validate_prompts(prompts(copy,contract)),'paid_requests':0}
            else:
                with Round(args.round,create=True) as record:
                    result=record.initialize(copy,facts,str(args.facts.resolve()),raw_facts)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        config = json.loads(args.config.read_text()) if args.config else {}
        options = settle_options(config)
        if args.ready_text is not None:
            options.pop('ready_js', None)
            options['ready_text'] = args.ready_text
        if args.ready_js is not None:
            options.pop('ready_text', None)
            options['ready_js'] = args.ready_js
        if args.settle_timeout_ms is not None:
            options['timeout_ms'] = args.settle_timeout_ms
        config['settle'] = options
        options = settle_options(config)
        source = Path(args.url).expanduser()
        url = source.resolve().as_uri() if source.is_file() else args.url
        if args.out and args.out.exists():
            raise DesignError('audit output exists; choose a new receipt path')
        if args.render and args.render.exists():
            raise DesignError('render exists; choose a new render path')
        if args.dry_run:
            print(json.dumps({'dry_run':True,'url':url,'viewport':args.viewport,'settle':options,'paid_requests':0,'operation':'browse live polish and optional render'}));return 0
        browser = Browser(args.session)
        result = None
        try:
            result = browser.polish(url, args.viewport, config)
            if args.render:
                args.render.parent.mkdir(parents=True, exist_ok=True)
                browser.screenshot(args.render)
        except PageNotReady as error:
            result = error.audit
        finally:
            if not args.session:
                try:
                    browser.close()
                except (DesignError, OSError, ValueError) as error:
                    if result is None or result.get('measurement') != 'not_run':
                        raise
                    result['cleanup_error'] = str(error)
        output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x') as f:
                f.write(output)
        print(output if args.json else json.dumps({'clean':result['clean'],'complete':result['complete'],'counts':{k:len(v) for k,v in result['findings'].items()},'settle':result['settle'],'error':result.get('error'),'out':str(args.out) if args.out else None}))
        if result.get('measurement') == 'not_run':
            return 2
        return 0 if result['clean'] else 1
    except (DesignError, OSError, ValueError) as exc:
        print(json.dumps({'success':False,'error':str(exc)}), file=sys.stderr)
        return 2
