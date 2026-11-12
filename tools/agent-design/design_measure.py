"""Measurements are observations. Semantic annotations carry their own provenance."""
import base64
import csv
import html
import io
import json
from pathlib import Path
import shutil
from statistics import median

from design_browser import Browser, DesignError, command, TOOL
from design_contract import digest,normalize
from design_provider import png_size
from design_state import write_new


def image_ocr(path):
    binary=shutil.which('tesseract')
    if not binary:raise DesignError('image measurement needs the existing tesseract CLI for TSV bounding boxes; no OCR values were guessed')
    text=command([binary,str(path),'stdout','tsv'])
    words=[]
    for row in csv.DictReader(io.StringIO(text),delimiter='\t',quoting=csv.QUOTE_NONE):
        if not row.get('text','').strip():continue
        words.append({'text':row['text'],'confidence':float(row['conf']),
                      **{key:int(row[key]) for key in ('left','top','width','height','block_num','par_num','line_num','word_num')}})
    return words,text


def validate_regions(regions,width,height):
    ids=set()
    for region in regions:
        if not isinstance(region,dict) or not region.get('id') or region['id'] in ids:raise DesignError('image regions require unique IDs')
        ids.add(region['id'])
        if not region.get('source'):raise DesignError('each semantic region annotation requires its source')
        if any(isinstance(region.get(k),bool) or not isinstance(region.get(k),int) for k in ('x','y','width','height')):raise DesignError('region bounds must be integer image pixels')
        if not (region['x']>=0 and region['y']>=0 and region['width']>0 and region['height']>0 and
                region['x']+region['width']<=width and region['y']+region['height']<=height):raise DesignError('annotated region is outside the image: '+region['id'])


def lines_from_words(words):
    groups={}
    for word in words:groups.setdefault(tuple(word[k] for k in ('block_num','par_num','line_num')),[]).append(word)
    lines=[]
    for key,items in groups.items():
        x=min(w['left'] for w in items);y=min(w['top'] for w in items)
        right=max(w['left']+w['width'] for w in items);bottom=max(w['top']+w['height'] for w in items)
        lines.append({'id':'.'.join(map(str,key)),'text':' '.join(w['text'] for w in items),
                      'x':x,'y':y,'width':right-x,'height':bottom-y,'words':items,
                      'method':'Tesseract TSV observed line union; OCR text is not authoritative copy'})
    return sorted(lines,key=lambda l:(l['y'],l['x']))


def measure_image(path,contract,folder,regions=None,browser=None):
    path=Path(path);folder=Path(folder);regions=regions or []
    data=path.read_bytes();width,height=png_size(data);validate_regions(regions,width,height)
    words,tsv=image_ocr(path);write_new(folder/'ocr.tsv',tsv)
    lines=lines_from_words(words)
    # Auto samples are observations only: a modal color is not silently named ground or ink.
    auto=[{'id':'whole-image','x':0,'y':0,'width':width,'height':height,'role':None,'source':'original image dimensions'}]
    auto.extend({'id':'ocr-'+line['id'],**{k:line[k] for k in ('x','y','width','height')},'role':None,'source':'ocr.tsv line '+line['id']} for line in lines)
    samples=auto+regions
    payload='data:image/png;base64,'+base64.b64encode(data).decode()
    write_new(folder/'measurement-source.html','<!doctype html><meta charset="utf-8"><img alt="Measurement source" src="'+payload+'">')
    own=browser is None;browser=browser or Browser()
    try:
        target=contract['viewports'][0]
        browser.open((folder/'measurement-source.html').resolve().as_uri(),(target['width'],target['height']))
        pixels=browser.evaluate('('+(TOOL/'measure.js').read_text()+')('+json.dumps(samples)+')')
    finally:
        if own:browser.close()
    write_new(folder/'pixel-samples.json',pixels)
    roles=[]
    for node in contract['nodes']:
        if not node.get('text'):continue
        matched=[line for line in lines if normalize(line['text'])==normalize(node['text'])]
        roles.append({'node_id':node['id'],'role':node.get('role'),'matches':[l['id'] for l in matched],
                      'glyph_box_heights_px':[l['height'] for l in matched] or None,
                      'css_font_size':None,'font_family':None,'font_weight':None,
                      'method':'exact label match against OCR lines; glyph boxes are not CSS font sizes'})
    gaps=[]
    for i,left in enumerate(lines):
        for right in lines[i+1:]:
            overlap=min(left['y']+left['height'],right['y']+right['height'])-max(left['y'],right['y'])
            gap=right['x']-(left['x']+left['width'])
            if overlap>0 and gap>0:gaps.append({'between':[left['id'],right['id']],'width_px':gap,'fraction_of_image':gap/width,'method':'horizontal empty interval between overlapping OCR line boxes, not inferred column gutter'})
    sections=sorted((r for r in regions if r.get('role')=='section'),key=lambda r:(r['y'],r['x']))
    columns=sorted((r for r in regions if r.get('role')=='column'),key=lambda r:r['x'])
    named={}
    for role in ('ground','ink','accent'):
        named[role]=[{'region':s['id'],'dominant':s['colors'][0], 'source':s['source'],
                      'sampled_pixels':s['pixels'],'method':s['method']} for s in pixels['samples'] if s.get('role')==role] or None
    result={'schema':1,'image_sha256':digest(data),'dimensions':{'width':width,'height':height,'units':'image pixels'},
            'color_space':pixels['color_space'],'palette':named,
            'dominant_color_observation':pixels['samples'][0]['colors'][0],
            'palette_note':'Semantic color roles require region evidence. All tied modal colors, region areas and distinct color counts are in pixel-samples.json.',
            'text':{'lines':lines,'median_word_height_px':median([w['height'] for w in words]) if words else None,'roles':roles},
            'geometry':{'observed_text_gaps':gaps,'column_edges':[{'left':r['x'],'right':r['x']+r['width'],'source':r['source']} for r in columns] or None,
                        'column_gutters':[{'width_px':b['x']-a['x']-a['width'],'between':[a['id'],b['id']]} for a,b in zip(columns,columns[1:])] or None,
                        'sections':[{**r,'height_fraction':r['height']/height,'top_fraction':r['y']/height} for r in sections] or None},
            'diagrams':[{**r,'kind':r.get('kind'),'kind_source':r['source'] if r.get('kind') else None} for r in regions if r.get('role')=='diagram'] or None,
            'annotations':regions,'facts_source':contract['source'],'unknowns':'Null means unavailable, never a measured zero or permission to invent facts.'}
    overlay=['<svg xmlns="http://www.w3.org/2000/svg" width="'+str(width)+'" height="'+str(height)+'" viewBox="0 0 '+str(width)+' '+str(height)+'">',
             '<image href="'+payload+'" width="100%" height="100%"/>']
    for r in [*lines,*regions]:
        overlay.append('<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="none" stroke="magenta"><title>{label}</title></rect>'.format(**r,label=html.escape(r.get('text',r['id']))))
    overlay.append('</svg>');write_new(folder/'regions.svg',''.join(overlay))
    write_new(folder/'measurement.json',result)
    return result


def measure(record,regions=None,dry_run=False):
    record.require('images_ruled','measured')
    selected=record.state.get('selected_images',[])
    if not selected:raise DesignError('the image ruling selected no images; a new design round needs an owner ruling')
    annotations=regions or {}
    if set(annotations)-set(selected):raise DesignError('regions reference an image not selected by the owner')
    images={i['id']:i for i in record.state['images']}
    for key in selected:
        image=images[key];path=record.resolve(image['path'])
        if digest(path.read_bytes())!=image['sha256']:raise DesignError('selected image changed: '+key)
        validate_regions(annotations.get(key,[]),*png_size(path.read_bytes()))
    if dry_run:return {'dry_run':True,'selected':selected,'paid_requests':0,'ocr_available':bool(shutil.which('tesseract'))}
    for key in selected:
        region_hash=digest(json.dumps(annotations.get(key,[]),sort_keys=True))
        existing=record.state['measurements'].get(key)
        if existing:
            if existing['regions_sha256']!=region_hash:raise DesignError('measurement annotations changed; keep this round and start a revised round')
            if digest(record.resolve(existing['path']).read_bytes())!=existing['sha256']:raise DesignError('measurement receipt changed')
            continue
        folder=record.attempt('measurements/'+key)
        result=measure_image(record.resolve(images[key]['path']),record.contract(),folder,annotations.get(key,[]))
        measurement=folder/'measurement.json'
        record.state['measurements'][key]={'path':str(measurement.relative_to(record.path)),'sha256':digest(measurement.read_bytes()),
                                          'regions_sha256':region_hash,'image_sha256':result['image_sha256']}
        record.save('measured chosen image '+key)
    if record.state['stage']=='images_ruled':record.transition('measured')
    return {'stage':record.state['stage'],'measurements':record.state['measurements']}
