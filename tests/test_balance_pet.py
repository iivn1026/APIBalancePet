import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from decimal import Decimal
import tempfile
import json
import urllib.error

p=Path(__file__).resolve().parents[1]/'balance_pet.py'
s=importlib.util.spec_from_file_location('pet',p)
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)

class Tests(unittest.TestCase):
    def test_paths(self):
        for u in ['https://example.com','https://example.com/v1/','https://example.com/v1/usage']:
            self.assertEqual(m.endpoint(u),'https://example.com/v1/usage')
        for u in ['http://site.test','https://key@site.test','https://site.test?key=x']:
            with self.assertRaises(ValueError):m.endpoint(u)
    def test_wallet_zero(self):
        r=m.parse_balance({'balance':0,'remaining':2,'unit':'USD'})
        self.assertEqual(r[0],'钱包余额'); self.assertEqual(r[2],Decimal('0'))
    def test_key(self):
        r=m.parse_balance({'mode':'quota_limited','remaining':12.5,'status':'expired'})
        self.assertEqual(r[0],'Key 剩余额度');self.assertEqual(r[3],'Key 已过期')
    def test_subscription(self):
        r=m.parse_balance({'planName':'订阅','remaining':-1})
        self.assertEqual(r[1],'不限额');self.assertIsNone(r[2])
    def test_bad(self):
        for p in [{},{'balance':'NaN'},{'balance':True},{'balance':None},{'mode':'quota_limited','rate_limits':[]},{'isValid':False,'balance':10}]:
            with self.assertRaises(ValueError):m.parse_balance(p)
    def test_dpapi_storage(self):
        with tempfile.TemporaryDirectory() as d, patch.object(m,'CONFIG',Path(d)/'settings.json'):
            c=dict(m.DEFAULT,key='test-only-secret')
            m.save_config(c)
            self.assertNotIn(c['key'],m.CONFIG.read_text())
            self.assertEqual(m.load_config(),c)
    def test_network_contract(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{"balance": 12.5, "unit":"USD"}'
        with patch.object(m.urllib.request,'build_opener') as b:
            b.return_value.open.return_value=Response()
            self.assertEqual(m.fetch(dict(m.DEFAULT,url='https://example.com',key='dummy'))[2],Decimal('12.5'))
            req=b.return_value.open.call_args.args[0]
            self.assertEqual(req.get_method(),'GET')
            self.assertEqual(req.get_header('Authorization'),'Bearer dummy')
    def test_auth_failure(self):
        with patch.object(m.urllib.request,'build_opener') as b:
            b.return_value.open.side_effect=urllib.error.HTTPError('https://example.test',401,'secret',{},None)
            with self.assertRaisesRegex(ValueError,'API Key 无效'):m.fetch(dict(m.DEFAULT,url='https://example.com',key='dummy'))
    def test_redirect_denied(self):
        self.assertIsNone(m.NoRedirect().redirect_request(None,None,302,'',{},'https://other.test'))

if __name__=='__main__':unittest.main()
