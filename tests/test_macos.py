import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import balance_pet as pet
from platform_support import MACOS
from thought_bubble import cloud_image


@unittest.skipUnless(MACOS, 'macOS only')
class MacTests(unittest.TestCase):
    def test_keychain_storage_and_clear(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(pet, 'CONFIG', Path(folder) / 'settings.json'), \
                patch('keyring.backends.macOS.Keyring') as backend:
            vault = backend.return_value
            cfg = dict(pet.DEFAULT, key='test-only-secret')
            pet.save_config(cfg)
            saved = json.loads(pet.CONFIG.read_text())
            self.assertNotIn(cfg['key'], pet.CONFIG.read_text())
            vault.set_password.assert_called_once_with('APIBalancePet', saved['keychain_account'], cfg['key'])
            vault.get_password.return_value = cfg['key']
            self.assertEqual(pet.load_config(), cfg)
            pet.save_config(dict(cfg, key=''))
            vault.delete_password.assert_called_once_with('APIBalancePet', saved['keychain_account'])
            self.assertNotIn('keychain_account', json.loads(pet.CONFIG.read_text()))

    def test_locked_keychain_loads_without_secret(self):
        from keyring.errors import KeyringError
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(pet, 'CONFIG', Path(folder) / 'settings.json'), \
                patch('keyring.backends.macOS.Keyring') as backend:
            pet.CONFIG.write_text(json.dumps(dict(keychain_account='test')))
            backend.return_value.get_password.side_effect = KeyringError('locked')
            self.assertEqual(pet.load_config()['key'], '')

    def test_cloud_has_transparent_corners(self):
        for mode in ('above', 'below', 'left', 'right'):
            image, _ = cloud_image(380, mode, 210)
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertEqual(image.getchannel('A').getextrema(), (0, 255))
