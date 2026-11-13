"""Synthetic local receipt tests. Real browser/control coverage is in test_preview."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

TOOL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOL))
from design_ballot import prepare_ballot,import_ruling,STATE,ballot_fingerprint,make_ballot
from design_browser import DesignError
from design_contract import digest
from design_reproduce import reproduce
from test_reproduce import prepared_round,Builder,model


class BallotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev');self.root=Path(self.tmp.name)
        self.r=prepared_round(self.root/'round')
    def tearDown(self):self.r.__exit__(None,None,None);self.tmp.cleanup()
    def prepare(self,kind='images'):
        if kind=='images' and not self.r.state['ballots'].get(kind):self.r.state['stage']='images_ready'
        return prepare_ballot(self.r,kind,prepare_only=True)
    def submission(self,resolved=True,index=0,selected=None,note='  advance exactly\nKeep my whitespace. </script>  '):
        self.prepare();ballot=self.r.state['ballots']['images'];part=ballot['parts'][index]
        folder=self.r.resolve(ballot['path']);key=part['keys'][0]
        chosen=selected if selected is not None else ([part['labels'][0]] if resolved else [])
        state={'feedback':{key:note},'submitted_at':'2026-11-13T01:00:00Z'}
        source=STATE.sub(lambda _: '<script type="application/json" id="fb-state">'+json.dumps(state).replace('<','\\u003c')+'</script>',(folder/part['file']).read_text())
        self.assertEqual(ballot_fingerprint(source),part['fingerprint'])
        dest=folder/'local-reviews'/str(index)/uuid.uuid4().hex;dest.mkdir(parents=True)
        submitted=dest/'submitted.html';submitted.write_text(source)
        (dest/'owner-input.json').write_text(json.dumps({**state,'complete':resolved,'selected_labels':chosen}))
        receipt={'host':'local','review_url':'http://127.0.0.1:12345/test-fixture/review/'+str(index),
                 'review_version':dest.name,'read_at':state['submitted_at'],
                 'published_ballot_sha256':part['sha256'],'readback_sha256':digest(source),
                 'owner_input':'owner-input.json','selection_status':'complete' if resolved else 'needs_clarification',
                 'selected_labels':chosen,'selection_method':'explicit_local_controls'}
        rp=dest/'receipt.json';rp.write_text(json.dumps(receipt));return submitted,rp,note,key
    def test_multipart_waits_for_every_ruling_and_rejects_cross_part_choice(self):
        original=self.r.state['images'][0];self.r.state['images']=[{**original,'id':f'image-{i}'} for i in range(3)]
        sample={'label':'1','kind':'images','bytes':(self.r.path/'fixture.png').read_bytes(),'width':64,'height':96}
        limit=len(make_ballot('b-'+'a'*32+'-part1',[sample]).encode())+10
        with patch('design_ballot.BALLOT_MAX_BYTES',limit):self.prepare()
        ballot=self.r.state['ballots']['images'];self.assertEqual(len(ballot['parts']),3)
        for index,part in enumerate(ballot['parts']):
            submitted,rp,_,_=self.submission(index=index)
            receipt=json.loads(rp.read_text())
            if index==0:
                rp.write_text(json.dumps({**receipt,'selected_labels':[ballot['parts'][1]['labels'][0]]}))
                with self.assertRaises(DesignError):import_ruling(self.r,'images',submitted,rp)
                rp.write_text(json.dumps(receipt))
            import_ruling(self.r,'images',submitted,rp)
            if index<2:
                import_ruling(self.r,'images',submitted,rp);self.assertEqual(self.r.state['stage'],'image_ballot_pending')
        self.assertEqual(self.r.state['stage'],'images_ruled')
        self.assertEqual(set(self.r.state['selected_images']),{'image-0','image-1','image-2'})
        self.assertEqual(len(self.r.state['rulings']),3)
    def test_verbatim_local_ruling_and_idempotent_import(self):
        submitted,receipt,note,field=self.submission()
        result=import_ruling(self.r,'images',submitted,receipt)
        self.assertEqual(result['feedback'][field],note);self.assertEqual(result['stage'],'images_ruled')
        self.assertEqual(self.r.state['selected_images'],['image-fixture'])
        self.assertEqual(json.loads((self.r.path/'labels.yaml').read_text())['rulings'][0]['feedback'][field],note)
        self.assertEqual(import_ruling(self.r,'images',submitted,receipt)['status'],'ruling already recorded')
    def test_ambiguous_selection_remains_pending(self):
        submitted,receipt,_,_=self.submission(resolved=False)
        result=import_ruling(self.r,'images',submitted,receipt)
        self.assertEqual(result['stage'],'image_ballot_pending');self.assertEqual(result['status'],'selection needs clarification')
    def test_resolved_reading_of_same_notes_preserves_both_receipts(self):
        submitted,receipt,note,field=self.submission(resolved=False)
        import_ruling(self.r,'images',submitted,receipt)
        prior=self.r.resolve(self.r.state['rulings'][0]['path'])/'review-receipt.json';prior_bytes=prior.read_bytes()
        submitted,resolved,_,_=self.submission(resolved=True)
        result=import_ruling(self.r,'images',submitted,resolved)
        self.assertEqual(result['stage'],'images_ruled');self.assertEqual(len(self.r.state['rulings']),2)
        self.assertEqual(prior.read_bytes(),prior_bytes);self.assertEqual(self.r.state['rulings'][0]['selected_labels'],None)
        self.assertEqual(self.r.state['rulings'][1]['feedback'][field],note)
        self.assertEqual(import_ruling(self.r,'images',submitted,resolved)['status'],'ruling already recorded')
        submitted,rejected,_,_=self.submission(selected=[])
        with self.assertRaises(DesignError):import_ruling(self.r,'images',submitted,rejected)
    def test_import_before_ballot_has_a_structured_prerequisite_error(self):
        with self.assertRaisesRegex(DesignError,'no prepared images ballot'):import_ruling(self.r,'images',self.root/'absent.html',self.root/'absent.json')
    def test_changed_candidate_and_external_host_are_rejected(self):
        submitted,receipt,_,_=self.submission();original=submitted.read_text()
        submitted.write_text(original.replace('Candidate 1','Changed 1'))
        with self.assertRaises(DesignError):import_ruling(self.r,'images',submitted,receipt)
        submitted.write_text(original);value=json.loads(receipt.read_text());value['host']='claude';receipt.write_text(json.dumps(value))
        with self.assertRaisesRegex(DesignError,'local-only'):import_ruling(self.r,'images',submitted,receipt)
        value['host']='local';value['review_url']='https://example.com/fake';receipt.write_text(json.dumps(value))
        with self.assertRaises(DesignError):import_ruling(self.r,'images',submitted,receipt)
    def test_cloud_publishing_flags_are_unavailable(self):
        for flag in ('--publish','--claude-session=fixture'):
            result=subprocess.run([str(TOOL/'agent-design'),'ballot','images','--round',str(self.r.path),flag],capture_output=True,text=True)
            self.assertEqual(result.returncode,2);self.assertIn('unrecognized arguments',result.stderr)
        runtime=(TOOL/'ballot-runtime.js').read_text()
        self.assertNotIn('claude.use',runtime);self.assertNotIn('api.publish',runtime)
    def test_page_ballot_requires_actual_audits_and_sandboxed_frames(self):
        reproduce(self.r,provider=Builder(),lookup=model)
        result=self.prepare('pages');source=Path(result['ballot']).read_text()
        self.assertIn('sandbox="allow-scripts"',source);self.assertNotIn('allow-same-origin',source)
        audit=json.loads((Path(result['ballot']).parent/'chrome-audit.json').read_text())
        self.assertTrue(audit['clean']);self.assertEqual(len(audit['coverage']['independently_verified_frames']),1)
        self.assertNotIn('page-image-fixture',source)
        page=self.r.state['pages'][0];self.r.resolve(page['path']).write_text('tampered')
        with self.assertRaises(DesignError):prepare_ballot(self.r,'pages',dry_run=True)
