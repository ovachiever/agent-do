"""Official, refreshed model authority and private, receipted OpenAI requests.

No price or spend policy lives here. There are no automatic paid retries.
"""
import base64
import json
from pathlib import Path
import re
import struct
import urllib.error
import urllib.request
import uuid
import zlib

from design_browser import agent_do, DesignError
from design_contract import digest, validate_prompts
from design_state import now, write_new

CATALOG='https://developers.openai.com/api/docs/models.md'
IMAGE_GUIDE='https://developers.openai.com/api/docs/guides/image-generation.md'
FALLBACK='gpt-image-2'  # Explicit owner-authorized availability fallback, not automatic error recovery.


def refresh_doc(url):
    reply=json.loads(agent_do('context','fetch',url,'--json'))
    if reply.get('success') is not True:raise DesignError('official documentation refresh failed: '+url)
    result=reply.get('result',{})
    if result.get('source')!=url:raise DesignError('documentation source mismatch')
    text=(Path(result['cached_at'])/'content.md').read_text()
    return {'url':url,'fetched_at':now(),'sha256':digest(text),'text':text}


def select_model(catalog,kind):
    entries=re.findall(r'\]\(/api/docs/models/([a-z0-9.-]+?)(?:\.md)?\):\s*([^\n]+)',catalog)
    if kind=='image':
        # The old generation may retain "most capable" after a new release.
        # Prefer the latest catalogued precision-family alias, never a dated
        # snapshot or the faster Flare tier. Its page/limits are verified below.
        versions={}
        for slug,description in entries:
            slug=slug.removesuffix('.md')
            match=re.fullmatch(r'gpt-image-(\d+(?:\.\d+)*)-sunburst',slug)
            if match and 'image generation' in description.lower():
                versions[tuple(map(int,match[1].split('.')))]=slug
        if versions:return versions[max(versions)]
    candidates=set()
    for slug,description in entries:
        words=description.lower()
        if 'most capable model' not in words:continue
        image='image generation' in words
        if image!=(kind=='image'):continue
        if any(word in slug.split('-') for word in ('mini','nano','flare','fast','luna')):continue
        if kind=='text' and any(word in words for word in ('coding model','audio','voice','research model','cybersecurity')):continue
        candidates.add(slug.removesuffix('.md'))
    if len(candidates)!=1:raise DesignError('provider catalog does not identify one strongest '+kind+' model; refresh the authority parser, never guess a cheaper tier')
    return candidates.pop()


def image_limits(guide,model):
    def number(pattern):
        m=re.search(pattern,guide,re.I)
        if not m:raise DesignError('published image limits changed; update the parser against '+IMAGE_GUIDE)
        return int(m.group(1).replace(',',''))
    step=number(r'must be multiples of\s+`?(\d+)')
    edge=number(r'neither edge may exceed\s+`?([\d,]+)')
    match=re.search(r'total pixel count must be between\s+`?([\d,]+)`?\s+and\s+`?([\d,]+)',guide,re.I)
    ratio=re.search(r'aspect ratio must be between\s+1:(\d+)\s+and\s+(\d+):1',guide,re.I)
    if not match or not ratio or ratio[1]!=ratio[2]:raise DesignError('published image area/aspect constraints are unreadable')
    area_min,area_max=[int(v.replace(',','')) for v in match.groups()]
    # Read which models support the highest quality from the guide's explicit sentence.
    quality=None
    for sentence in guide.splitlines():
        if 'add `xhigh` and `max` quality' in sentence and '`'+model+'`' in sentence:
            quality='max'
        family=re.fullmatch(r'gpt-image-(\d+(?:\.\d+)*)-sunburst',model)
        if (family and 'Sunburst and Flare models' in sentence and
                'quality options are' in sentence and '`max`' in sentence and
                family[1] in re.findall(r'GPT-Image-(\d+(?:\.\d+)*)',sentence)):
            quality='max'
    if model==FALLBACK and 'Earlier GPT Image models support quality settings up to `high`' in guide:quality='high'
    if quality is None:raise DesignError('strongest quality is not documented for '+model)
    return {'multiple':step,'max_edge':edge,'min_pixels':area_min,'max_pixels':area_max,'max_ratio':int(ratio[1]),'quality':quality,'source':IMAGE_GUIDE}


def portrait_size(limits,requested=None):
    step=limits['multiple'];edge=limits['max_edge']
    if requested:
        try:width,height=map(int,requested.lower().split('x'))
        except (TypeError,ValueError):raise DesignError('size must be WIDTHxHEIGHT')
    else:
        # Maximize published area first, then portrait height. No local resolution ceiling.
        possible=[]
        for height in range(step,edge+1,step):
            width=min(height-step,edge,(limits['max_pixels']//height//step)*step)
            if width>0 and height<=width*limits['max_ratio'] and width*height>=limits['min_pixels']:
                possible.append((width*height,height,width))
        if not possible:raise DesignError('provider limits contain no portrait size')
        _,height,width=max(possible)
    if not (0<width<height<=edge and width%step==0 and height%step==0 and
            limits['min_pixels']<=width*height<=limits['max_pixels'] and height<=width*limits['max_ratio']):
        raise DesignError('portrait size violates the current published image limits: '+json.dumps(limits))
    return f'{width}x{height}'


def image_size(limits,requested=None,viewport=None):
    if viewport is None:
        return portrait_size(limits,requested)
    step=limits['multiple'];edge=limits['max_edge']
    def valid(w,h):
        return (0<w<=edge and 0<h<=edge and w%step==0 and h%step==0 and
                limits['min_pixels']<=w*h<=limits['max_pixels'] and
                max(w,h)<=min(w,h)*limits['max_ratio'])
    if requested:
        try:w,h=map(int,requested.lower().split('x'))
        except (TypeError,ValueError):raise DesignError('size must be WIDTHxHEIGHT')
        if not valid(w,h):raise DesignError('size violates the current published image limits')
    else:
        ratio=viewport['width']/viewport['height']
        candidates=((w,h) for w in range(step,edge+1,step) for h in range(step,edge+1,step) if valid(w,h))
        try:w,h=min(candidates,key=lambda wh:(abs(wh[0]/wh[1]-ratio),-wh[0]*wh[1]))
        except ValueError:raise DesignError('no provider size fits the viewport') from None
    return f'{w}x{h}'


def text_limits(page):
    sentence=next((line for line in page.splitlines() if '`reasoning.effort` supports' in line),'')
    efforts=re.findall(r'`([^`]+)`',sentence)[1:]
    maximum=re.search(r'([\d,]+)\s+max output tokens',page,re.I)
    if not efforts or not maximum:raise DesignError('model page lacks maximum reasoning/output authority; update the parser')
    # The provider lists supported effort levels in increasing order in this sentence.
    return {'reasoning':efforts[-1],'max_output_tokens':int(maximum[1].replace(',',''))}


def authority(kind,fetch=refresh_doc,model=None):
    catalog=fetch(CATALOG)
    chosen=model or select_model(catalog['text'],kind)
    page=fetch('https://developers.openai.com/api/docs/models/'+chosen+'.md')
    if chosen not in page['text']:raise DesignError('model page did not identify requested model')
    docs=[catalog,page]
    if kind=='image':
        guide=fetch(IMAGE_GUIDE);docs.append(guide);limits=image_limits(guide['text'],chosen)
    else:limits=text_limits(page['text'])
    return {'kind':kind,'model':chosen,'limits':limits,'documents':docs,'checked_at':now()}


class APIError(DesignError):
    def __init__(self,status,code,message,request_id=None):
        super().__init__(f'OpenAI request failed: HTTP {status}, {code}: {message}')
        self.status=status;self.code=code;self.request_id=request_id

    def model_unavailable(self):
        return self.status in (400,404) and self.code in ('model_not_found','model_not_available','unsupported_model')


class Provider:
    def __init__(self):self._key=None

    def redact(self,value):
        if isinstance(value,str):
            text=value.replace(self._key,'[REDACTED]') if self._key else value
            return re.sub(r'\bsk-[A-Za-z0-9_-]+','[REDACTED]',text)
        if isinstance(value,list):return [self.redact(v) for v in value]
        if isinstance(value,dict):return {k:self.redact(v) for k,v in value.items() if k.lower() not in ('authorization','api_key','openai_api_key')}
        return value

    def post(self,endpoint,payload,folder):
        if endpoint=='images/generations':validate_prompts({'request':payload.get('prompt','')})
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        if self._key is None:
            self._key=agent_do('creds','get','OPENAI_API_KEY','--reveal').strip()
            if not self._key:raise DesignError('OpenAI credential did not resolve through agent-do creds')
        request_id=str(uuid.uuid4())
        body=json.dumps(payload).encode()
        write_new(folder/'request.json',{'endpoint':endpoint,'client_request_id':request_id,'started_at':now(),
                  'request_bytes':len(body),'request_sha256':digest(body),
                  'prompt_characters':len(payload['prompt']) if isinstance(payload.get('prompt'),str) else None,
                  'prompt_sha256':digest(payload['prompt']) if isinstance(payload.get('prompt'),str) else None,
                  'payload':self.redact(payload)})
        request=urllib.request.Request('https://api.openai.com/v1/'+endpoint,body,
                {'Content-Type':'application/json','Authorization':'Bearer '+self._key,'X-Client-Request-Id':request_id},method='POST')
        try:
            # Deliberately no local timeout, token budget, price gate, or retry loop.
            with urllib.request.urlopen(request) as response:
                result=self.redact(json.loads(response.read()))
                receipt={'received_at':now(),'request_id':response.headers.get('x-request-id'),
                         'client_request_id':request_id,'usage':result.get('usage') if result.get('usage') is not None else 'usage not returned','response':result}
                write_new(folder/'response.json',receipt)
                return receipt
        except urllib.error.HTTPError as error:
            try:body=json.loads(error.read())
            except (ValueError,UnicodeDecodeError):body={'error':{'code':'unreadable_error','message':'Provider returned a non-JSON error'}}
            body=self.redact(body);detail=body.get('error',{})
            receipt={'received_at':now(),'status':error.code,'request_id':error.headers.get('x-request-id'),
                     'client_request_id':request_id,'response':body,'usage':body.get('usage','usage not returned')}
            write_new(folder/'error.json',receipt)
            raise APIError(error.code,detail.get('code'),detail.get('message',''),receipt['request_id']) from None
        except (OSError,ValueError) as error:
            write_new(folder/'uncertain.json',{'at':now(),'client_request_id':request_id,'error':self.redact(str(error)),
                      'usage':'usage not returned','status':'outcome unknown; no automatic paid retry'})
            raise DesignError('Provider outcome is unknown. Evidence saved; explicit --retry-uncertain is required to issue a replacement request.') from None


def png_size(data):
    if data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR':raise DesignError('provider did not return the requested PNG')
    offset=8;ended=False;image_data=[]
    try:
        while offset<len(data):
            length=struct.unpack('>I',data[offset:offset+4])[0]
            tag=data[offset+4:offset+8];chunk=data[offset+8:offset+8+length]
            crc=struct.unpack('>I',data[offset+8+length:offset+12+length])[0]
            if zlib.crc32(tag+chunk)!=crc:raise DesignError('PNG checksum failed')
            if tag==b'IDAT':image_data.append(chunk)
            offset+=length+12
            if tag==b'IEND':ended=True;break
        if not ended or not image_data or offset!=len(data):raise DesignError('incomplete PNG image')
        width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',data[16:29])
        allowed={0:(1,2,4,8,16),2:(8,16),3:(1,2,4,8),4:(8,16),6:(8,16)}
        if not width or not height or depth not in allowed.get(color,()) or compression or filtering or interlace not in (0,1):raise DesignError('invalid PNG header')
        channels={0:1,2:3,3:1,4:2,6:4}[color]
        decoded=zlib.decompress(b''.join(image_data))
        # PNG scanline sizes and the seven Adam7 passes are format constants, not policy caps.
        passes=[(0,0,1,1)] if interlace==0 else [(0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2)]
        position=0
        for x,y,dx,dy in passes:
            columns=max(0,(width-x+dx-1)//dx);rows=max(0,(height-y+dy-1)//dy)
            if not columns or not rows:continue
            stride=1+(columns*channels*depth+7)//8
            for _ in range(rows):
                if position+stride>len(decoded) or decoded[position] not in range(5):raise DesignError('invalid PNG scanline data')
                position+=stride
        if position!=len(decoded):raise DesignError('PNG pixel data does not match its declared dimensions')
        return width,height
    except (struct.error,zlib.error):raise DesignError('malformed PNG image') from None


def image_from_response(receipt,size):
    images=receipt['response'].get('data',[])
    if len(images)!=1 or not images[0].get('b64_json'):raise DesignError('image request did not return exactly one base64 image')
    try:data=base64.b64decode(images[0]['b64_json'],validate=True)
    except ValueError:raise DesignError('provider image is not valid base64') from None
    if png_size(data)!=tuple(map(int,size.split('x'))):raise DesignError('provider image dimensions differ from the request')
    return data
