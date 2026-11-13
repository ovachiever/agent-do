"""Dashboard transport regressions; no model calls or real credentials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
TOOL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOL));sys.path.insert(0,str(TOOL/'test'))
from design_contract import compile_contract,prompts,validate_prompts
from design_browser import DesignError
from design_provider import Provider,image_size
from design_imagine import imagine
from design_state import Round
from design_ballot import make_ballot,validate_ballot_size,BALLOT_MAX_BYTES,compact_png
from test_contract import facts
from test_provider import lookup

class DashboardTests(unittest.TestCase):
    def test_labels_only_compact_provenance_and_viewport(self):
        f=facts();f['viewports']=[{'width':1440,'height':1000}]
        f['nodes'] += [{'id':f'repo-{i}','text':f'repository-{i}','data':{'tickets':i}} for i in range(20)]
        c=compile_contract('',f,'/Users/private/a/very/long/path/facts.json')
        self.assertEqual(c['paragraphs'],[])
        self.assertIn('/Users/private',c['source'])
        for text in prompts('',c).values():
            self.assertNotIn('/Users/private',text)
            self.assertIn('1440 by 1000',text)
            self.assertNotIn('Use portrait framing',text)
            for i in range(20):self.assertIn(f'repository-{i}',text)
        self.assertLess(max(validate_prompts(prompts('',c)).values()),10000)

    def test_overlength_refused_before_freeze_and_transport(self):
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp:
            with Round(Path(tmp)/'round',create=True) as r:
                with self.assertRaises(DesignError):r.initialize('X'*32001,facts())
                self.assertFalse((r.path/'initialization.json').exists())
            with patch('design_provider.agent_do') as creds,patch('urllib.request.urlopen') as http:
                with self.assertRaises(DesignError):Provider().post('images/generations',{'prompt':'X'*32001},Path(tmp)/'request')
                creds.assert_not_called();http.assert_not_called()
                self.assertFalse((Path(tmp)/'request').exists())

    def test_dry_run_validates_frozen_legacy_prompt_before_authority(self):
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp,Round(Path(tmp)/'r',create=True) as r:
            r.initialize('',facts())
            r.resolve(r.state['prompts']['exact']['path']).write_text('X'*32001)
            with patch('design_imagine.authority') as authority:
                with self.assertRaises(DesignError):imagine(r,dry_run=True,lookup=authority)
                authority.assert_not_called()

    def test_landscape_and_scroll_sizes(self):
        limits=lookup('image')['limits']
        w,h=map(int,image_size(limits,viewport={'width':1440,'height':1000}).split('x'))
        self.assertGreater(w,h);self.assertEqual(w/h,1.44)
        self.assertEqual(image_size(limits),'2160x3840')
        self.assertEqual(image_size(limits,'1440x1008',{'width':1440,'height':1000}),'1440x1008')
        with self.assertRaises(DesignError):image_size(limits,'99999x1',{'width':1,'height':1})

    def test_wire_body_preserves_long_unicode_prompt(self):
        from test_provider import io
        class Response:
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b'{"data":[]}'
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp:
            p=Provider();p._key='synthetic-test'
            prompt='Dashboard café 中文 '*1000
            with patch('urllib.request.urlopen',return_value=Response()) as transport:
                p.post('images/generations',{'prompt':prompt},tmp)
            self.assertEqual(json.loads(transport.call_args.args[0].data)['prompt'],prompt)
            from design_contract import digest
            receipt=json.loads((Path(tmp)/'request.json').read_text())
            self.assertEqual(receipt['request_sha256'],digest(transport.call_args.args[0].data))
            self.assertEqual(receipt['prompt_characters'],len(prompt))

    def test_local_ballot_has_no_external_payload_limit_and_keeps_webp_type(self):
        s=make_ballot('test',[{'label':'1','kind':'images','bytes':b'fixture','width':1440,'height':1000,'mime':'image/webp'}])
        self.assertIn('data:image/webp;base64',s)
        self.assertEqual(validate_ballot_size(s),len(s.encode()))
        self.assertIsNone(BALLOT_MAX_BYTES)
        self.assertEqual(validate_ballot_size('x'*(16*1024*1024)),16*1024*1024)

if __name__=='__main__':unittest.main()
