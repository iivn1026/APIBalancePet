import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mac_accounts as store


class Vault:
    def __init__(self): self.values = {}
    def get_password(self, service, account): return self.values.get(account)
    def set_password(self, service, account, value): self.values[account] = value
    def delete_password(self, service, account): self.values.pop(account, None)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'settings.json'
        self.vault = Vault()
        self.data = dict(store.PREFERENCES, accounts=[
            store.account('工作', url='https://work.example.com', key='secret-work'),
            store.account('个人', url='https://personal.example.com', key='secret-personal')])

    def test_isolated_secret_roundtrip_and_removal(self):
        store.save(self.data, self.path, self.vault)
        raw = self.path.read_text()
        self.assertNotIn('secret-work', raw)
        self.assertNotIn('secret-personal', raw)
        recovered = store.load(self.path, self.vault)
        self.assertEqual([x['key'] for x in recovered['accounts']], ['secret-work', 'secret-personal'])
        old = recovered['accounts'][0]['keychain_account']
        recovered['accounts'].pop(0)
        store.save(recovered, self.path, self.vault)
        self.assertNotIn(old, self.vault.values)
        self.assertEqual(len(self.vault.values), 1)

    def test_migrate_single_connection_without_writing(self):
        self.path.write_text(json.dumps(dict(url='https://old.example.com', keychain_account='old', interval=600)))
        self.vault.values['old'] = 'old-key'
        before = self.path.read_bytes()
        data = store.load(self.path, self.vault)
        self.assertEqual(data['accounts'][0]['key'], 'old-key')
        self.assertEqual(data['interval'], 600)
        self.assertEqual(self.path.read_bytes(), before)
        store.save(data, self.path, self.vault)
        self.assertNotIn('old', self.vault.values)
        self.assertEqual(store.load(self.path, self.vault)['accounts'][0]['key'], 'old-key')

    def test_failed_keychain_write_preserves_old_config(self):
        store.save(self.data, self.path, self.vault)
        before = self.path.read_bytes()
        old = copy.deepcopy(self.vault.values)
        original = self.vault.set_password
        count = [0]
        def fail_second(*args):
            count[0] += 1
            if count[0] == 2: raise OSError('locked')
            return original(*args)
        with patch.object(self.vault, 'set_password', side_effect=fail_second):
            with self.assertRaises(OSError): store.save(self.data, self.path, self.vault)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(old, self.vault.values)

    def test_failed_file_replace_rolls_back_new_secrets(self):
        store.save(self.data, self.path, self.vault)
        before, old = self.path.read_bytes(), copy.deepcopy(self.vault.values)
        with patch.object(Path, 'replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError): store.save(self.data, self.path, self.vault)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(old, self.vault.values)

    def test_unreadable_secret_reference_is_preserved(self):
        from keyring.errors import KeyringError
        store.save(self.data, self.path, self.vault)
        with patch.object(self.vault, 'get_password', side_effect=KeyringError('locked')):
            data = store.load(self.path, self.vault)
        self.assertIsNone(data['accounts'][0]['key'])
        references = {row['keychain_account'] for row in data['accounts']}
        store.save(data, self.path, self.vault)
        self.assertEqual(references, set(self.vault.values))

    def test_validation(self):
        self.data['accounts'][0]['url'] = 'http://example.com'
        with self.assertRaises(ValueError): store.save(self.data, self.path, self.vault)
        self.assertFalse(self.vault.values)

    def test_selection_does_not_rewrite_secrets(self):
        store.save(self.data, self.path, self.vault)
        before = dict(self.vault.values)
        identifier = self.data['accounts'][1]['id']
        store.save_selection(identifier, self.path)
        self.assertEqual(self.vault.values, before)
        self.assertEqual(store.load(self.path, self.vault)['menubar_account'], identifier)
