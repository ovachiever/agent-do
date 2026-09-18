import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOL))
from design_browser import DesignError
from design_contract import compile_contract, prompts, check_copy
from design_state import Round


def facts():
    return {'schema':1,'id':'test-surface','title':'Test surface','frame':{'paper':'#ffffff','ink':'#111111','bodySize':20},
            'groups':[{'id':'main','order':0,'productions':['field']}],
            'nodes':[{'id':'open','role':'action','kind':'action','group':'main','text':'Open'},
                     {'id':'score','role':'figure','kind':'text','group':'main','text':'42%'}],
            'viewports':[{'id':'desktop','width':800,'height':600}]}


class ContractTests(unittest.TestCase):
    def test_complete_copy_and_labels_in_all_levels(self):
        copy='A complete paragraph.\n\nThe next paragraph is here.'
        c=compile_contract(copy,facts())
        p=prompts(copy,c)
        self.assertEqual(set(p),{'exact','half','open'})
        for level, text in p.items():
            self.assertIn(copy,text)
            self.assertIn('42%',text)
            self.assertIn('Open',text)
            self.assertIn('No icons',text)
        self.assertNotIn('#111111',p['open'])
        self.assertIn('palette, typefaces',p['open'])
        self.assertNotIn('productions',json.dumps(c))

    def test_duplicate_node_ids_and_foreign_body_prose_rejected(self):
        v=facts();v['nodes'].append(dict(v['nodes'][0]))
        with self.assertRaises(DesignError):compile_contract('Owner copy.',v)
        v=facts();v['nodes'].append({'id':'hype','role':'body','text':'The ultimate platform.'})
        with self.assertRaises(DesignError):compile_contract('Owner copy.',v)

    def test_named_nodes_required_not_recursive_allowlist(self):
        with self.assertRaises(DesignError):compile_contract('Owner copy.',{'sentences':{'bad':'Invented.'}})
        v=facts();v['sentences']={'bad':'Old manifesto.'};v['forbidden']=['Brand new motto.']
        c=compile_contract('Owner copy.',v)
        self.assertNotIn('Old manifesto',json.dumps(c))
        self.assertNotIn('Brand new motto',json.dumps(c))

    def snapshot(self, extra=None):
        rows=[{'text':'Owner ','copy_id':'p1','node_id':None,'fact_id':None},
              {'text':'copy.','copy_id':'p1','node_id':None,'fact_id':None},
              {'text':'Open','copy_id':None,'node_id':'open','fact_id':None},
              {'text':'42%','copy_id':None,'node_id':'score','fact_id':'score'}]
        return {'complete':True,'text':{'copies':{'p1':'Owner copy.'},'bindings':rows+(extra or [])},'fact_marks':[]}

    def test_rendered_boundaries_and_exact_figure(self):
        c=compile_contract('Owner copy.',facts())
        self.assertTrue(check_copy(self.snapshot(),c)['clean'])
        s=self.snapshot();s['text']['bindings'][-1]['text']='43%'
        self.assertFalse(check_copy(s,c)['clean'])

    def test_short_invented_line_and_wrong_fact_binding_fail(self):
        c=compile_contract('Owner copy.',facts())
        s=self.snapshot([{'text':'Trust us.','node_id':None,'copy_id':None,'fact_id':None}])
        self.assertIn('stray_text',{e['code'] for e in check_copy(s,c)['findings']})
        s=self.snapshot();s['text']['bindings'][-1]['fact_id']='open'
        self.assertIn('wrong_fact',{e['code'] for e in check_copy(s,c)['findings']})

    def test_repeated_copy_and_missing_figure_fail(self):
        c=compile_contract('Owner copy.',facts())
        s=self.snapshot();s['text']['copies']['p1']='Owner copy. Owner copy.'
        self.assertFalse(check_copy(s,c)['clean'])
        s=self.snapshot();s['text']['bindings'].pop()
        self.assertIn('missing_node',{e['code'] for e in check_copy(s,c)['findings']})

    def test_copy_order_is_verified(self):
        c=compile_contract('First.\n\nSecond.',facts())
        s=self.snapshot();s['text']['copies']={'p1':'First.','p2':'Second.'}
        s['text']['bindings']=[{'text':'Second.','copy_id':'p2'},{'text':'First.','copy_id':'p1'}]+s['text']['bindings'][2:]
        self.assertIn('copy_order',{e['code'] for e in check_copy(s,c)['findings']})

    def test_chart_marks_require_their_actual_source_value(self):
        c=compile_contract('Owner copy.',facts())
        s=self.snapshot();s['fact_marks']=[{'fact_id':'score','value':'99%','visible':True}]
        self.assertIn('wrong_fact',{e['code'] for e in check_copy(s,c)['findings']})


class RoundTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev')
        self.path=Path(self.tmp.name)/'round'

    def tearDown(self):self.tmp.cleanup()

    def test_mutation_lock_and_append_only_history(self):
        with Round(self.path,create=True) as r:
            r.initialize('Owner copy.',facts())
            with self.assertRaises(DesignError):
                with Round(self.path):pass
            r.save('test receipt')
            self.assertEqual(len(list((self.path/'history').glob('*.json'))),2)
        with Round(self.path) as r:
            self.assertEqual(r.state['stage'],'briefed')
            self.assertEqual(r.contract()['nodes'][0]['id'],'open')

    def test_tampered_frozen_inputs_fail(self):
        with Round(self.path,create=True) as r:r.initialize('Owner copy.',facts())
        (self.path/'inputs/copy.md').write_text('Changed.')
        with self.assertRaises(DesignError):
            with Round(self.path):pass

    def test_illegal_stage_jump_rejected(self):
        with Round(self.path,create=True) as r:
            r.initialize('Owner copy.',facts())
            with self.assertRaises(DesignError):r.transition('pages_ready')

    def test_interrupted_initialization_resumes_original_bytes(self):
        self.path.mkdir()
        raw=json.dumps(facts(),indent=4)+'\n'
        (self.path/'initialization.json').write_text(json.dumps({'copy':'Owner copy.','facts':facts(),'source':'facts.json','raw_facts':raw}))
        with Round(self.path) as r:
            self.assertEqual(r.state['stage'],'briefed')
            self.assertEqual(r.resolve('inputs/facts.json').read_text(),raw)

    def test_nested_state_references_survive_checkpoints(self):
        with Round(self.path,create=True) as r:
            r.initialize('Owner copy.',facts());nested=r.state.setdefault('builders',{})
            r.save('checkpoint');nested['one']={'attempts':[]};r.save('second checkpoint')
        with Round(self.path) as r:self.assertIn('one',r.state['builders'])


if __name__=='__main__':
    (TOOL.parents[1]/'.dev').mkdir(exist_ok=True)
    unittest.main()
