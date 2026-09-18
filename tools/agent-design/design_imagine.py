"""Resumable image generation: one original provider receipt per image request."""
import json
from pathlib import Path

from design_browser import DesignError
from design_contract import digest
from design_provider import authority, portrait_size, Provider, APIError, FALLBACK, image_from_response
from design_state import write_new


def imagine(record,per_level=2,size=None,dry_run=False,retry_uncertain=False,provider=None,lookup=authority):
    record.require('briefed','images_ready')
    if isinstance(per_level,bool) or not isinstance(per_level,int) or per_level<=0:raise DesignError('per-level must be a positive integer')
    current=lookup('image');selected_size=portrait_size(current['limits'],size)
    plan={'per_level':per_level,'size':size,'levels':list(record.state['prompts'])}
    old=record.state.get('image_plan')
    if old and old!=plan:raise DesignError('generation plan is frozen; resume with its original count/size or start a new round')
    if dry_run:return {'dry_run':True,'model':current['model'],'quality':current['limits']['quality'],'size':selected_size,
                      'requests':per_level*len(plan['levels']),'completed':len(record.state['images']),'paid_requests':0,'authority':current}
    if record.state['stage']=='images_ready':return record.state
    if not old:
        record.state['image_plan']=plan;record.save('image request count and level plan frozen')
    documents=record.attempt('provider-authority');write_new(documents/'image.json',current)
    provider=provider or Provider()
    completed={(r['level'],r['ordinal']) for r in record.state['images']}
    for level in plan['levels']:
        prompt=record.resolve(record.state['prompts'][level]['path']).read_text()
        for ordinal in range(1,per_level+1):
            if (level,ordinal) in completed:continue
            slot=record.path/'generations'/level/str(ordinal);slot.mkdir(parents=True,exist_ok=True)
            existing=[]
            for path in slot.iterdir():
                if not path.is_dir():continue
                if (path/'response.json').exists():existing.append(path)
                elif (path/'request.json').exists() and not (path/'error.json').exists():
                    if not retry_uncertain:raise DesignError('uncertain prior image request at '+str(path)+'; inspect its receipt or explicitly use --retry-uncertain')
            if existing:
                if len(existing)!=1:raise DesignError('multiple successful image responses in one slot; preserve evidence and reconcile explicitly')
                attempt=existing[0];request=json.loads((attempt/'request.json').read_text())['payload']
                receipt=json.loads((attempt/'response.json').read_text())
            else:
                chosen=current
                while True:
                    attempt=record.attempt(str(slot.relative_to(record.path)))
                    chosen_size=portrait_size(chosen['limits'],size)
                    request={'model':chosen['model'],'prompt':prompt,'size':chosen_size,'quality':chosen['limits']['quality'],'n':1,'output_format':'png'}
                    write_new(attempt/'authority.json',chosen)
                    try:
                        receipt=provider.post('images/generations',request,attempt);break
                    except APIError as error:
                        if (attempt/'error.json').exists():record.record_usage(attempt/'error.json',json.loads((attempt/'error.json').read_text()),'imagine')
                        if chosen['model']!=FALLBACK and error.model_unavailable():
                            chosen=lookup('image',model=FALLBACK)
                            write_new(attempt/'fallback.json',{'to':FALLBACK,'reason':str(error),'authority_checked_at':chosen['checked_at']})
                            continue
                        raise
                    except DesignError:
                        if (attempt/'uncertain.json').exists():record.record_usage(attempt/'uncertain.json',json.loads((attempt/'uncertain.json').read_text()),'imagine')
                        raise
            record.record_usage(attempt/'response.json',receipt,'imagine')
            data=image_from_response(receipt,request['size'])
            image_path=attempt/'image.png'
            if image_path.exists():
                if image_path.read_bytes()!=data:raise DesignError('saved image differs from original provider response')
            else:write_new(image_path,data)
            image={'id':level+'-'+str(ordinal),'level':level,'ordinal':ordinal,'path':str(image_path.relative_to(record.path)),
                   'sha256':digest(data),'model_requested':request['model'],'model_returned':receipt['response'].get('model'),
                   'size':request['size'],'quality':request['quality'],
                   'seed':receipt['response']['data'][0].get('seed',receipt['response'].get('seed')),
                   'seed_reason':'Preserve a returned seed; null when the provider returns none. No seed was requested.',
                   'prompt_sha256':digest(prompt),'request_id':receipt.get('request_id'),
                   'receipt':str((attempt/'response.json').relative_to(record.path)),'usage':receipt.get('usage','usage not returned')}
            record.state['images'].append(image)
            record.save('image '+image['id']+' decoded and preserved')
    record.transition('images_ready')
    return {'stage':record.state['stage'],'images':record.state['images'],'usage':record.state['usage']}
