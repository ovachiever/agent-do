"""Real browser regression fixtures, exercised through agent-do browse."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))
from design_browser import Browser


class PolishBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="design-polish-", dir=TOOL.parents[1] / ".dev")
        cls.browser = Browser()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.directory.cleanup()

    def audit(self, body, css="", width=800, height=600, config=None):
        page = Path(self.directory.name) / (uuid.uuid4().hex + ".html")
        page.write_text('<!doctype html><meta charset="utf-8"><style>'
                        'body{margin:20px;font:20px/30px monospace}*{box-sizing:border-box}'
                        + css + '</style>' + body)
        return self.browser.polish(page.as_uri(), (width, height), config or {})

    def test_inline_text_boundaries_and_actual_viewport(self):
        result = self.audit('<p data-copy-id="p1">All <em>six</em> at once.</p>')
        self.assertEqual(result['viewport']['width'], 800)
        self.assertEqual(result['text']['rendered'].strip(), 'All six at once.')
        self.assertEqual(result['text']['copies']['p1'], 'All six at once.')
        self.assertTrue(result['clean'], result['findings'])

    def test_orphan_across_nested_inline_nodes(self):
        result = self.audit('<p style="width:9ch">one two <em>three</em></p>')
        self.assertTrue(result['findings']['orphans'])
        self.assertEqual(result['findings']['orphans'][0]['last_word'], 'three')

    def test_protected_long_label_has_no_character_exemption(self):
        label = 'An explicitly protected caption with far more than sixty characters in this fixture'
        result = self.audit('<label style="display:block;width:24ch">' + label + '</label>')
        self.assertTrue(result['findings']['phrase_wraps'])
        self.assertGreater(len(result['findings']['phrase_wraps'][0]['text']), 60)

    def test_duplicates_include_short_sentences_and_inline_text(self):
        result = self.audit('<p>You <em>decide.</em></p><p>You decide.</p>')
        self.assertEqual(result['findings']['duplicates'][0]['count'], 2)

    def test_control_alignment_threshold_scales_with_type(self):
        body = '<div class="pair"><p>Reference text<br>Second line<br>Third line<br>Fourth line</p><div><button>Open</button></div></div>'
        css = '.pair{display:grid;grid-template-columns:1fr 1fr;align-items:start}.pair p{margin:0}button{font:inherit}'
        result = self.audit(body, css)
        finding = result['findings']['floating_controls'][0]
        self.assertEqual(finding['tolerance_px'], 30)
        self.assertIn('line-height', finding['threshold_source'])
        centered = self.audit(body, css + '.pair{align-items:center}')
        self.assertFalse(centered['findings']['floating_controls'])

    def test_explicit_top_alignment_is_measured_against_top(self):
        body = '<div id="pair"><p>Reference<br>Second line<br>Third line</p><button>Open</button></div>'
        result = self.audit(body, '#pair{display:flex;align-items:start;gap:2em}p{margin:0}button{font:inherit}',
                            config={'alignments':[{'selector':'#pair','mode':'top','source':'fixture brief'}]})
        self.assertFalse(result['findings']['floating_controls'])

    def test_svg_caption_clipped_by_viewbox(self):
        result = self.audit('<svg width="100" height="50" viewBox="0 0 100 50" style="overflow:hidden"><text x="80" y="25">Clipped caption</text></svg>')
        self.assertTrue(result['findings']['clipped_text'])
        self.assertGreater(result['coverage']['svg_text_runs'], 0)

    def test_hidden_overflow_cannot_make_text_pass(self):
        result = self.audit('<div style="width:80px;overflow:hidden;white-space:nowrap">A long hidden caption.</div>')
        self.assertTrue(result['findings']['clipped_text'])
        self.assertTrue(result['findings']['overflow'])

    def test_document_horizontal_overflow(self):
        result = self.audit('<div style="width:2000px">Visible text.</div>')
        self.assertTrue(result['findings']['overflow'])

    def test_hidden_text_is_not_copy(self):
        result = self.audit('<p>Visible.</p><p data-copy-id="p1" hidden>Secret copy.</p>')
        self.assertNotIn('Secret', result['text']['rendered'])
        self.assertNotIn('p1', result['text']['copies'])


if __name__ == '__main__':
    (TOOL.parents[1] / '.dev').mkdir(exist_ok=True)
    unittest.main()
