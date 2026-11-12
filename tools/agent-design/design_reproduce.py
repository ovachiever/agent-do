"""Normal vision-capable frontend builders, followed by independent live checks."""
import base64
from html.parser import HTMLParser
import json
from pathlib import Path

from design_browser import Browser,DesignError
from design_contract import check_copy,digest
from design_provider import authority,Provider
from design_state import write_new

OUTPUT_SCHEMA={'type':'object','properties':{'html':{'type':'string'},'implementation_decisions':{'type':'array','items':{'type':'string'}}},
               'required':['html','implementation_decisions'],'additionalProperties':False}

BUILDER_RULES='''You are a frontend designer reproducing a chosen image as a complete, beautiful, working browser page.
Use your normal HTML, CSS, typography and inline SVG design abilities. The image supplies structure, palette, proportions,
type roles and diagrams. Reproduce its composition faithfully. The measurement packet supplies observations, not a template.
The image is never an authority for words or figures. Re-impose the frozen owner copy and facts after interpreting its look.

CONTENT CONTRACT:
Every approved paragraph appears verbatim, exactly once, in order. Preserve punctuation and wording, including the opening
and closing. Text may cross inline elements or a heading/body boundary, but cannot be rewritten, abbreviated or repeated.
Tag each approved paragraph's element(s) with its data-copy-id. Every other visible text element must have data-node-id for
its exact allowed label or data-fact-id for its exact fact value. A label may appear only its owner-declared occurrences.
Every visible number (including dates, IDs, axes and SVG captions) must carry its own appropriate data-fact-id, binding the
specific claim, not merely an equal number elsewhere. Keep labels and their figures in their declared content group.
No motto, tagline, icon, gradient, stock imagery, decorative logo, device frame, invented sentence or invented figure.
Do not display contract IDs, sources or design commentary as page copy.

DIAGRAMS:
Draw diagrams with inline SVG, tagged data-diagram-kind="quantitative" or "nonquantitative". Every quantitative mark must
carry data-fact-id and data-value containing its literal source value. SVG text follows the same copy and fact contract.
Do not fabricate a plotted series to match a picture. If the source lacks quantitative data, preserve the visual role using
a nonquantitative diagram of the supplied mechanism, and record that implementation choice outside the page.

IMPLEMENTATION AND POLISH:
Return a full self-contained HTML document with inline CSS and SVG, semantic reading order, responsive behavior for all
declared viewports, accessible text and actual navigation hrefs when supplied. No scripts, iframes, canvas, rasterized text,
generated CSS text or editable form values. Use ordinary HTML text so every word can be checked. Font resources may load
from approved sources. No screenshot-as-page. Never hide, clip, delete, shrink text to illegibility, or weaken an audit to
pass. Fix relationships and proportions while preserving the image's composition. Keep short phrases together, avoid
single-word orphan tails, duplicate sentences, clipped captions, floating paired controls and horizontal overflow.
The external checker is independent of you. Its full measurements and renders are supplied on repair. Continue until all
declared viewport checks pass. Return JSON with html and implementation_decisions; commentary never enters visible copy.
'''


class DocumentCheck(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.findings=[]
    def handle_starttag(self,tag,attributes):
        attrs=dict(attributes)
        if tag in ('script','iframe','canvas','img','video','object','embed','input','textarea'):
            self.findings.append({'code':'uninspectable_or_executable_content','tag':tag})
        if any(k.lower().startswith('on') for k in attrs):self.findings.append({'code':'event_handler','tag':tag})
        if tag=='svg' and attrs.get('data-diagram-kind') not in ('quantitative','nonquantitative'):
            self.findings.append({'code':'diagram_kind_missing'})


def document_check(html):
    parser=DocumentCheck();parser.feed(html)
    if '<!doctype html>' not in html.lower():parser.findings.append({'code':'doctype_missing'})
    return parser.findings


def audit_candidate(path,contract,folder,browser=None):
    path=Path(path);folder=Path(folder);raw=path.read_bytes();document_findings=document_check(raw.decode())
    result={'schema':1,'html_sha256':digest(raw),'document_findings':document_findings,'viewports':[],'clean':False}
    if document_findings:
        write_new(folder/'audit.json',result);return result
    own=browser is None;browser=browser or Browser()
    try:
        for ordinal,view in enumerate(contract['viewports']):
            config=dict(contract['polish'])
            config['phrases']=[*config.get('phrases',[]),*[{'text':n['text'],'source':n['source']} for n in contract['nodes'] if n.get('text') and n.get('role') in ('label','action','figure')]]
            polish=browser.polish(path.resolve().as_uri(),(view['width'],view['height']),config)
            copy=check_copy(polish,contract)
            diagram_findings=browser.evaluate('''(()=>{const issues=[];for(const svg of document.querySelectorAll('svg[data-diagram-kind="quantitative"]')) {
              for(const mark of svg.querySelectorAll('[data-value]')) if(!mark.dataset.factId) issues.push({code:'unbound_quantitative_mark',value:mark.dataset.value});
              if(!svg.querySelector('[data-fact-id][data-value]')) issues.push({code:'quantitative_diagram_without_source_values'});
            }return issues})()''')
            render=folder/(str(ordinal)+'.png');browser.screenshot(render)
            row={'viewport':view,'polish':polish,'copy':copy,'diagram_findings':diagram_findings,
                 'render':render.name,'render_sha256':digest(render.read_bytes()),
                 'clean':polish['clean'] and copy['clean'] and not diagram_findings}
            write_new(folder/(str(ordinal)+'.json'),row);result['viewports'].append(row)
    finally:
        if own:browser.close()
    if path.read_bytes()!=raw:raise DesignError('candidate HTML changed while it was being audited')
    result['clean']=bool(result['viewports']) and all(v['clean'] for v in result['viewports'])
    write_new(folder/'audit.json',result);return result


def response_output(receipt):
    response=receipt['response']
    if response.get('status')!='completed':raise DesignError('builder response was incomplete: '+str(response.get('incomplete_details') or response.get('status')))
    text=''.join(c.get('text','') for item in response.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
    try:value=json.loads(text)
    except ValueError:raise DesignError('builder did not return the required structured HTML document') from None
    if not isinstance(value.get('html'),str) or not value['html'].strip():raise DesignError('builder returned no HTML')
    return value


def builder_request(model,contract,image,measurement,previous=None):
    packet={'contract':contract,'measurement':measurement,'previous_attempt':previous}
    content=[{'type':'input_text','text':BUILDER_RULES+'\nFROZEN WORK PACKET\n'+json.dumps(packet,ensure_ascii=False)},
             {'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(image).decode(),'detail':'original'}]
    if previous:
        for render in previous.get('render_paths',[]):
            content.append({'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(Path(render).read_bytes()).decode(),'detail':'original'})
    return {'model':model['model'],'reasoning':{'effort':model['limits']['reasoning']},
            'max_output_tokens':model['limits']['max_output_tokens'],'store':False,
            'text':{'format':{'type':'json_schema','name':'design_reproduction','strict':True,'schema':OUTPUT_SCHEMA}},
            'input':[{'role':'user','content':content}]}


def reproduce(record,dry_run=False,retry_uncertain=False,provider=None,lookup=authority,auditor=audit_candidate):
    record.require('measured','pages_ready')
    selected=record.state.get('selected_images',[])
    if not selected:raise DesignError('reproduction requires an explicit image ruling')
    current=lookup('text');contract=record.contract();images={i['id']:i for i in record.state['images']}
    for key in selected:
        image=images[key];measurement=record.state['measurements'].get(key)
        if not measurement:raise DesignError('chosen image has no measurement: '+key)
        if digest(record.resolve(image['path']).read_bytes())!=image['sha256']:raise DesignError('chosen image changed')
        if digest(record.resolve(measurement['path']).read_bytes())!=measurement['sha256']:raise DesignError('measurement changed')
    if dry_run:return {'dry_run':True,'builders':len(selected),'model':current['model'],'reasoning':current['limits']['reasoning'],
                      'viewports':contract['viewports'],'paid_requests':0,'authority':current}
    if record.state['stage']=='pages_ready':return {'stage':'pages_ready','pages':record.state['pages']}
    documents=record.attempt('provider-authority');write_new(documents/'text.json',current)
    provider=provider or Provider();completed={p['image_id'] for p in record.state['pages']}
    for key in selected:
        if key in completed:continue
        builder=record.state.setdefault('builders',{}).setdefault(key,{'attempts':[]})
        measurement=json.loads(record.resolve(record.state['measurements'][key]['path']).read_text())
        image=record.resolve(images[key]['path']).read_bytes();previous=None
        # One isolated builder per chosen image. Repairs have no iteration or token budget.
        while True:
            pending=next((a for a in builder['attempts'] if not a.get('finished')),None)
            if pending:
                folder=record.resolve(pending['path'])
                if (folder/'response.json').exists():receipt=json.loads((folder/'response.json').read_text())
                elif (folder/'request.json').exists() and not (folder/'error.json').exists():
                    if not retry_uncertain:raise DesignError('builder request outcome unknown at '+str(folder)+'; use --retry-uncertain only after inspecting the receipt')
                    pending['finished']=True;pending['status']='uncertain_replacement_authorized';record.save('uncertain builder request retained');continue
                else:
                    pending['finished']=True;pending['status']='request_failed';record.save('failed builder request retained');continue
            else:
                finished=[a for a in builder['attempts'] if a.get('audit')]
                if finished:
                    last=finished[-1];last_folder=record.resolve(last['path'])
                    previous={'html':(last_folder/'page.html').read_text(),'audit':json.loads(record.resolve(last['audit']).read_text()),
                              'render_paths':[str(p) for p in record.resolve(last['audit']).parent.glob('*.png')]}
                invalid=[a for a in builder['attempts'] if a.get('status')=='invalid_output']
                if invalid:
                    previous=previous or {}
                    previous['output_contract_failure']=invalid[-1]['error']
                folder=record.attempt('builders/'+key)
                pending={'path':str(folder.relative_to(record.path)),'finished':False};builder['attempts'].append(pending)
                record.save('builder '+key+' request prepared')
                payload=builder_request(current,contract,image,measurement,previous)
                try:receipt=provider.post('responses',payload,folder)
                except DesignError:
                    for name in ('error.json','uncertain.json'):
                        if (folder/name).exists():record.record_usage(folder/name,json.loads((folder/name).read_text()),'reproduce')
                    raise
            record.record_usage(folder/'response.json',receipt,'reproduce')
            try:output=response_output(receipt)
            except DesignError as error:
                pending['finished']=True;pending['status']='invalid_output';pending['error']=str(error)
                pending['usage']=receipt.get('usage','usage not returned');record.save('incomplete builder output retained')
                continue
            page=folder/'page.html'
            if page.exists():
                if page.read_text()!=output['html']:raise DesignError('builder HTML differs from original response')
            else:write_new(page,output['html'])
            if not (folder/'decisions.json').exists():write_new(folder/'decisions.json',output['implementation_decisions'])
            # Reuse a completed check after interruption; never overwrite partial audit files.
            check_path=folder/'checks'
            if (check_path/'audit.json').exists():audit=json.loads((check_path/'audit.json').read_text())
            else:
                if check_path.exists():check_path=record.attempt(str((folder/'checks-retry').relative_to(record.path)))
                audit=auditor(page,contract,check_path)
            pending.update({'finished':True,'status':'passed' if audit['clean'] else 'repair_needed',
                            'audit':str((check_path/'audit.json').relative_to(record.path)),'usage':receipt.get('usage','usage not returned')})
            if audit['clean']:
                record.state['pages'].append({'id':'page-'+key,'image_id':key,'path':str(page.relative_to(record.path)),
                    'sha256':digest(page.read_bytes()),'audit':pending['audit'],'audit_sha256':digest((check_path/'audit.json').read_bytes()),
                    'renders':[{'path':str((check_path/v['render']).relative_to(record.path)),'sha256':v['render_sha256'],'viewport':v['viewport']} for v in audit['viewports']]})
                record.save('passing page '+key+' ready for the owner ballot');break
            record.save('builder '+key+' measured: '+pending['status'])
    record.transition('pages_ready')
    return {'stage':record.state['stage'],'pages':record.state['pages'],'usage':record.state['usage']}
