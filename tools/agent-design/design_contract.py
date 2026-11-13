"""Owner-controlled text and fact bindings, independent of layout and style."""
from collections import Counter, defaultdict
import hashlib
import json
import re
from design_browser import DesignError


def normalize(text):
    return re.sub(r'\s+', ' ', str(text)).strip()


def digest(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def compile_contract(copy, facts, source='facts.json'):
    if not isinstance(facts, dict) or not isinstance(facts.get('nodes'), list) or not facts['nodes']:
        raise DesignError('facts must use the approved node-tagged brief shape with a nonempty nodes array')
    paragraphs=[{'id':f'p{i+1}','text':text} for i,text in enumerate(re.split(r'\n\s*\n',copy.strip())) if text.strip()]
    whole=normalize(copy)
    nodes=[]; values={}; ids=set()
    for index,raw in enumerate(facts['nodes']):
        if not isinstance(raw,dict) or not isinstance(raw.get('id'),str) or not raw['id'] or raw['id'] in ids:
            raise DesignError('every fact node needs a unique nonempty id')
        node_id=raw['id'];ids.add(node_id)
        node={k:raw[k] for k in ('id','kind','role','group','text','href','order','data','unit','required','occurrences') if k in raw}
        node['source']=raw.get('source') or source+'#/nodes/'+str(index)
        if 'text' in node and not isinstance(node['text'],str):
            raise DesignError('node text must be a string: '+node_id)
        if node.get('role') in ('body','prose','paragraph') and normalize(node.get('text','')) not in whole:
            raise DesignError('facts contain narrative outside the approved copy: '+node_id)
        if isinstance(node.get('occurrences',1),bool) or not isinstance(node.get('occurrences',1),int) or node.get('occurrences',1)<1:
            raise DesignError('node occurrences must be a positive owner-authored count: '+node_id)
        if node.get('text'):
            values[node_id]={'value':node['text'],'source':node['source'],'node_id':node_id,'unit':node.get('unit')}
        def leaves(value, path):
            if isinstance(value,dict):
                for k,v in value.items():leaves(v,path+'/'+str(k).replace('~','~0').replace('/','~1'))
            elif isinstance(value,list):
                for i,v in enumerate(value):leaves(v,path+'/'+str(i))
            elif value is not None and not isinstance(value,bool):
                values[path]={'value':value,'source':node['source']+'/data'+path.split('/data',1)[-1],'node_id':node_id,'unit':node.get('unit')}
        if 'data' in node:leaves(node['data'],node_id+'/data')
        nodes.append(node)
    groups=[{k:g[k] for k in ('id','parent','kind','order') if k in g} for g in facts.get('groups',[])]
    views=facts.get('viewports')
    if not isinstance(views,list) or not views:
        raise DesignError('facts must declare target viewports')
    for v in views:
        if not isinstance(v,dict) or any(isinstance(v.get(k),bool) or not isinstance(v.get(k),int) or v[k]<=0 for k in ('width','height')):
            raise DesignError('every viewport requires positive integer width and height')
    return {'schema':1,'id':facts.get('id'),'title':facts.get('title') or facts.get('surface'),
            'copy_sha256':digest(copy),'paragraphs':paragraphs,'nodes':nodes,'facts':values,'groups':groups,
            'frame':facts.get('frame',{}),'viewports':views,'polish':facts.get('polish',{}),
            'exact_design':facts.get('exact_design'),
            'content_order':[p['id'] for p in paragraphs],
            'source':source,'framing':facts.get('framing','viewport')}


# Images API prompt maximum, not a local cost or token budget.
# https://developers.openai.com/api/reference/resources/images/methods/generate
MAX_PROMPT_CHARACTERS = 32000


def validate_prompts(compiled):
    sizes={level:len(text) for level,text in compiled.items()}
    oversized={level:size for level,size in sizes.items() if size>MAX_PROMPT_CHARACTERS}
    if oversized:
        raise DesignError('compiled image prompt exceeds provider maximum of 32000 characters: '+json.dumps(oversized)+'. Preserve the brief; revise its representation before freezing or sending.')
    return sizes


def prompts(copy, contract):
    # Provenance remains in the local contract. Send each display value once,
    # without filesystem paths or the duplicate flattened verification index.
    nodes=[{k:v for k,v in node.items() if k!='source'} for node in contract['nodes']]
    content=json.dumps({'title':contract['title'],'nodes':nodes,'groups':contract['groups']},ensure_ascii=False,separators=(',',':'))
    mode=contract.get('framing','scroll') # Frozen legacy contracts retain their framing.
    if mode not in ('viewport','scroll'):
        raise DesignError('framing must be viewport or scroll')
    view=contract['viewports'][0]
    composition=(f"Show the complete {view['width']} by {view['height']} CSS pixel viewport, with the same aspect ratio. "
                 if mode=='viewport' else 'Use portrait framing and include every section from beginning to end. ')
    framing=('A high-fidelity screenshot of the requested web interface, as captured from a real browser. '
             f"Compose for the approved browser viewport width of {contract['viewports'][0]['width']} CSS pixels, "
             'This layout width is separate from the generated raster dimensions '
             'and must not appear as page text. '
             + composition + 'All text must be sharp and spelled exactly as supplied. '
             'The intended product and content are specified below. A product name is plain text, never a decorative logo.\n\n')
    laws=('No icons, gradients, stock imagery, device frames, decorative logos, mottos, taglines, or invented text. '
          'No added sentences, captions, figures, or claims. Draw diagrams of the subject using only the supplied facts. '
          'If data for a quantitative plot is absent, show a nonquantitative mechanism supported by the supplied content. '
          'Include every approved paragraph verbatim, once, in its given order, and every supplied label and factual display. '
          'Nothing may be omitted to fit the image.\n\n')
    frozen=('APPROVED COPY, VERBATIM\n<approved-copy>\n'+copy+'\n</approved-copy>\n\n'
            'FACTS AND LABELS (identifiers and source paths are metadata, not visible copy)\n'+content+'\n')
    layout=(contract.get('exact_design') or
            ('Use the supplied viewport as a dashboard canvas. Arrange navigation, controls, summaries and repeated data groups in a clear grid. Use only the supplied labels and values; do not add introductory prose.' if not contract['paragraphs'] else None) or
            'One centered content grid, two equal columns. Full-width navigation above the opening. '
            'The opening paragraph spans the grid. Each subsequent paragraph occupies the left column; '
            'its associated factual diagram or figures occupy the right. Keep group order and every '
            'shared left edge. Headings use the display role, prose the body role, figures the numeric '
            'role. Use the supplied role sizes and palette. Gaps within a group equal one body line-height; '
            'gaps between groups equal the display line-height. Hairline rules separate groups. '
            'The final paragraph spans the grid, with closing actions immediately beneath it. '
            'Use unfilled, outlined rectangular buttons. No shadows. No rounded cards.')
    exact=('EXACT: Follow this recorded composition and the house tokens literally. These are design '
           'decisions for this prompt, not content facts or general laws.\nCOMPOSITION\n'+
           (layout if isinstance(layout,str) else json.dumps(layout,ensure_ascii=False,indent=2))+
           '\nHOUSE TOKENS\n'+json.dumps(contract['frame'],ensure_ascii=False,indent=2)+'\n\n')
    # Release numeric geometry in HALF while retaining named palette and type character.
    loose={k:v for k,v in contract['frame'].items() if isinstance(v,str) and not re.search(r'(width|height|size|spacing|gap|radius)',k,re.I)}
    half=('HALF: Content is fixed; interpret the supplied palette and type roles loosely as a house character. '
          'Choose the layout, proportions, spacing, section treatments, diagram forms and rhythm of the scroll. '
          'Keep the whole composition coherent.\nHOUSE DIRECTION\n'+json.dumps(loose,ensure_ascii=False,indent=2)+'\n\n')
    opened=('OPEN: Everything below must be on the page in order. Every choice about how it looks is yours: '
            'palette, typefaces, light or dark or both, grid, spacing, scroll rhythm, section treatments, '
            'diagram form and proportions. Create a compelling whole for this product. Content is fixed; design is entirely free.\n\n')
    compiled={level:framing+direction+laws+frozen for level,direction in [('exact',exact),('half',half),('open',opened)]}
    validate_prompts(compiled)
    return compiled


def check_copy(snapshot, contract):
    findings=[]
    add=lambda code,**data:findings.append({'code':code,**data})
    expected={p['id']:normalize(p['text']) for p in contract['paragraphs']}
    actual=snapshot.get('text',{}).get('copies',{})
    for key,text in expected.items():
        if normalize(actual.get(key,''))!=text:add('copy_mismatch',id=key,expected=text,actual=actual.get(key))
    for key in actual:
        if key not in expected:add('unknown_copy',id=key)
    bindings=snapshot.get('text',{}).get('bindings',[])
    order=[];node_chunks=defaultdict(lambda:defaultdict(list))
    for row in bindings:
        text=row.get('text','')
        if not normalize(text):continue
        cp=row.get('copy_id');node=row.get('node_id');fact=row.get('fact_id')
        if cp:
            if cp not in expected:add('unknown_copy',id=cp)
            if cp not in order:order.append(cp)
        elif node:
            node_chunks[node][row.get('node_instance','default')].append(text)
        elif fact:
            value=contract['facts'].get(fact)
            if value is None or normalize(text)!=normalize(value['value']):add('wrong_fact',id=fact,text=text)
        else:add('stray_text',text=text,selector=row.get('selector'))
        if re.search(r'\d',text):
            value=contract['facts'].get(fact)
            if value is None:add('unbound_figure',text=text,selector=row.get('selector'))
            elif any(number not in re.findall(r'[+−-]?\d+(?:[.,]\d+)*(?:%|[A-Za-z]+)?',str(value['value'])) for number in re.findall(r'[+−-]?\d+(?:[.,]\d+)*(?:%|[A-Za-z]+)?',text)):
                add('wrong_fact',id=fact,text=text,expected=value['value'])
    if order!=list(expected):add('copy_order',expected=list(expected),actual=order)
    known={n['id']:n for n in contract['nodes']}
    for key,instances in node_chunks.items():
        node=known.get(key)
        if node is None:add('unknown_node',id=key);continue
        wanted=normalize(node.get('text',''))
        repeats=node.get('occurrences',1)
        for chunks in instances.values():
            value=normalize(''.join(chunks))
            if value!=wanted:add('node_mismatch',id=key,expected=wanted,actual=value)
        if len(instances)!=repeats:add('node_occurrences',id=key,expected=repeats,actual=len(instances))
    for node in contract['nodes']:
        if not node.get('text') or node.get('required') is False:continue
        covered_by_copy=any(normalize(node['text'])==t for t in expected.values())
        if node['id'] not in node_chunks and not covered_by_copy:add('missing_node',id=node['id'])
    for mark in snapshot.get('fact_marks',[]):
        fact=contract['facts'].get(mark.get('fact_id'))
        if fact is None or normalize(mark.get('value'))!=normalize(fact['value']):add('wrong_fact',mark=mark)
    if not snapshot.get('complete'):add('incomplete_render_coverage')
    return {'schema':1,'clean':not findings,'findings':findings,'paragraphs':len(expected),'fact_bindings':sum(bool(r.get('fact_id')) for r in bindings)}
