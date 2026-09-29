import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from urllib.parse import urlsplit, parse_qs
from PIL import Image
import json

source = Path(__file__).resolve().parents[1]/'balance_pet.py'
spec = importlib.util.spec_from_file_location('pet',source)
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class FeatureTests(unittest.TestCase):
    def test_custom_path_and_security(self):
        self.assertEqual(m.endpoint('https://example.com/v1','/api/balance'),'https://example.com/api/balance')
        self.assertEqual(m.endpoint('https://example.com',''),'https://example.com/v1/usage')
        for path in ['https://evil.test','//evil.test/a','/', '/foo?key=secret','/foo#x','/a b']:
            with self.assertRaises(ValueError):m.endpoint('https://example.com',path)

    def test_real_date_ranges(self):
        now = datetime(2026,9,30,15,0,tzinfo=timezone(timedelta(hours=8)))
        for period,start,days in [('24h','2026-09-30',1),('7d','2026-09-24',7),('30d','2026-09-01',30)]:
            win=m.usage_window(dict(m.DEFAULT,usage_period=period),now)
            self.assertEqual(win['params'],dict(start_date=start,end_date='2026-09-30',days=days))
        self.assertIn('非滚动24小时',m.usage_window(m.DEFAULT,now)['note'])

    def test_actual_cost_never_uses_list_price(self):
        payload={'model_stats':[{'model':'a','total_tokens':1234,'actual_cost':'0.001235','cost':100},
                                {'model':'b','total_tokens':0,'actual_cost':0},
                                {'model':'c','cost':9876},
                                {'model':'d','total_tokens':'NaN','actual_cost':True}]}
        report=m.summarize_usage(payload,m.usage_window(m.DEFAULT))
        self.assertEqual(report['rows'][0]['actual_cost'],Decimal('0.001235'))
        self.assertIn('1,234',m.usage_row_text(report['rows'][0]))
        self.assertIn('0.000000 USD',m.usage_row_text(report['rows'][1]))
        self.assertIsNone(report['rows'][2]['actual_cost'])
        self.assertIn('实际花费 未提供',m.usage_row_text(report['rows'][2]))
        self.assertIsNone(report['rows'][3]['tokens'])

    def test_no_lifetime_totals_mislabeled_recent(self):
        report=m.summarize_usage({'usage':{'total':{'actual_cost':999,'total_tokens':123}}},m.usage_window(m.DEFAULT))
        self.assertEqual(report['rows'],[])
        self.assertEqual(report['message'],'接口未提供模型明细')
        many=m.summarize_usage({'model_stats':[dict(model=f'm{i}',total_tokens=i,actual_cost=i/100) for i in range(32)]},m.usage_window(m.DEFAULT))
        self.assertEqual(len(many['rows']),32)

    def test_request_range_and_disable(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self,n):return b'{"balance": 10, "model_stats":[{"model":"a","total_tokens":10,"actual_cost":0.1}]}'
        with patch.object(m.urllib.request,'build_opener') as opener:
            opener.return_value.open.return_value=Response()
            result=m.fetch(dict(m.DEFAULT,url='https://example.com',key='dummy',usage_period='7d',api_path='/api/balance'))
            req=opener.return_value.open.call_args.args[0]
            parsed=urlsplit(req.full_url)
            self.assertEqual(parsed.path,'/api/balance')
            self.assertIn('start_date',parse_qs(parsed.query))
            self.assertEqual(parse_qs(parsed.query)['days'],['7'])
            self.assertEqual(result[4]['rows'][0]['model'],'a')
            result=m.fetch(dict(m.DEFAULT,url='https://example.com',key='dummy',usage_enabled=False))
            req=opener.return_value.open.call_args.args[0]
            self.assertEqual(urlsplit(req.full_url).query,'')
            self.assertIsNone(result[4])

    def test_import_copies_alpha_image(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'CONFIG',Path(folder)/'settings.json'):
            original=Path(folder)/'source.png'
            image=Image.new('RGBA',(100,150),(0,100,200,0));image.putpixel((50,75),(20,40,50,255));image.save(original)
            imported=m.store_avatar(m.read_avatar(original));original.unlink()
            recovered=m.read_avatar(imported)
            self.assertEqual(recovered.getpixel((0,0))[3],0)
            self.assertEqual(recovered.getpixel((50,75))[3],255)
            broken=Path(folder)/'broken.png';broken.write_text('invalid')
            with self.assertRaises(ValueError):m.read_avatar(broken)

    def test_old_config_migration(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'CONFIG',Path(folder)/'settings.json'):
            m.CONFIG.write_text(json.dumps(dict(url='https://example.com/proxy/v1/usage',encrypted_key='')))
            c=m.load_config()
            self.assertEqual(c['api_path'],'/proxy/v1/usage')
            self.assertEqual(c['pet_size'],100)
            self.assertEqual(c['usage_period'],'24h')

if __name__=='__main__':unittest.main()
