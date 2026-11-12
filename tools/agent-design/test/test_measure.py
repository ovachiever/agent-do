"""Real image decoding, pixel sampling and OCR, without paid generation."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

TOOL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOL))
from design_browser import Browser,DesignError
from design_contract import compile_contract
from design_measure import measure_image,validate_regions
from test_contract import facts


class MeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev');cls.root=Path(cls.tmp.name)
        cls.browser=Browser()

    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.tmp.cleanup()

    def test_observed_pixels_and_unavailable_semantics(self):
        def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
        w,h=128,192
        data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes([20,40,60])*w)*h))+chunk(b'IEND',b'')
        image=self.root/'pixels.png';image.write_bytes(data)
        result=measure_image(image,compile_contract('Owner copy.',facts()),self.root/'pixels',
                  [{'id':'ground','role':'ground','source':'synthetic uniform region','x':0,'y':0,'width':128,'height':192}],self.browser)
        self.assertEqual(result['palette']['ground'][0]['dominant']['rgba'],[20,40,60,255])
        self.assertEqual(result['palette']['ground'][0]['sampled_pixels'],w*h)
        self.assertIsNone(result['geometry']['column_edges']);self.assertIsNone(result['diagrams'])
        self.assertTrue((self.root/'pixels/regions.svg').exists())

    def test_real_ocr_bounds_are_not_claimed_as_css_font_sizes(self):
        page=self.root/'text.html';page.write_text('<!doctype html><style>body{margin:40px;background:white;color:black;font:48px/1.5 monospace}</style>Open')
        self.browser.open(page.as_uri(),(640,480));image=self.root/'text.png';self.browser.screenshot(image)
        result=measure_image(image,compile_contract('Owner copy.',facts()),self.root/'text',browser=self.browser)
        role=next(r for r in result['text']['roles'] if r['node_id']=='open')
        self.assertTrue(role['matches']);self.assertGreater(role['glyph_box_heights_px'][0],0)
        self.assertIsNone(role['css_font_size']);self.assertIsNone(role['font_family'])

    def test_annotations_need_source_and_real_image_bounds(self):
        with self.assertRaises(DesignError):validate_regions([{'id':'x','x':0,'y':0,'width':10,'height':10}],100,100)
        with self.assertRaises(DesignError):validate_regions([{'id':'x','source':'fixture','x':90,'y':0,'width':11,'height':10}],100,100)


if __name__=='__main__':
    (TOOL.parents[1]/'.dev').mkdir(exist_ok=True)
    unittest.main()
