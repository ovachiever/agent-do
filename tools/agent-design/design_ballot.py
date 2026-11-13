"""Local-only blind ballots with durable, explicit owner controls."""
import base64
from datetime import datetime
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import struct
from urllib.parse import urlparse
import uuid

from design_browser import Browser,DesignError,TOOL
from design_contract import digest
from design_provider import png_size
from design_reproduce import audit_candidate
from design_state import now,write_new

# Local review has no external publishing envelope. Tests can exercise legacy multipart splitting.
BALLOT_MAX_BYTES=None

STATE=re.compile(r'(?<=</title>)\s*<script type="application/json" id="fb-state">([\s\S]*?)</script>')


def public_png(data):
    png_size(data)
    # Keep rendering/color chunks, remove text/EXIF/time metadata without changing pixels.
    result=[data[:8]];offset=8
    keep={b'IHDR',b'PLTE',b'IDAT',b'IEND',b'tRNS',b'iCCP',b'sRGB',b'gAMA',b'cHRM',b'sBIT'}
    while offset<len(data):
        length=struct.unpack('>I',data[offset:offset+4])[0];end=offset+length+12
        if data[offset+4:offset+8] in keep:result.append(data[offset:end])
        offset=end
    return b''.join(result)


def compact_png(path,data):
    """Optional existing native codec; never resize or use lossy compression."""
    codec=shutil.which('cwebp')
    if codec is None:return data,'image/png'
    output=path.with_suffix('.webp')
    result=subprocess.run([codec,'-quiet','-lossless','-exact','-m','6','-metadata','icc',str(path),'-o',str(output)],capture_output=True)
    if result.returncode:
        raise DesignError('lossless ballot encoding failed: '+result.stderr.decode(errors='replace'))
    encoded=output.read_bytes()
    if not (encoded[:4]==b'RIFF' and encoded[8:12]==b'WEBP'):
        raise DesignError('lossless encoder did not return WebP')
    return (encoded,'image/webp') if len(encoded)<len(data) else (data,'image/png')


def validate_ballot_size(source):
    size=len(source.encode('utf-8'))
    if BALLOT_MAX_BYTES is not None and size>BALLOT_MAX_BYTES:
        raise DesignError(f'ballot exceeds the configured {BALLOT_MAX_BYTES}-byte part budget; originals preserved')
    return size


def public_html(source):
    source=re.sub(r'<!--[\s\S]*?-->','',source)
    source=re.sub(r'<title\b[^>]*>[\s\S]*?</title>','<title>Candidate</title>',source,flags=re.I)
    def meta(match):
        return match[0] if re.search(r'\bcharset\s*=|\bname\s*=\s*["\']viewport["\']',match[0],re.I) else ''
    return re.sub(r'<meta\b[^>]*>',meta,source,flags=re.I)


def make_ballot(key,candidates):
    head='''<!doctype html>
<html lang="en"><head><title>Design ballot</title><script type="application/json" id="fb-state">{"feedback":{},"submitted_at":null}</script>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html{color-scheme:dark}body{margin:0;background:#171717;color:#eee;font:16px/1.5 system-ui}
main{padding:1.5em}h1,h2{font:inherit;margin:0 0 1em}section{margin:2em 0}label{display:block;margin:1em 0 .5em}
.candidate{overflow:auto;max-width:100%;background:white}img,iframe{display:block;max-width:none;border:0}
textarea{box-sizing:border-box;display:block;width:100%;min-height:6em;background:#242424;color:#eee;border:1px solid #777;padding:1em;font:inherit}
footer{position:sticky;bottom:0;padding:1em;background:#171717;border-top:1px solid #777}button{font:inherit;padding:.5em 1em}#fb-status{margin-right:1em}</style></head><body>
<main><h1>View each candidate and leave your ruling below.</h1>'''
    parts=[head]
    for candidate in candidates:
        label=candidate['label'];field=key+'-'+label
        if candidate['kind']=='images':
            image=base64.b64encode(candidate['bytes']).decode()
            visual='<img alt="Candidate '+label+'" width="'+str(candidate['width'])+'" height="'+str(candidate['height'])+'" src="data:'+candidate.get('mime','image/png')+';base64,'+image+'">'
        else:
            visual='<iframe id="candidate-'+label+'" title="Candidate '+label+'" sandbox="allow-scripts" width="'+str(candidate['width'])+'" height="'+str(candidate['height'])+'" srcdoc="'+html.escape(candidate['html'],quote=True)+'"></iframe>'
        parts.append('<section><h2>Candidate '+label+'</h2><div class="candidate">'+visual+'</div><label for="note-'+label+'">Your note: '+label+'</label><textarea id="note-'+label+'" data-fb="'+field+'"></textarea><div hidden data-fb-saved="'+field+'"></div></section>')
    field=key+'-overall'
    parts.append('<section><label for="overall">Overall</label><textarea id="overall" data-fb="'+field+'"></textarea><div hidden data-fb-saved="'+field+'"></div></section></main><footer><span id="fb-status"></span><button id="fb-submit">Submit ruling</button></footer><script>')
    parts.append((TOOL/'ballot-runtime.js').read_text());parts.append('</script></body></html>')
    return ''.join(parts)


def ballot_parts(key,candidates):
    groups=[];current=[]
    for candidate in candidates:
        group_key=key+'-part'+str(len(groups)+1)
        if BALLOT_MAX_BYTES is not None and len(make_ballot(group_key,current+[candidate]).encode())>BALLOT_MAX_BYTES and current:
            groups.append(current);current=[]
            group_key=key+'-part'+str(len(groups)+1)
        current.append(candidate)
        validate_ballot_size(make_ballot(group_key,current))
    if current:groups.append(current)
    result=[]
    for index,group in enumerate(groups):
        part_key=key if len(groups)==1 else key+'-part'+str(index+1)
        source=make_ballot(part_key,group)
        validate_ballot_size(source)
        result.append({'file':'ballot.html' if index==0 else f'ballot-{index+1}.html',
                       'source':source,'sha256':digest(source),'fingerprint':ballot_fingerprint(source),
                       'labels':[c['label'] for c in group],
                       'keys':[part_key+'-'+c['label'] for c in group]+[part_key+'-overall']})
    return result


def advance_rulings(record,kind,ballot,ruled):
    parts=ballot.get('parts',[ballot])
    selected=[]
    for part in parts:
        latest=next((r for r in reversed(record.state.get('rulings',[]))
                     if r['stage']==kind and r.get('part_sha256',ballot['sha256'])==part['sha256']),None)
        if latest is None or latest.get('selected_labels') is None:return False
        selected.extend(latest['blind_key'][label]['id'] for label in latest['selected_labels'])
    record.state['selected_'+kind]=selected
    record.save('all ballot parts have explicit owner selections')
    record.transition(ruled)
    return True


class CanonicalHTML(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.tokens=[]
    def handle_starttag(self,tag,attrs):self.tokens.append(['start',tag,sorted((k,v if v is not None else '') for k,v in attrs)])
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs)
    def handle_endtag(self,tag):self.tokens.append(['end',tag])
    def handle_data(self,data):
        if data.strip():self.tokens.append(['data',data])
    def handle_comment(self,data):self.tokens.append(['comment',data])


def ballot_fingerprint(source):
    blanked,count=STATE.subn('<script type="application/json" id="fb-state">{}</script>',source)
    if count!=1:raise DesignError('ballot must have exactly one canonical fb-state block')
    parser=CanonicalHTML();parser.feed(blanked)
    return digest(json.dumps(parser.tokens,ensure_ascii=False))


def verify_candidates(record,kind):
    candidates=record.state[kind]
    if not candidates:raise DesignError('no candidates for '+kind+' ballot')
    for candidate in candidates:
        if digest(record.resolve(candidate['path']).read_bytes())!=candidate['sha256']:raise DesignError('candidate changed: '+candidate['id'])
        if kind=='pages':
            path=record.resolve(candidate['audit'])
            if digest(path.read_bytes())!=candidate['audit_sha256']:raise DesignError('candidate audit changed')
            audit=json.loads(path.read_text())
            if not audit['clean'] or audit['html_sha256']!=candidate['sha256']:raise DesignError('page has no current complete passing audit')
            for render in candidate['renders']:
                if digest(record.resolve(render['path']).read_bytes())!=render['sha256']:raise DesignError('candidate render changed')
    return candidates


def prepare_ballot(record,kind,dry_run=False,prepare_only=False):
    ready,pending=('images_ready','image_ballot_pending') if kind=='images' else ('pages_ready','page_ballot_pending')
    allowed=[ready,pending]
    if prepare_only and record.state['ballots'].get(kind):
        allowed+=['images_ruled','measured','pages_ready','page_ballot_pending','ruled'] if kind=='images' else ['ruled']
    record.require(*allowed);candidates=verify_candidates(record,kind)
    if dry_run:return {'dry_run':True,'stage':kind,'candidates':len(candidates),'publication':'local HTTP review and default browser','paid_requests':0,'status':'ballot pending'}
    ballot=record.state['ballots'].get(kind)
    if not ballot:
        folder=record.attempt('ballots/'+kind);key='b-'+uuid.uuid4().hex
        shuffled=list(candidates);secrets.SystemRandom().shuffle(shuffled)
        mapping={};public=[];frames=[];view=record.contract()['viewports'][0]
        for index,original in enumerate(shuffled,1):
            label=str(index);candidate={'label':label,'kind':kind}
            if kind=='images':
                data=public_png(record.resolve(original['path']).read_bytes());candidate['bytes']=data
                candidate['width'],candidate['height']=png_size(data)
                png_path=folder/('candidate-'+label+'.png');write_new(png_path,data)
                candidate['bytes'],candidate['mime']=compact_png(png_path,data)
                public_hash=digest(candidate['bytes'])
            else:
                source=public_html(record.resolve(original['path']).read_text())
                candidate.update(html=source,width=view['width'],height=view['height']);public_hash=digest(source)
                path=folder/('candidate-'+label+'.html');write_new(path,source)
                # Public bytes changed during metadata removal: inspect those bytes again.
                audit=audit_candidate(path,record.contract(),folder/('candidate-'+label+'-checks'))
                if not audit['clean']:raise DesignError('public candidate needs repair after metadata stripping; retained at '+str(path))
                frames.append({'selector':'#candidate-'+label,'sha256':public_hash,'width':view['width'],'height':view['height'],'audit_path':str(folder/('candidate-'+label+'-checks')/'audit.json'),'audit_sha256':digest((folder/('candidate-'+label+'-checks')/'audit.json').read_bytes())})
            mapping[label]={'id':original['id'],'source_sha256':original['sha256'],'public_sha256':public_hash}
            public.append(candidate)
        write_new(folder/'blind-key.json',{'sealed':True,'mapping':mapping})
        parts=ballot_parts(key,public)
        browser=Browser()
        try:
            for part in parts:
                write_new(folder/part['file'],part['source'])
                part_frames=[f for f in frames if f['selector'].split('-')[-1] in part['labels']]
                chrome=browser.polish((folder/part['file']).as_uri(),(view['width'],view['height']),{'verified_frames':part_frames})
                write_new(folder/('chrome-audit.json' if part['file']=='ballot.html' else part['file']+'.audit.json'),chrome)
                if not chrome['clean']:raise DesignError('ballot chrome did not pass live polish; evidence retained at '+str(folder))
                del part['source']
        finally:browser.close()
        ballot={'path':str(folder.relative_to(record.path)),'key':key,**parts[0],
                'parts':parts,'status':'ballot pending'}
        record.state['ballots'][kind]=ballot
        record.save('blind '+kind+' ballot prepared and mechanically checked')
    if record.state['stage']==ready:record.transition(pending)
    folder=record.resolve(ballot['path'])
    parts=ballot.get('parts',[{'file':'ballot.html',**ballot}])
    for part in parts:
        if digest((folder/part['file']).read_bytes())!=part['sha256']:raise DesignError('prepared ballot changed')
    publication=[{'path':str(folder/part['file']),'sha256':part['sha256'],'keys':part['keys'],'bytes':(folder/part['file']).stat().st_size} for part in parts]
    return {'status':'local ballot prepared','ballot':str(folder/'ballot.html'),'bytes':len((folder/'ballot.html').read_bytes()),'stage':record.state['stage'],'parts':publication}


def import_ruling(record,kind,submitted,receipt_path,dry_run=False):
    pending,ruled=('image_ballot_pending','images_ruled') if kind=='images' else ('page_ballot_pending','ruled')
    ballot=record.state['ballots'].get(kind)
    if not ballot:raise DesignError('no prepared '+kind+' ballot exists for this round')
    folder=record.resolve(ballot['path'])
    source=Path(submitted).read_text();receipt=json.loads(Path(receipt_path).read_text())
    if receipt.get('host')!='local':raise DesignError('design review is local-only; Artifact and external-host receipts are forbidden')
    part=next((p for p in ballot.get('parts',[ballot]) if ballot_fingerprint(source)==p['fingerprint']),None)
    if part is None:raise DesignError('submitted ballot changed content outside fb-state')
    state=json.loads(STATE.search(source)[1]);feedback=state.get('feedback')
    if not state.get('submitted_at') or not isinstance(feedback,dict):raise DesignError('ballot has no submitted owner ruling')
    if set(feedback)-set(part['keys']) or any(not isinstance(v,str) for v in feedback.values()):raise DesignError('unknown note keys or non-text feedback')
    host=urlparse(receipt.get('review_url',''))
    if receipt.get('published_ballot_sha256')!=part['sha256'] or receipt.get('readback_sha256')!=digest(source):raise DesignError('Review receipt does not bind the prepared and submitted ballots')
    try:datetime.fromisoformat(receipt['read_at'].replace('Z','+00:00'))
    except (KeyError,ValueError,TypeError):raise DesignError('Review receipt needs its actual ISO read timestamp') from None
    raw_path=Path(receipt.get('owner_input',''))
    if not raw_path.is_absolute():raw_path=Path(receipt_path).resolve().parent/raw_path
    if not raw_path.is_file() or not raw_path.read_bytes():raise DesignError('raw local owner input is missing')
    mapping=json.loads((folder/'blind-key.json').read_text())['mapping']
    mapping={label:value for label,value in mapping.items() if label in part.get('labels',mapping)}
    selected=receipt.get('selected_labels',[]);resolved=receipt.get('selection_status')=='complete'
    if not isinstance(selected,list) or len(selected)!=len(set(selected)) or any(label not in mapping for label in selected):raise DesignError('invalid selected ballot labels')
    expected=folder/'local-reviews'
    parent=Path(receipt_path).resolve().parent
    if (not parent.is_relative_to(expected.resolve()) or Path(submitted).resolve()!=parent/'submitted.html'
            or Path(receipt_path).resolve()!=parent/'receipt.json' or raw_path.resolve()!=parent/'owner-input.json'
            or host.scheme!='http' or host.hostname!='127.0.0.1' or receipt.get('review_version')!=parent.name):
        raise DesignError('local receipt must come from this round preview host')
    owner=json.loads(raw_path.read_text())
    if (receipt.get('selection_method')!='explicit_local_controls' or owner.get('feedback')!=feedback
            or owner.get('submitted_at')!=state['submitted_at'] or owner.get('selected_labels')!=selected
            or type(owner.get('complete'))!=bool or owner['complete']!=resolved):
        raise DesignError('local receipt does not match the saved owner controls')
    fingerprint=digest(source)
    # A host may first archive an ambiguous reading and then resolve the same
    # submitted notes. Preserve both readings; only identical dispositions are
    # idempotent. A changed choice after advancement still requires a new round.
    disposition=selected if resolved else None
    previous=next((r for r in reversed(record.state.get('rulings',[]))
                   if r['stage']==kind and r['submitted_sha256']==fingerprint
                   and r.get('selected_labels')==disposition),None)
    if previous:
        if not dry_run and record.state['stage']==pending:advance_rulings(record,kind,ballot,ruled)
        return {'status':'ruling already recorded','stage':record.state['stage'],'feedback':feedback}
    record.require(pending,ruled)
    if record.state['stage']==ruled:raise DesignError('a changed ruling after stage advancement needs a revised round; previous evidence stays intact')
    if dry_run:return {'dry_run':True,'feedback':feedback,'selection_resolved':resolved,'paid_requests':0}
    revision=record.attempt('rulings/'+kind)
    write_new(revision/'submitted.html',source);write_new(revision/'review-receipt.json',receipt)
    write_new(revision/'owner-input-original.json',raw_path.read_bytes())
    ruling={'stage':kind,'part_sha256':part['sha256'],'submitted_at':state['submitted_at'],'feedback':feedback,'review_url':receipt['review_url'],
            'review_version':receipt['review_version'],'submitted_sha256':fingerprint,'blind_key':mapping,'key_unsealed':True,
            'selected_labels':disposition,'selection_evidence':receipt.get('selection_evidence',[]),
            'path':str(revision.relative_to(record.path))}
    write_new(revision/'labels.yaml',ruling) # JSON is a YAML subset; avoids rewriting exact strings through a YAML emitter.
    write_new(revision/'unsealed-key.json',{'sealed':False,'mapping':mapping})
    record.state.setdefault('rulings',[]).append(ruling)
    projection=record.path/('.labels-'+uuid.uuid4().hex)
    write_new(projection,{'schema':1,'round':record.state['id'],'rulings':record.state['rulings']});os.replace(projection,record.path/'labels.yaml')
    record.save('owner ruling imported verbatim from local review controls')
    complete=advance_rulings(record,kind,ballot,ruled) if resolved else False
    return {'status':('ruling recorded' if complete else 'part recorded; awaiting remaining rulings') if resolved else 'selection needs clarification','stage':record.state['stage'],'feedback':feedback,
            'selected':record.state.get('selected_'+kind),'key_unsealed':mapping,'labels':str(record.path/'labels.yaml')}
