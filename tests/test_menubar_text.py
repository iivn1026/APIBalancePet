import sys
import unittest
from decimal import Decimal


@unittest.skipUnless(sys.platform == 'darwin', 'macOS menu bar')
class MenuBarTextTests(unittest.TestCase):
    def test_amount_formatting(self):
        from mac_pet import balance_title
        self.assertEqual(balance_title(None), '—')
        for value, expected in [('128.4500', '128.45 USD'), ('0', '0.00 USD'), ('0.0012', '0.0012 USD'), ('10000.12', '10,000.12 USD')]:
            self.assertEqual(balance_title(('钱包余额', value+' USD', Decimal(value), '', None)), expected)
        self.assertEqual(balance_title(('订阅剩余额度', '不限额', None, '', None)), '不限额')
