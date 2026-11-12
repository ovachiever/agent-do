"""A builder fixture repairs against real browser audits, never a mocked pass."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

TOOL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOL))
from design_contract import digest
from design_reproduce import reproduce,document_check
from design_state import Round,write_new
from test_contract import facts


def model(kind):return {'model':'provider-strongest-fixture','limits':{'reasoning':'max','max_output_tokens':128000},'documents':[]}

PAGE='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Fixture</title>
<style>body{margin:24px;font:20px/30px Arial;color:#111;background:#fff}button{font:inherit}</style>
<p data-copy-id="p1">Owner copy.</p><button data-node-id="open">Open</button>
<p data-node-id="score" data-fact-id="score">42%</p></html>'''


class Builder:
    def __init__(self):self.requests=[]
    def post(self,endpoint,payload,folder):
        self.requests.append(payload)
        page=PAGE+('<p>Trust us.</p>' if len(self.requests)==1 else '')
        receipt={'usage':{'input_tokens':100,'output_tokens':200},'response':{'status':'completed',
                 'output':[{'content':[{'type':'output_text','text':json.dumps({'html':page,'implementation_decisions':['Fixture source']})}]}]}}
        write_new(folder/'request.json',{'payload':payload});write_new(folder/'response.json',receipt);return receipt


def prepared_round(path):
    record=Round(path,create=True).__enter__()
    record.initialize('Owner copy.',facts())
    def chunk(tag,value):return struct.pack('>I',len(value))+tag+value+struct.pack('>I',zlib.crc32(tag+value))
    image=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,96,8,0,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff'*64)*96))+chunk(b'IEND',b'')
    write_new(record.path/'fixture.png',image)
    record.state['images']=[{'id':'image-fixture','path':'fixture.png','sha256':digest(image)}]
    record.transition('images_ready');record.transition('image_ballot_pending');record.transition('images_ruled')
    record.state['selected_images']=['image-fixture']
    measurement=write_new(record.path/'fixture-measurement.json',{'image_sha256':digest(image)})
    measurement['path']='fixture-measurement.json';record.state['measurements']={'image-fixture':measurement}
    record.transition('measured');return record


class ReproductionTests(unittest.TestCase):
    def test_repairs_until_actual_copy_and_polish_pass(self):
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp:
            r=prepared_round(Path(tmp)/'round')
            try:
                builder=Builder();result=reproduce(r,provider=builder,lookup=model)
                self.assertEqual(len(builder.requests),2)
                self.assertEqual(result['stage'],'pages_ready');self.assertEqual(len(result['pages']),1)
                self.assertEqual(builder.requests[0]['reasoning']['effort'],'max')
                self.assertIn('Trust us.',builder.requests[1]['input'][0]['content'][0]['text'])
                self.assertEqual(len(r.state['builders']['image-fixture']['attempts']),2)
                first=r.state['builders']['image-fixture']['attempts'][0]
                self.assertEqual(first['status'],'repair_needed')
                audit=json.loads(r.resolve(result['pages'][0]['audit']).read_text())
                self.assertTrue(audit['clean']);self.assertTrue(audit['viewports'][0]['copy']['clean'])
                self.assertTrue(r.resolve(result['pages'][0]['renders'][0]['path']).is_file())
                reproduce(r,provider=builder,lookup=model);self.assertEqual(len(builder.requests),2)
            finally:r.__exit__(None,None,None)

    def test_dry_run_does_not_launch_builder(self):
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp:
            r=prepared_round(Path(tmp)/'round')
            try:
                builder=Builder();result=reproduce(r,dry_run=True,provider=builder,lookup=model)
                self.assertEqual(result['paid_requests'],0);self.assertEqual(builder.requests,[])
                self.assertEqual(r.state['stage'],'measured')
            finally:r.__exit__(None,None,None)

    def test_executable_or_uninspectable_documents_never_run(self):
        for content in ('<script>location="https://example.com"</script>','<img src="page.png">','<svg></svg>','<button onclick="alert(1)">Open</button>'):
            self.assertTrue(document_check('<!doctype html>'+content))


if __name__=='__main__':
    (TOOL.parents[1]/'.dev').mkdir(exist_ok=True)
    unittest.main()
