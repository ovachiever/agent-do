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

    def test_inline_fact_binding_does_not_split_layout_analysis(self):
        result=self.audit('<p data-copy-id="p1" style="width:9ch">one two <span data-fact-id="n">three</span></p>')
        self.assertEqual(result['findings']['orphans'][0]['last_word'],'three')
        self.assertEqual(result['text']['copies']['p1'],'one two three')

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

    def test_closed_details_only_measure_the_first_summary(self):
        result = self.audit('<details id="closed"><summary><span>Visible summary</span></summary>'
                            '<p data-copy-id="hidden" style="width:9ch">one two three</p>'
                            '<div style="height:10px;overflow:hidden">Hidden caption</div>'
                            '<summary>Hidden second summary</summary>'
                            '<span data-fact-id="hidden" data-value="42">42</span></details>')
        self.assertEqual(result['text']['rendered'].strip(), 'Visible summary')
        self.assertNotIn('hidden', result['text']['copies'])
        self.assertFalse(result['fact_marks'][0]['visible'])
        self.assertTrue(result['clean'], result['findings'])
        self.assertFalse(self.browser.evaluate('document.querySelector("details").open'))

    def test_nested_summary_cannot_escape_a_closed_outer_details(self):
        result = self.audit('<details><summary>Outer summary</summary>'
                            '<details open><summary>Hidden inner summary</summary>'
                            '<p>Hidden inner content.</p></details></details>'
                            '<details open><summary>Open summary</summary>'
                            '<details><summary>Visible inner summary</summary>'
                            '<p>Hidden nested content.</p></details></details>')
        self.assertNotIn('Hidden', result['text']['rendered'])
        self.assertIn('Visible inner summary', result['text']['rendered'])
        self.assertTrue(result['clean'], result['findings'])

    def test_open_details_still_report_real_layout_defects(self):
        result = self.audit('<details open><summary>Summary</summary>'
                            '<p style="width:9ch">one two three</p>'
                            '<div style="width:80px;overflow:hidden;white-space:nowrap">A long hidden caption.</div></details>')
        self.assertTrue(result['findings']['orphans'])
        self.assertTrue(result['findings']['clipped_text'])

    def test_scrollable_text_below_the_fold_is_not_clipped_by_the_shell(self):
        body = '<div id="shell"><main id="scroll"><p>First visible row.</p>' + ''.join(
            '<p>Reachable row ' + str(i) + '.</p>' for i in range(30)) + '</main></div>'
        for overflow in ('hidden', 'clip'):
            with self.subTest(overflow=overflow):
                result = self.audit(body, '#shell{height:150px;overflow:' + overflow + ';border:5px solid}'
                                    '#scroll{height:100%;overflow:auto}p{margin:0}')
                self.assertIn('Reachable row 29.', result['text']['rendered'])
                self.assertFalse(result['findings']['clipped_text'], result['findings'])
                self.assertFalse(result['findings']['overflow'], result['findings'])
                self.assertTrue(result['clean'], result['findings'])

    def test_horizontal_scrolling_is_reachable_through_a_hidden_shell(self):
        result = self.audit('<div id="shell"><div id="scroll"><p>Reachable horizontal caption.</p></div></div>',
                            '#shell{width:160px;overflow:hidden}#scroll{width:100%;overflow:auto}'
                            'p{margin:0;width:1000px;white-space:nowrap}')
        self.assertFalse(result['findings']['clipped_text'], result['findings'])
        self.assertFalse(result['findings']['overflow'], result['findings'])

    def test_a_scroll_container_does_not_hide_a_clip_inside_it(self):
        result = self.audit('<div id="shell"><div id="scroll"><div style="height:300px"></div>'
                            '<p id="cut">A long hidden caption.</p></div></div>',
                            '#shell{height:150px;overflow:hidden}#scroll{height:100%;overflow:auto}'
                            '#cut{width:80px;overflow:hidden;white-space:nowrap}')
        self.assertIn('#cut', {f['clipped_by'] for f in result['findings']['clipped_text']})

    def test_scroll_reachability_is_per_axis(self):
        result = self.audit('<div id="shell"><div id="scroll"><p>A long hidden caption.</p>'
                            '<div style="height:300px"></div></div></div>',
                            '#shell{width:160px;height:120px;overflow:hidden}'
                            '#scroll{width:400px;height:100%;overflow-y:auto;overflow-x:hidden}'
                            'p{white-space:nowrap;margin:0}')
        self.assertIn('#shell', {f['clipped_by'] for f in result['findings']['clipped_text']})

    def test_content_before_the_scroll_origin_is_still_inaccessible(self):
        result = self.audit('<div id="shell"><div id="scroll"><p id="unreachable">Unreachable row.</p>'
                            '<div style="height:600px"></div></div></div>',
                            '#shell{margin-top:100px;height:150px;overflow:hidden}'
                            '#scroll{position:relative;height:100%;overflow:auto}'
                            '#unreachable{position:absolute;top:-60px;margin:0}')
        self.assertIn('#shell', {f['clipped_by'] for f in result['findings']['clipped_text']})

    def test_rtl_horizontal_scroll_reachability(self):
        result = self.audit('<div id="shell"><div id="scroll"><p>Reachable horizontal caption.</p></div></div>',
                            '#shell{margin-left:400px;width:160px;overflow:hidden}'
                            '#scroll{direction:rtl;width:100%;overflow:auto}'
                            'p{margin:0;white-space:nowrap}')
        self.assertFalse(result['findings']['clipped_text'], result['findings'])

    def test_clipped_scrollport_and_unrelated_scroller_remain_findings(self):
        fixtures = (
            ('<div id="shell"><div id="scroll"><div style="height:200px"></div><p>Cut off row.</p>'
             '<div style="height:600px"></div></div></div>', '#scroll{height:300px;overflow:auto}'),
            ('<div id="shell"><div id="scroll"><div style="height:600px"></div></div>'
             '<p>Unreachable sibling.</p></div>', '#scroll{height:120px;overflow:auto}')
        )
        for body, css in fixtures:
            with self.subTest(body=body):
                result = self.audit(body, '#shell{height:100px;overflow:hidden}' + css)
                self.assertIn('#shell', {f['clipped_by'] for f in result['findings']['clipped_text']})

    def test_declared_clamp_with_related_control_is_accepted_without_clicking(self):
        result = self.audit('<div id="excerpt" data-polish-clamp>one two<br>three</div>'
                            '<button id="expand" aria-expanded="false" aria-controls="excerpt" '
                            'onclick="throw new Error(\'must not click\')">Read more</button>',
                            '#excerpt{height:30px;overflow:hidden}button{font:inherit}')
        self.assertTrue(result['clean'], result['findings'])
        self.assertEqual(result['coverage']['intentional_clamps'][0]['selector'], '#excerpt')
        self.assertEqual(result['coverage']['intentional_clamps'][0]['control'], '#expand')
        self.assertEqual(self.browser.evaluate('document.querySelector("button").getAttribute("aria-expanded")'), 'false')

    def test_local_disclosure_control_accepts_an_unambiguous_clamp(self):
        result = self.audit('<section><div data-polish-clamp>one two<br>three</div>'
                            '<button aria-expanded="false">Read more</button></section>',
                            '[data-polish-clamp]{height:30px;overflow:hidden}button{font:inherit}')
        self.assertTrue(result['clean'], result['findings'])
        self.assertEqual(len(result['coverage']['intentional_clamps']), 1)

    def test_line_clamp_with_disclosure_does_not_report_a_hidden_orphan(self):
        result = self.audit('<p id="excerpt" data-polish-clamp>one two<br>three</p>'
                            '<button aria-expanded="false" aria-controls="excerpt">Read more</button>',
                            '#excerpt{margin:0;display:-webkit-box;-webkit-box-orient:vertical;'
                            '-webkit-line-clamp:1;overflow:hidden}button{font:inherit}')
        self.assertTrue(result['clean'], result['findings'])

    def test_clamp_marker_without_an_available_related_control_is_not_an_exemption(self):
        controls = (
            '',
            '<button aria-expanded="true" aria-controls="excerpt">Read less</button>',
            '<button aria-expanded="false" aria-controls="unrelated">Read more</button>',
            '<button disabled aria-expanded="false" aria-controls="excerpt">Read more</button>',
            '<button hidden aria-expanded="false" aria-controls="excerpt">Read more</button>',
            '<button aria-disabled="true" aria-expanded="false" aria-controls="excerpt">Read more</button>',
            '<div inert><button aria-expanded="false" aria-controls="excerpt">Read more</button></div>',
            '<span aria-expanded="false" aria-controls="excerpt">Read more</span>',
        )
        for control in controls:
            with self.subTest(control=control):
                result = self.audit('<p id="excerpt" data-polish-clamp>one two<br>three</p>' + control,
                                    '#excerpt{height:30px;overflow:hidden}')
                self.assertEqual(result['coverage']['intentional_clamps'], [])
                self.assertTrue(result['findings']['clipped_text'])
                self.assertTrue(result['findings']['overflow'])

    def test_control_does_not_exempt_an_unmarked_clip(self):
        result = self.audit('<p id="excerpt">one two<br>three</p>'
                            '<button aria-expanded="false" aria-controls="excerpt">Read more</button>',
                            '#excerpt{height:30px;overflow:hidden}')
        self.assertTrue(result['findings']['clipped_text'])
        self.assertTrue(result['findings']['overflow'])

    def test_clamp_exemption_does_not_hide_horizontal_or_inner_clipping(self):
        result = self.audit('<div id="excerpt" data-polish-clamp>'
                            '<div id="inner">A long hidden caption.</div><br>one two</div>'
                            '<button aria-expanded="false" aria-controls="excerpt">Read more</button>',
                            '#excerpt{width:80px;height:60px;overflow:hidden;white-space:nowrap}'
                            '#inner{width:40px;overflow:hidden}')
        self.assertIn('#inner', {f['clipped_by'] for f in result['findings']['clipped_text']})
        self.assertTrue(any(f['axis'] == 'x' for f in result['findings']['overflow']))

    def test_visible_orphan_inside_a_clamp_is_still_reported(self):
        result = self.audit('<p id="excerpt" data-polish-clamp>one two<br>three<br>four five</p>'
                            '<button aria-expanded="false" aria-controls="excerpt">Read more</button>',
                            '#excerpt{height:60px;overflow:hidden}')
        self.assertEqual(result['findings']['orphans'][0]['last_word'], 'three')

    def test_br_is_a_rendered_word_boundary(self):
        result = self.audit('<p data-copy-id="p1">First line<br>Second line</p>')
        self.assertEqual(result['text']['copies']['p1'], 'First line Second line')

    def test_transparent_or_offscreen_copy_does_not_count(self):
        result = self.audit('<p data-copy-id="p1" style="color:transparent">Invisible.</p><p data-copy-id="p2" style="position:absolute;left:-9000px">Offscreen.</p>')
        self.assertEqual(result['text']['copies'], {})

    def test_svg_rectangular_clip_path_is_measured(self):
        result=self.audit('<svg width="400" height="80"><defs><clipPath id="clip"><rect width="80" height="60"/></clipPath></defs><g clip-path="url(#clip)"><text x="20" y="30">Long clipped caption</text></g></svg>')
        self.assertTrue(result['findings']['clipped_text'])
        self.assertTrue(any('clipPath' in f['clipped_by'] for f in result['findings']['clipped_text']))

    def test_uninspectable_generated_text_cannot_pass(self):
        result=self.audit('<p>Owner copy.</p>','p::after{content:"Invented motto."}')
        self.assertFalse(result['complete']);self.assertTrue(result['coverage']['uninspected_generated_content'])


if __name__ == '__main__':
    (TOOL.parents[1] / '.dev').mkdir(exist_ok=True)
    unittest.main()
