import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import mac_accounts as store


class Vault:
    def __init__(self): self.values = {}
    def get_password(self, service, account): return self.values.get(account)
    def set_password(self, *args): raise AssertionError('Must not write to Keychain')
    def delete_password(self, *args): raise AssertionError('Must not delete from Keychain')


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'settings.json'
        self.vault = Vault()
        self.data = dict(store.PREFERENCES, accounts=[
            store.account('工作', url='https://work.example.com', key='secret-work'),
            store.account('个人', url='https://personal.example.com', key='secret-personal')])

    def test_local_roundtrip_permissions_and_removal(self):
        store.save(self.data, self.path, self.vault)
        raw = json.loads(self.path.read_text())
        self.assertEqual(raw['version'], 3)
        self.assertEqual(raw['accounts'][0]['key'], 'secret-work')
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        recovered = store.load(self.path, self.vault)
        self.assertEqual([x['key'] for x in recovered['accounts']], ['secret-work', 'secret-personal'])
        recovered['accounts'].pop(0)
        store.save(recovered, self.path, self.vault)
        self.assertEqual(len(store.load(self.path)['accounts']), 1)

    def test_migrate_single_connection_automatically(self):
        self.path.write_text(json.dumps(dict(url='https://old.example.com', keychain_account='old', interval=600)))
        self.vault.values['old'] = 'old-key'
        data = store.load(self.path, self.vault)
        self.assertEqual(data['accounts'][0]['key'], 'old-key')
        self.assertEqual(data['interval'], 600)
        raw = json.loads(self.path.read_text())
        self.assertEqual(raw['version'], 3)
        self.assertNotIn('keychain_account', raw['accounts'][0])
        self.assertEqual(self.vault.values['old'], 'old-key')

    def test_migrate_multiple_connections_without_swapping_keys(self):
        rows = [dict(a, keychain_account='ref-'+str(i)) for i,a in enumerate(self.data['accounts'])]
        for i,row in enumerate(rows):
            self.vault.values[row['keychain_account']] = row.pop('key')
        self.path.write_text(json.dumps(dict(self.data, version=2, accounts=rows)))
        data = store.load(self.path, self.vault)
        self.assertEqual([a['key'] for a in data['accounts']], ['secret-work','secret-personal'])
        with patch.object(self.vault, 'get_password', side_effect=AssertionError('No Keychain reads')):
            self.assertEqual(store.load(self.path,self.vault)['accounts'], data['accounts'])

    def test_failed_file_replace_preserves_config_and_cleans_temporary(self):
        store.save(self.data, self.path)
        before = self.path.read_bytes()
        self.data['accounts'][0]['key'] = 'replacement'
        with patch.object(Path, 'replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError): store.save(self.data, self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_unreadable_legacy_secret_preserved_then_retried(self):
        row = dict(self.data['accounts'][0], keychain_account='legacy')
        row.pop('key')
        self.path.write_text(json.dumps(dict(self.data, version=2, accounts=[row])))
        with patch.object(self.vault,'get_password',side_effect=OSError('locked')):
            data=store.load(self.path,self.vault)
        self.assertIsNone(data['accounts'][0]['key'])
        store.save(data,self.path)
        self.assertEqual(json.loads(self.path.read_text())['accounts'][0]['keychain_account'],'legacy')
        self.vault.values['legacy']='recovered'
        self.assertEqual(store.load(self.path,self.vault)['accounts'][0]['key'],'recovered')

    def test_validation(self):
        self.data['accounts'][0]['url']='http://example.com'
        with self.assertRaises(ValueError): store.save(self.data,self.path)
        self.assertFalse(self.path.exists())

    def test_selection_preserves_local_secrets(self):
        store.save(self.data,self.path)
        identifier=self.data['accounts'][1]['id']
        store.save_selection(identifier,self.path)
        data=store.load(self.path)
        self.assertEqual(data['menubar_account'],identifier)
        self.assertEqual([a['key'] for a in data['accounts']],['secret-work','secret-personal'])
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode),0o600)
