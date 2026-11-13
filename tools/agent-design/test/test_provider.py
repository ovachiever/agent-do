import base64
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import io
import zlib

TOOL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOL))
from design_browser import DesignError
from design_provider import select_model,image_limits,portrait_size,text_limits,Provider,APIError
from design_imagine import imagine
from design_state import Round,write_new
from test_contract import facts

CATALOG='''- [Sunburst](/api/docs/models/gpt-image-2.5-sunburst.md): Our most capable model for image generation and editing
- [Flare](/api/docs/models/gpt-image-2.5-flare.md): Fast everyday image generation
- [Astra](/api/docs/models/gpt-6-astra.md): Our most capable model, built for the hardest end-to-end work'''
GUIDE='''`gpt-image-2.5-sunburst` and `gpt-image-2.5-flare` add `xhigh` and `max` quality settings. Earlier GPT Image models support quality settings up to `high`.
Width and height must be multiples of 16, the aspect ratio must be between 1:3 and 3:1, and neither edge may exceed 3840 pixels. The total pixel count must be between 655,360 and 8,294,400.'''

def lookup(kind,model=None):
    model=model or 'gpt-image-2.5-sunburst'
    return {'kind':kind,'model':model,'limits':image_limits(GUIDE,model),'documents':[],'checked_at':'test fixture'}


class FakeProvider:
    """Transport fixture only, never used by the production CLI."""
    def __init__(self,fail=None):self.calls=[];self.fail=fail
    def post(self,endpoint,payload,folder):
        self.calls.append(payload)
        write_new(folder/'request.json',{'payload':payload})
        if self.fail:
            error=self.fail;self.fail=None
            write_new(folder/'error.json',{'code':error.code});raise error
        w,h=map(int,payload['size'].split('x'))
        def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
        data=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,0,0,0,0))+
              chunk(b'IDAT',zlib.compress((b'\x00'+b'\xff'*w)*h))+chunk(b'IEND',b''))
        receipt={'response':{'data':[{'b64_json':base64.b64encode(data).decode()}]},'usage':'usage not returned','request_id':'fixture'}
        write_new(folder/'response.json',receipt);return receipt


class ProviderTests(unittest.TestCase):
    def test_latest_sunburst_despite_old_catalog_superlative(self):
        catalog=CATALOG+'\n- [Sunburst](/api/docs/models/gpt-image-2.6-sunburst.md): Image generation and editing for detailed visual work\n- [Flare](/api/docs/models/gpt-image-2.7-flare.md): Image generation for fast iteration'
        self.assertEqual(select_model(catalog,'image'),'gpt-image-2.6-sunburst')
        self.assertEqual(select_model(catalog,'text'),'gpt-6-astra')
        catalog+='\n- [Sunburst](/api/docs/models/gpt-image-2.10-sunburst.md): Image generation and editing'
        catalog+='\n- [Snapshot](/api/docs/models/gpt-image-2.11-sunburst-2026-11-12.md): Image generation and editing'
        self.assertEqual(select_model(catalog,'image'),'gpt-image-2.10-sunburst')

    def test_family_quality_must_explicitly_include_selected_generation(self):
        guide=GUIDE+'\nFor the Sunburst and Flare models in both GPT-Image-2.6 and GPT-Image-2.5, the quality options are `low`, `medium`, `high`, `xhigh`, and `max`.'
        self.assertEqual(image_limits(guide,'gpt-image-2.6-sunburst')['quality'],'max')
        with self.assertRaises(DesignError):image_limits(guide,'gpt-image-2.7-sunburst')
        with self.assertRaises(DesignError):image_limits(GUIDE,'gpt-image-2.6-sunburst')

    def test_strongest_models_not_speed_tiers(self):
        self.assertEqual(select_model(CATALOG,'image'),'gpt-image-2.5-sunburst')
        self.assertEqual(select_model(CATALOG,'text'),'gpt-6-astra')
        with self.assertRaises(DesignError):select_model('Unknown catalog','image')

    def test_published_maximums_not_local_caps(self):
        limits=image_limits(GUIDE,'gpt-image-2.5-sunburst')
        self.assertEqual(portrait_size(limits),'2160x3840')
        self.assertEqual(limits['quality'],'max')
        self.assertEqual(text_limits('`reasoning.effort` supports `low`, `high`, `max`.\n128,000 max output tokens'),{'reasoning':'max','max_output_tokens':128000})
        with self.assertRaises(DesignError):portrait_size(limits,'3840x2160')
        with self.assertRaises(DesignError):image_limits('Unknown sizes','gpt-image-2.5-sunburst')

    def test_fallback_only_genuine_model_availability(self):
        self.assertTrue(APIError(404,'model_not_found','missing').model_unavailable())
        for status,code in [(401,'invalid_api_key'),(403,'permission_denied'),(429,'rate_limit'),(500,'model_not_found'),(400,'invalid_request')]:
            self.assertFalse(APIError(status,code,'failure').model_unavailable())

    def test_secrets_redacted_in_provider_errors(self):
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp:
            p=Provider();p._key='test-secret'
            body=json.dumps({'error':{'code':'invalid_api_key','message':'test-secret sk-abcdef'}}).encode()
            error=urllib.error.HTTPError('https://api.openai.com',401,'failure',{},io.BytesIO(body))
            with patch('urllib.request.urlopen',side_effect=error),self.assertRaises(APIError):p.post('images/generations',{'model':'example'},tmp)
            saved=(Path(tmp)/'error.json').read_text()
            self.assertNotIn('test-secret',saved);self.assertNotIn('sk-abcdef',saved)

    def test_uncertain_transport_is_not_silently_retried(self):
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp:
            p=Provider();p._key='private'
            with patch('urllib.request.urlopen',side_effect=OSError('socket closed')) as call,self.assertRaises(DesignError):p.post('images/generations',{},tmp)
            self.assertEqual(call.call_count,1);self.assertTrue((Path(tmp)/'uncertain.json').exists())

    def test_count_runs_in_full_and_resume_does_not_regenerate(self):
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp,Round(Path(tmp)/'round',create=True) as r:
            r.initialize('Owner copy.',facts());p=FakeProvider()
            result=imagine(r,per_level=7,provider=p,lookup=lookup)
            self.assertEqual(len(result['images']),21)
            self.assertTrue(all(i['seed'] is None and i['usage']=='usage not returned' for i in result['images']))
            imagine(r,per_level=7,provider=p,lookup=lookup)
            self.assertEqual(len(p.calls),21)

    def test_availability_fallback_retains_both_attempts(self):
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp,Round(Path(tmp)/'round',create=True) as r:
            r.initialize('Owner copy.',facts());p=FakeProvider(APIError(404,'model_not_found','missing'))
            imagine(r,per_level=1,provider=p,lookup=lookup)
            self.assertEqual(p.calls[1]['model'],'gpt-image-2')
            self.assertEqual(p.calls[1]['quality'],'high')
            self.assertEqual(len(list(r.path.rglob('fallback.json'))),1)

    def test_invalid_image_receipt_is_retained_and_can_resume(self):
        class InvalidOnce(FakeProvider):
            def post(self,endpoint,payload,folder):
                if self.calls:return super().post(endpoint,payload,folder)
                self.calls.append(payload)
                write_new(folder/'request.json',{'payload':payload})
                receipt={'response':{'data':[{'b64_json':base64.b64encode(b'not a PNG').decode()}]},
                         'usage':{'output_tokens':7}}
                write_new(folder/'response.json',receipt);return receipt
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp,Round(Path(tmp)/'round',create=True) as r:
            r.initialize('Owner copy.',facts());p=InvalidOnce()
            with self.assertRaises(DesignError):imagine(r,per_level=1,provider=p,lookup=lookup)
            rejected=list(r.path.rglob('invalid-image.json'))
            self.assertEqual(len(rejected),1);original=(rejected[0].parent/'response.json').read_bytes()
            result=imagine(r,per_level=1,provider=p,lookup=lookup)
            self.assertEqual(result['stage'],'images_ready');self.assertEqual(len(p.calls),4)
            self.assertEqual((rejected[0].parent/'response.json').read_bytes(),original)
            self.assertEqual(len(r.state['usage']),4)

    def test_dry_run_never_calls_credentials_or_paid_transport(self):
        with tempfile.TemporaryDirectory(dir=TOOL.parents[1]/'.dev') as tmp,Round(Path(tmp)/'round',create=True) as r:
            r.initialize('Owner copy.',facts());p=FakeProvider()
            result=imagine(r,dry_run=True,provider=p,lookup=lookup)
            self.assertEqual(result['requests'],6);self.assertEqual(p.calls,[])
            self.assertEqual(r.state['stage'],'briefed')


if __name__=='__main__':
    (TOOL.parents[1]/'.dev').mkdir(exist_ok=True)
    unittest.main()
