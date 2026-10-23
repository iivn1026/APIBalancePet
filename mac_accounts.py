"""Local multi-account settings with one-time migration of legacy Keychain keys."""
import json
import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit
import balance_pet as core

SERVICE = 'APIBalancePet'
PREFERENCES = dict(interval=300, usage_enabled=True, usage_period='24h', menubar_account='')


def account(name='', **values):
    item = dict(id=uuid.uuid4().hex, name=name, url='', api_path='/v1/usage', key='',
                threshold='5', enabled=True)
    item.update(values)
    return item


def validate(data):
    if not 60 <= int(data['interval']) <= 86400:
        raise ValueError('刷新间隔需为 60～86400 秒。')
    if data['usage_period'] not in ('24h', '7d', '30d'):
        raise ValueError('请选择有效的用量时间范围。')
    ids = set()
    for item in data['accounts']:
        if not item['id'] or item['id'] in ids:
            raise ValueError('账户标识重复。')
        ids.add(item['id'])
        if not item['name'].strip():
            raise ValueError('请为每个连接填写名称。')
        core.endpoint(item['url'], item['api_path'])
        if item['key'] is not None and any(c.isspace() for c in item['key']):
            raise ValueError('API Key 不能含空格或换行。')
        if core.number(item['threshold']) < 0:
            raise ValueError('低余额阈值不能小于 0。')


def _write(saved, path):
    """Create the temporary file privately before writing any credentials."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(saved, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
    except OSError as error:
        raise OSError('保存失败，原有配置已保留。请检查配置文件权限。') from error
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def load(path=None, vault=None):
    path = path or core.CONFIG
    data = dict(PREFERENCES, accounts=[])
    try:
        saved = json.loads(path.read_text('utf-8'))
        if not isinstance(saved, dict): raise ValueError('Invalid settings')
    except FileNotFoundError:
        return data
    except (OSError, ValueError) as error:
        raise OSError('无法读取配置文件，请先备份并检查 settings.json。') from error
    for key in PREFERENCES:
        data[key] = saved.get(key, PREFERENCES[key])
    if saved.get('version') in (2, 3):
        items = saved.get('accounts', [])
    else:
        items = []
        if saved.get('url') or saved.get('keychain_account'):
            item = account(urlsplit(saved.get('url', '')).hostname or '原有连接')
            item.pop('key')
            item.update({k: saved[k] for k in ('url', 'api_path', 'threshold', 'keychain_account', 'key') if k in saved})
            if 'api_path' not in saved:
                old_path = urlsplit(saved.get('url', '')).path.rstrip('/')
                if old_path.endswith('/usage'): item['api_path'] = old_path
            items.append(item)
    migrated = False
    for raw in items:
        item = account()
        item.update({k: raw[k] for k in ('id', 'name', 'url', 'api_path', 'threshold', 'enabled') if k in raw})
        if 'key' in raw and isinstance(raw['key'], str):
            item['key'] = raw['key']
        elif raw.get('keychain_account'):
            item['keychain_account'] = raw['keychain_account']
            item['key'] = None
            try:
                if vault is None:
                    from keyring.backends.macOS import Keyring
                    vault = Keyring()
                item['key'] = vault.get_password(SERVICE, item['keychain_account'])
                if item['key'] is not None:
                    item.pop('keychain_account')
                    migrated = True
            except Exception:
                pass
            if item['key'] is None:
                item['key_error'] = '旧密钥未能迁移，请重新填写 API Key。'
        data['accounts'].append(item)
    if migrated or saved.get('version') != 3:
        save(data, path)
    return data


def save(data, path=None, vault=None):
    """Save local keys atomically; never write to or delete from Keychain."""
    path = path or core.CONFIG
    validate(data)
    rows = []
    for item in data['accounts']:
        row = {k: item[k] for k in ('id', 'name', 'url', 'api_path', 'threshold', 'enabled')}
        if item['key'] is None:
            # Preserve an unreadable legacy reference so migration can be retried.
            if item.get('keychain_account'): row['keychain_account'] = item['keychain_account']
        else:
            row['key'] = item['key']
        rows.append(row)
    _write(dict(version=3, accounts=rows, **{key: data[key] for key in PREFERENCES}), path)
    for item in data['accounts']:
        if item['key'] is not None:
            item.pop('keychain_account', None)
            item.pop('key_error', None)


def save_selection(identifier, path=None):
    path = path or core.CONFIG
    if not path.exists(): return
    data = json.loads(path.read_text('utf-8'))
    if data.get('version') not in (2, 3): return
    data['menubar_account'] = identifier
    _write(data, path)
