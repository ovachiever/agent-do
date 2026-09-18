"""Test the real self-saving script locally; no fixture is a publication receipt."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOL))
from design_ballot import prepare_ballot,import_ruling,STATE,ballot_fingerprint
from design_browser import Browser,DesignError
from design_contract import digest
from design_state import write_new
from design_reproduce import reproduce
from test_reproduce import prepared_round,Builder,model


class BallotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev');self.root=Path(self.tmp.name)
        self.r=prepared_round(self.root/'round');self.browser=Browser();self.drops=[]

    def tearDown(self):self.browser.close();self.r.__exit__(None,None,None);self.tmp.cleanup()

    def prepare(self,kind='images'):
        if kind=='images':self.r.state['stage']='images_ready' # Isolated test fixture, never a production stage bypass.
        return prepare_ballot(self.r,kind,target=lambda _: 'claude-test-fixture',
                              drop=lambda path,who,key:self.drops.append((path,who,key)) or 'test handoff only; not published')

    def submission(self,kind='images',resolved=True):
        result=self.prepare(kind);ballot=self.r.state['ballots'][kind]
        self.browser.open(Path(result['ballot']).as_uri(),(800,600))
        initial=self.browser.evaluate('({published:window.published || null,notes:document.querySelectorAll("textarea").length})')
        self.assertIsNone(initial['published'])
        note='  advance exactly\nKeep my whitespace. </script>  '
        field=ballot['keys'][0]
        script='''(async()=>{window.saved=new Promise(resolve=>window.resolveSaved=resolve);
          window.claude={use:async name=>({publish:async doc=>{window.published=doc;window.resolveSaved(doc)}})};
          document.querySelector('textarea').value=NOTE;
          document.querySelector('#fb-submit').click();return await window.saved})()'''.replace('NOTE',json.dumps(note))
        source=self.browser.evaluate(script)
        self.assertEqual(json.loads(STATE.search(source)[1])['feedback'][field],note)
        self.assertEqual(ballot_fingerprint(source),ballot['fingerprint'])
        submitted=self.root/'submitted.html';submitted.write_text(source)
        raw=self.root/'artifact-fixture.json';raw.write_text(json.dumps({'fixture_only':True,'html':source}))
        receipt={'host':'claude','artifact_url':'https://claude.ai/code/artifact/test-fixture','artifact_version':'fixture-version',
                 'read_at':'2026-09-18T23:00:00Z','published_ballot_sha256':ballot['sha256'],'readback_sha256':digest(source),
                 'artifact_read_receipt':str(raw),'selection_status':'complete' if resolved else 'needs_clarification',
                 'selected_labels':['1'],'selection_evidence':[{'label':'1','key':field,'quote':note}]}
        receipt_path=self.root/'receipt.json';receipt_path.write_text(json.dumps(receipt))
        return submitted,receipt_path,note,field

    def test_pending_handoff_and_verbatim_self_saving_readback(self):
        submitted,receipt,note,field=self.submission()
        self.assertEqual(self.r.state['stage'],'image_ballot_pending');self.assertEqual(len(self.drops),1)
        result=import_ruling(self.r,'images',submitted,receipt)
        self.assertEqual(result['feedback'][field],note);self.assertEqual(result['stage'],'images_ruled')
        self.assertEqual(self.r.state['selected_images'],['image-fixture'])
        labels=json.loads((self.r.path/'labels.yaml').read_text())
        self.assertEqual(labels['rulings'][0]['feedback'][field],note)
        self.assertEqual(import_ruling(self.r,'images',submitted,receipt)['status'],'ruling already recorded')

    def test_ambiguous_selection_remains_pending(self):
        submitted,receipt,_,_=self.submission(resolved=False)
        result=import_ruling(self.r,'images',submitted,receipt)
        self.assertEqual(result['stage'],'image_ballot_pending');self.assertEqual(result['status'],'selection needs clarification')

    def test_resolved_reading_of_same_notes_preserves_both_receipts(self):
        submitted,receipt,note,field=self.submission(resolved=False)
        import_ruling(self.r,'images',submitted,receipt)
        prior=self.r.resolve(self.r.state['rulings'][0]['path'])/'artifact-receipt.json'
        prior_bytes=prior.read_bytes()
        value=json.loads(receipt.read_text());value['selection_status']='complete'
        resolved=self.root/'resolved-receipt.json';resolved.write_text(json.dumps(value))
        result=import_ruling(self.r,'images',submitted,resolved)
        self.assertEqual(result['stage'],'images_ruled')
        self.assertEqual(len(self.r.state['rulings']),2)
        self.assertEqual(prior.read_bytes(),prior_bytes)
        self.assertEqual(self.r.state['rulings'][0]['selected_labels'],None)
        self.assertEqual(self.r.state['rulings'][1]['feedback'][field],note)
        self.assertEqual(import_ruling(self.r,'images',submitted,resolved)['status'],'ruling already recorded')
        value['selected_labels']=[];resolved.write_text(json.dumps(value))
        with self.assertRaises(DesignError):import_ruling(self.r,'images',submitted,resolved)

    def test_import_before_ballot_has_a_structured_prerequisite_error(self):
        with self.assertRaisesRegex(DesignError,'no prepared images ballot'):
            import_ruling(self.r,'images',self.root/'absent.html',self.root/'absent.json')

    def test_changed_candidate_or_fabricated_host_is_rejected(self):
        submitted,receipt,_,_=self.submission()
        original=submitted.read_text();submitted.write_text(original.replace('Candidate 1','Changed 1'))
        with self.assertRaises(DesignError):import_ruling(self.r,'images',submitted,receipt)
        submitted.write_text(original)
        value=json.loads(receipt.read_text());value['artifact_url']='https://example.com/fake';receipt.write_text(json.dumps(value))
        with self.assertRaises(DesignError):import_ruling(self.r,'images',submitted,receipt)

    def test_page_ballot_requires_actual_audits_and_sandboxed_frames(self):
        reproduce(self.r,provider=Builder(),lookup=model)
        result=self.prepare('pages');source=Path(result['ballot']).read_text()
        self.assertIn('sandbox="allow-scripts"',source);self.assertNotIn('allow-same-origin',source)
        audit=json.loads((Path(result['ballot']).parent/'chrome-audit.json').read_text())
        self.assertTrue(audit['clean']);self.assertEqual(len(audit['coverage']['independently_verified_frames']),1)
        self.assertNotIn('page-image-fixture',source)
        page=self.r.state['pages'][0];self.r.resolve(page['path']).write_text('tampered')
        with self.assertRaises(DesignError):prepare_ballot(self.r,'pages',dry_run=True)


if __name__=='__main__':
    (TOOL.parents[1]/'.dev').mkdir(exist_ok=True)
    unittest.main()
