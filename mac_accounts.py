"""Versioned multi-account settings; secrets live only in macOS Keychain."""
import json
import uuid
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


def load(path=None, vault=None):
    from keyring.backends.macOS import Keyring
    from keyring.errors import KeyringError
    path = path or core.CONFIG
    data = dict(PREFERENCES, accounts=[])
    try:
        saved = json.loads(path.read_text('utf-8'))
        if not isinstance(saved, dict):
            raise ValueError('Invalid settings')
    except FileNotFoundError:
        return data
    except (OSError, ValueError) as error:
        raise OSError('无法读取配置文件，请先备份并检查 settings.json。') from error
    for key in PREFERENCES:
        data[key] = saved.get(key, PREFERENCES[key])
    if saved.get('version') == 2:
        items = saved.get('accounts', [])
    else:
        items = []
        if saved.get('url') or saved.get('keychain_account'):
            item = account(urlsplit(saved.get('url', '')).hostname or '原有连接')
            item.update({k: saved[k] for k in ('url', 'api_path', 'threshold', 'keychain_account') if k in saved})
            if 'api_path' not in saved:
                old_path = urlsplit(saved.get('url', '')).path.rstrip('/')
                if old_path.endswith('/usage'): item['api_path'] = old_path
            items.append(item)
    vault = vault or Keyring()
    for raw in items:
        item = account()
        item.update({k: raw[k] for k in ('id', 'name', 'url', 'api_path', 'threshold', 'enabled', 'keychain_account') if k in raw})
        if item.get('keychain_account'):
            try:
                item['key'] = vault.get_password(SERVICE, item['keychain_account'])
                if item['key'] is None:
                    item['key_error'] = '钥匙串中未找到密钥，请重新填写。'
            except KeyringError:
                item['key'] = None
                item['key_error'] = '钥匙串暂不可用，解锁后重试。'
        data['accounts'].append(item)
    return data


def save(data, path=None, vault=None):
    """Write new secret references, atomically commit JSON, then retire old refs."""
    from keyring.backends.macOS import Keyring
    path = path or core.CONFIG
    validate(data)
    vault = vault or Keyring()
    previous = {}
    if path.exists():
        previous = json.loads(path.read_text('utf-8'))
    old_refs = {row['keychain_account'] for row in previous.get('accounts', []) if row.get('keychain_account')}
    if previous.get('keychain_account'):
        old_refs.add(previous['keychain_account'])
    written = []
    rows = []
    references = {}
    try:
        for item in data['accounts']:
            row = {k: item[k] for k in ('id', 'name', 'url', 'api_path', 'threshold', 'enabled')}
            if item['key'] is None:
                if item.get('keychain_account'):
                    row['keychain_account'] = item['keychain_account']
            elif item['key']:
                reference = 'account-' + uuid.uuid4().hex
                vault.set_password(SERVICE, reference, item['key'])
                written.append(reference)
                row['keychain_account'] = reference
            references[item['id']] = row.get('keychain_account')
            rows.append(row)
        saved = dict(version=2, accounts=rows, **{key: data[key] for key in PREFERENCES})
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2), 'utf-8')
        temporary.chmod(0o600)
        temporary.replace(path)
    except Exception as error:
        for reference in written:
            try: vault.delete_password(SERVICE, reference)
            except Exception: pass
        raise OSError('保存失败，原有配置已保留。请检查钥匙串及文件权限。') from error
    active_refs = {row['keychain_account'] for row in rows if row.get('keychain_account')}
    for reference in old_refs-active_refs:
        try: vault.delete_password(SERVICE, reference)
        except Exception: pass
    for item in data['accounts']:
        item.pop('keychain_account', None)
        if references[item['id']]: item['keychain_account'] = references[item['id']]
        if item['key'] is not None: item.pop('key_error', None)


def save_selection(identifier, path=None):
    """Change the selected balance without rewriting any Keychain secrets."""
    path = path or core.CONFIG
    if not path.exists(): return
    data = json.loads(path.read_text('utf-8'))
    if data.get('version') != 2: return
    data['menubar_account'] = identifier
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)
