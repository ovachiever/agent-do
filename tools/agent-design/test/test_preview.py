"""Real loopback/browser tests on synthetic rounds; never owner approval evidence."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

TOOL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOL))
from design_ballot import prepare_ballot
from design_browser import Browser
from design_preview import make_server,launch,atomic_json
from design_state import Round
from test_reproduce import prepared_round


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev');self.root=Path(self.tmp.name)/'round'
        r=prepared_round(self.root)
        try:
            r.state['stage']='images_ready';r.state.pop('selected_images',None)
            prepare_ballot(r,'images',prepare_only=True)
            self.ballot=r.state['ballots']['images'];self.key=self.ballot['keys'][0]
        finally:r.__exit__(None,None,None)
        self.server=make_server(self.root,'images');self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=self.server.info['url'];self.origin='http://'+self.server.address
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close();self.tmp.cleanup()
    def post(self,body,origin=None):
        request=urllib.request.Request(self.url+'review/0',json.dumps(body).encode(),{'Origin':origin or self.origin,'Content-Type':'application/json'})
        with urllib.request.urlopen(request) as r:return json.load(r)
    def test_local_notes_reload_then_explicit_selection_through_browser(self):
        browser=Browser()
        try:
            browser.open(self.url+'part/0',(900,700))
            note='  Exact note\n</script>  '
            browser.evaluate('document.querySelector("textarea").value='+json.dumps(note))
            result=browser.evaluate('''(async()=>{document.querySelector('#fb-submit').click();
              while(document.querySelector('#fb-submit').disabled) await new Promise(r=>setTimeout(r,20));
              return document.querySelector('#fb-status').textContent})()''')
            self.assertIn('Saved.',result)
            with Round(self.root) as r:self.assertEqual(r.state['stage'],'image_ballot_pending')
            browser.open(self.url+'part/0',(900,700))
            self.assertEqual(browser.evaluate('document.querySelector("textarea").value'),note)
            result=browser.evaluate('''(async()=>{document.querySelector('[data-choice]').checked=true;
              document.querySelector('#confirm-selection').checked=true;document.querySelector('#fb-submit').click();
              while(document.querySelector('#fb-submit').disabled) await new Promise(r=>setTimeout(r,20));
              return document.querySelector('#fb-status').textContent})()''')
            self.assertIn('Saved.',result)
            with Round(self.root) as r:
                self.assertEqual(r.state['stage'],'images_ruled');self.assertEqual(r.state['selected_images'],['image-fixture'])
                self.assertEqual(r.state['rulings'][0]['feedback'][self.key],note)
                self.assertEqual(prepare_ballot(r,'images',prepare_only=True)['stage'],'images_ruled')
            with self.assertRaises(urllib.error.HTTPError):self.post({'feedback':{},'complete':True,'selected_labels':[]})
        finally:browser.close()
    def test_reject_all_is_explicit_and_needs_no_invented_note(self):
        self.post({'feedback':{},'complete':True,'selected_labels':[]})
        with Round(self.root) as r:self.assertEqual(r.state['selected_images'],[])
    def test_no_private_files_cross_origin_unknown_keys_or_implicit_choices(self):
        for path in ('manifest.json','../manifest.json','blind-key.json'):
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.url+path)
        valid={'feedback':{self.key:'test fixture'},'complete':False,'selected_labels':[]}
        with self.assertRaises(urllib.error.HTTPError):self.post(valid,'https://unrelated.example')
        for bad in ({**valid,'feedback':{'unknown':'text'}},{**valid,'selected_labels':['1']},{**valid,'complete':True,'selected_labels':['999']}):
            with self.assertRaises(urllib.error.HTTPError):self.post(bad)
        with Round(self.root) as r:self.assertNotIn('rulings',r.state)
    def test_launch_reuses_live_server_and_opens_default_browser(self):
        atomic_json(self.root/'.preview-images.json',self.server.info)
        with patch('design_preview.webbrowser.open',return_value=True) as opened,patch('design_preview.subprocess.Popen') as spawn:
            result=launch(self.root,'images');self.assertEqual(result['url'],self.url)
            opened.assert_called_once_with(self.url);spawn.assert_not_called()
