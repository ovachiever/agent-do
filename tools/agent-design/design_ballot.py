"""Blind ballots are handed to Claude; only an actual Artifact read supplies a ruling."""
import base64
from datetime import datetime
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import secrets
import struct
from urllib.parse import urlparse
import uuid

from design_browser import agent_do,Browser,DesignError,TOOL
from design_contract import digest
from design_provider import png_size
from design_reproduce import audit_candidate
from design_state import now,write_new

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
            visual='<img alt="Candidate '+label+'" width="'+str(candidate['width'])+'" height="'+str(candidate['height'])+'" src="data:image/png;base64,'+image+'">'
        else:
            visual='<iframe id="candidate-'+label+'" title="Candidate '+label+'" sandbox="allow-scripts" width="'+str(candidate['width'])+'" height="'+str(candidate['height'])+'" srcdoc="'+html.escape(candidate['html'],quote=True)+'"></iframe>'
        parts.append('<section><h2>Candidate '+label+'</h2><div class="candidate">'+visual+'</div><label for="note-'+label+'">Your note: '+label+'</label><textarea id="note-'+label+'" data-fb="'+field+'"></textarea><div hidden data-fb-saved="'+field+'"></div></section>')
    field=key+'-overall'
    parts.append('<section><label for="overall">Overall</label><textarea id="overall" data-fb="'+field+'"></textarea><div hidden data-fb-saved="'+field+'"></div></section></main><footer><span id="fb-status"></span><button id="fb-submit">Submit ruling</button></footer><script>')
    parts.append((TOOL/'ballot-runtime.js').read_text());parts.append('</script></body></html>')
    return ''.join(parts)


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


def claude_target(explicit=None):
    status=json.loads(agent_do('coord','status','--json'))
    peers=[p for p in status.get('active_peers',[]) if p.get('runtime')=='claude' and p.get('status')=='active']
    if explicit:
        matches=[p for p in peers if explicit in (p.get('agent_id'),p.get('alias'))]
        if len(matches)==1:return matches[0]['agent_id']
        raise DesignError('requested ballot recipient is not an active Claude Code session')
    if len(peers)==1:return peers[0]['agent_id']
    raise DesignError('ballot pending: select an active Claude Code recipient with --claude-session; no alternate host is available')


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


def prepare_ballot(record,kind,recipient=None,dry_run=False,drop=None,target=claude_target):
    ready,pending=('images_ready','image_ballot_pending') if kind=='images' else ('pages_ready','page_ballot_pending')
    record.require(ready,pending);candidates=verify_candidates(record,kind)
    if dry_run:return {'dry_run':True,'stage':kind,'candidates':len(candidates),'publication':'Claude Code /ballot via coord drop','paid_requests':0,'status':'ballot pending'}
    ballot=record.state['ballots'].get(kind)
    if not ballot:
        folder=record.attempt('ballots/'+kind);key='b-'+uuid.uuid4().hex
        shuffled=list(candidates);secrets.SystemRandom().shuffle(shuffled)
        mapping={};public=[];frames=[];view=record.contract()['viewports'][0]
        for index,original in enumerate(shuffled,1):
            label=str(index);candidate={'label':label,'kind':kind}
            if kind=='images':
                data=public_png(record.resolve(original['path']).read_bytes());candidate['bytes']=data
                candidate['width'],candidate['height']=png_size(data);write_new(folder/('candidate-'+label+'.png'),data)
                public_hash=digest(data)
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
        source=make_ballot(key,public);write_new(folder/'ballot.html',source)
        browser=Browser()
        try:
            chrome=browser.polish((folder/'ballot.html').as_uri(),(view['width'],view['height']),{'verified_frames':frames})
        finally:browser.close()
        write_new(folder/'chrome-audit.json',chrome)
        if not chrome['clean']:raise DesignError('ballot chrome did not pass live polish; evidence retained at '+str(folder))
        ballot={'path':str(folder.relative_to(record.path)),'key':key,'sha256':digest(source),'fingerprint':ballot_fingerprint(source),
                'keys':[key+'-'+str(i) for i in range(1,len(public)+1)]+[key+'-overall'],'status':'ballot pending'}
        record.state['ballots'][kind]=ballot
        record.save('blind '+kind+' ballot prepared and mechanically checked')
    if record.state['stage']==ready:record.transition(pending)
    folder=record.resolve(ballot['path'])
    if digest((folder/'ballot.html').read_bytes())!=ballot['sha256']:raise DesignError('prepared ballot changed')
    if not ballot.get('drop'):
        recipient=target(recipient)
        instructions=f'''# Claude Code ballot handoff

Run `/ballot` using `{folder/'ballot.html'}`. Read `~/.claude/skills/ballot/SKILL.md`.
Publish with `capabilities: {{"artifact": {{}}}}`, then read back the real Artifact and verify its ballot and note keys.
This is a blind {kind} ballot. Do not inspect or publish blind-key.json before Erik submits. Do not replace hosting.
The local tool records only "ballot pending". Give Erik the real URL. Wait for his ruling; elapsed time is no answer.

When Erik submits, read the Artifact using its actual read capability. Save the exact returned HTML to a new file here.
Preserve every note verbatim, including whitespace and typos. Save the raw Artifact tool read receipt too.
Create a receipt JSON with host="claude", artifact_url, artifact_version, read_at (ISO timestamp),
published_ballot_sha256="{ballot['sha256']}", readback_sha256 (SHA-256 of the saved returned HTML),
and artifact_read_receipt (path to the saved raw tool read result).
For explicit choices add selection_status="complete", selected_labels (list of neutral labels), and
selection_evidence=[{{"label":"...","key":"...","quote":"the FULL original note, verbatim"}}].
If the owner's selection is ambiguous, use selection_status="needs_clarification"; never infer approval from silence.
Quote his notes and resolve the choice with him before completing that field. A rejection of all candidates is selected_labels=[].

Import using `agent-do design ballot {kind} --round {record.path} --submitted RETURNED_HTML --receipt RECEIPT_JSON`.
Keep the original, every submission, real URL/version, raw read receipt and ruling. Do not fabricate any receipt.
Known note keys: {json.dumps(ballot['keys'])}
'''
        handoff=folder/'CLAUDE-HANDOFF.md'
        if not handoff.exists():write_new(handoff,instructions)
        raw=(drop or (lambda path,who,key:agent_do('coord','drop','add',str(path),'--for',who,'--key',key,'--note','Use /ballot to publish and read this owner ballot; return exact Artifact evidence')))(handoff,recipient,ballot['key'])
        write_new(folder/'coord-drop.json',{'recipient':recipient,'returned':raw,'at':now()})
        ballot['drop']=str((folder/'coord-drop.json').relative_to(record.path));ballot['recipient']=recipient;record.save('Claude ballot handoff recorded')
    return {'status':'ballot pending','stage':record.state['stage'],'ballot':str(folder/'ballot.html'),'handoff':str(folder/'CLAUDE-HANDOFF.md'),'recipient':ballot.get('recipient'),'published_url':None}


def import_ruling(record,kind,submitted,receipt_path,dry_run=False):
    pending,ruled=('image_ballot_pending','images_ruled') if kind=='images' else ('page_ballot_pending','ruled')
    ballot=record.state['ballots'][kind];folder=record.resolve(ballot['path'])
    source=Path(submitted).read_text();receipt=json.loads(Path(receipt_path).read_text())
    if ballot_fingerprint(source)!=ballot['fingerprint']:raise DesignError('submitted ballot changed content outside fb-state')
    state=json.loads(STATE.search(source)[1]);feedback=state.get('feedback')
    if not state.get('submitted_at') or not isinstance(feedback,dict) or not feedback:raise DesignError('ballot has no submitted owner ruling')
    if set(feedback)-set(ballot['keys']) or any(not isinstance(v,str) for v in feedback.values()):raise DesignError('unknown note keys or non-text feedback')
    host=urlparse(receipt.get('artifact_url',''))
    if receipt.get('host')!='claude' or host.scheme!='https' or host.hostname!='claude.ai' or '/artifact/' not in host.path or not receipt.get('artifact_version'):
        raise DesignError('a real Claude Artifact URL and version read receipt is required')
    if receipt.get('published_ballot_sha256')!=ballot['sha256'] or receipt.get('readback_sha256')!=digest(source):raise DesignError('Artifact receipt does not bind the prepared and submitted ballots')
    try:datetime.fromisoformat(receipt['read_at'].replace('Z','+00:00'))
    except (KeyError,ValueError,TypeError):raise DesignError('Artifact receipt needs its actual ISO read timestamp') from None
    raw_path=Path(receipt.get('artifact_read_receipt',''))
    if not raw_path.is_absolute():raw_path=Path(receipt_path).resolve().parent/raw_path
    if not raw_path.is_file() or not raw_path.read_bytes():raise DesignError('raw Artifact read receipt is missing')
    mapping=json.loads((folder/'blind-key.json').read_text())['mapping']
    selected=receipt.get('selected_labels',[]);resolved=receipt.get('selection_status')=='complete'
    if not isinstance(selected,list) or len(selected)!=len(set(selected)) or any(label not in mapping for label in selected):raise DesignError('invalid selected ballot labels')
    if resolved:
        evidence=receipt.get('selection_evidence',[])
        for label in selected:
            if not any(e.get('label')==label and e.get('key') in feedback and e.get('quote')==feedback[e['key']] and e.get('quote','').strip() for e in evidence):
                raise DesignError('selected candidate has no exact owner-note evidence: '+label)
    fingerprint=digest(source)
    previous=next((r for r in record.state.get('rulings',[]) if r['submitted_sha256']==fingerprint),None)
    if previous:
        if not dry_run and previous.get('selected_labels') is not None and record.state['stage']==pending:record.transition(ruled)
        return {'status':'ruling already recorded','stage':record.state['stage'],'feedback':feedback}
    record.require(pending,ruled)
    if record.state['stage']==ruled:raise DesignError('a changed ruling after stage advancement needs a revised round; previous evidence stays intact')
    if dry_run:return {'dry_run':True,'feedback':feedback,'selection_resolved':resolved,'paid_requests':0}
    revision=record.attempt('rulings/'+kind)
    write_new(revision/'submitted.html',source);write_new(revision/'artifact-receipt.json',receipt)
    write_new(revision/'artifact-read-original',raw_path.read_bytes())
    ruling={'stage':kind,'submitted_at':state['submitted_at'],'feedback':feedback,'artifact_url':receipt['artifact_url'],
            'artifact_version':receipt['artifact_version'],'submitted_sha256':fingerprint,'blind_key':mapping,'key_unsealed':True,
            'selected_labels':selected if resolved else None,'selection_evidence':receipt.get('selection_evidence',[]),
            'path':str(revision.relative_to(record.path))}
    write_new(revision/'labels.yaml',ruling) # JSON is a YAML subset; avoids rewriting exact strings through a YAML emitter.
    write_new(revision/'unsealed-key.json',{'sealed':False,'mapping':mapping})
    record.state.setdefault('rulings',[]).append(ruling)
    projection=record.path/('.labels-'+uuid.uuid4().hex)
    write_new(projection,{'schema':1,'round':record.state['id'],'rulings':record.state['rulings']});os.replace(projection,record.path/'labels.yaml')
    if resolved:record.state['selected_'+kind]=[mapping[label]['id'] for label in selected]
    record.save('owner ruling imported verbatim from Claude Artifact read')
    if resolved:record.transition(ruled)
    return {'status':'ruling recorded' if resolved else 'selection needs clarification','stage':record.state['stage'],'feedback':feedback,
            'selected':record.state.get('selected_'+kind),'key_unsealed':mapping,'labels':str(record.path/'labels.yaml')}
