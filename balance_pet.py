"""Windows balance desktop pet. Network access is limited to user-configured GET requests."""
import base64
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import urllib.request
import urllib.error
from urllib.parse import urlsplit, urlunsplit
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import uuid
from PIL import Image, ImageTk, ImageOps, UnidentifiedImageError
from thought_bubble import ThoughtBubble

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
CONFIG = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'APIBalancePet' / 'settings.json'
DEFAULT = dict(url='', api_path='/v1/usage', key='', interval=300, threshold='5', topmost=True,
               image_path='', pet_size=100, usage_enabled=True, usage_period='24h')
PERIODS = {'近24小时': '24h', '近7天': '7d', '近30天': '30d'}


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, decrypt=False):
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dest = Blob()
    dll = ctypes.WinDLL('crypt32', use_last_error=True)
    fun = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    fun.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fun.restype = wintypes.BOOL
    if not fun(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
        raise OSError('Windows 密钥加密失败，请重新填写 Key。')
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        free = ctypes.WinDLL('kernel32').LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(dest.data)


def load_config():
    cfg = DEFAULT.copy()
    try:
        saved = json.loads(CONFIG.read_text('utf-8'))
        cfg.update({k: saved[k] for k in DEFAULT if k != 'key' and k in saved})
        if 'api_path' not in saved:
            old_path = urlsplit(cfg['url']).path.rstrip('/')
            if old_path.endswith('/usage'): cfg['api_path'] = old_path
        cfg['key'] = crypt(base64.b64decode(saved['encrypted_key']), True).decode() if saved.get('encrypted_key') else ''
    except (OSError, ValueError, KeyError):
        cfg['key'] = ''
    return cfg


def save_config(cfg):
    saved = {k: v for k, v in cfg.items() if k != 'key'}
    saved['encrypted_key'] = base64.b64encode(crypt(cfg['key'].encode())).decode() if cfg['key'] else ''
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG.with_suffix('.tmp')
    temp.write_text(json.dumps(saved, ensure_ascii=False, indent=2), 'utf-8')
    temp.replace(CONFIG)


def endpoint(address, api_path='/v1/usage'):
    u = urlsplit(address.strip())
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError('请输入 HTTPS 地址，不要包含账号、查询参数或 #。')
    path = api_path.strip() or '/v1/usage'
    if not path.startswith('/') or path.startswith('//') or '?' in path or '#' in path or chr(92) in path or any(c.isspace() for c in path):
        raise ValueError('接口路径需以 / 开头，不能含查询参数、空格或 #。')
    if path == '/': raise ValueError('请填写完整接口路径，例如 /v1/usage。')

    return urlunsplit((u.scheme, u.netloc, path.rstrip('/'), '', ''))


def number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('余额字段不是有效数字。')
    try:
        n = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('余额字段不是有效数字。')
    if not n.is_finite():
        raise ValueError('余额字段不是有效数字。')
    return n


def parse_balance(payload):
    if not isinstance(payload, dict):
        raise ValueError('接口返回格式不支持。')
    d = payload.get('data', payload)
    if not isinstance(d, dict) or d.get('isValid') is False:
        raise ValueError('Key 无效或接口返回格式不支持。')
    if 'balance' in d:
        label, value = '钱包余额', d['balance']
    elif d.get('mode') == 'quota_limited':
        label = 'Key 剩余额度'
        value = d.get('remaining', (d.get('quota') or {}).get('remaining'))
        if value is None:
            raise ValueError('此 Key 仅返回周期限额，未提供钱包余额。')
    elif 'remaining' in d:
        label, value = ('订阅剩余额度' if d.get('subscription') or d.get('planName') not in (None, '钱包余额') else '剩余额度'), d['remaining']
    else:
        raise ValueError('接口没有余额字段，请检查 Key 的分组或站点接口。')
    n = number(value)
    unlimited = n == -1 and label == '订阅剩余额度'
    unit = str(d.get('unit', 'USD'))[:12]
    display = '不限额' if unlimited else f'{n:,.4f} {unit}'
    status = d.get('status', '')
    detail = {'expired': 'Key 已过期', 'quota_exhausted': 'Key 额度已用完', 'disabled': 'Key 已停用'}.get(status, '')
    return label, display, None if unlimited else n, detail


def usage_window(cfg, now=None):
    # The server parses dates only, not timestamps: expose the actual granularity.
    zone = datetime.now().astimezone().tzinfo
    now = now or datetime.now(zone)
    days = {'24h': 1, '7d': 7, '30d': 30}.get(cfg.get('usage_period'), 1)
    today = now.astimezone(zone).date()
    start = today - timedelta(days=days-1)
    return {
        'params': {'start_date': start.isoformat(), 'end_date': today.isoformat(), 'days': days},
        'title': '近24小时 · 接口仅支持自然日' if days == 1 else f'近{days}个自然日（含今天）',
        'range': f'实际统计：{start.isoformat()} ～ {today.isoformat()}',
        'note': '仅展示今日汇总，非滚动24小时' if days == 1 else '按站点日界汇总，非逐笔请求记录',
    }


def optional_number(value):
    try: return number(value)
    except ValueError: return None


def summarize_usage(payload, window):
    d = payload.get('data', payload)
    report = dict(window, rows=[], message='接口未提供模型明细')
    stats = d.get('model_stats') if isinstance(d, dict) else None
    if not isinstance(stats, list): return report
    for row in stats:
        if not isinstance(row, dict): continue
        model = row.get('model') or row.get('model_name')
        if not isinstance(model, str) or not model.strip(): continue
        model = ' '.join(model.split())[:100]
        tokens = optional_number(row.get('total_tokens'))
        if tokens is not None and (tokens < 0 or tokens != tokens.to_integral_value()): tokens = None
        # Never substitute list price (cost/total_cost) for the actual billed cost.
        cost = optional_number(row.get('actual_cost'))
        report['rows'].append({'model': model, 'tokens': tokens, 'actual_cost': cost})
    report['message'] = '该时间范围无模型记录' if not stats else '模型字段不完整'
    return report


def usage_row_text(row):
    tokens = f"{int(row['tokens']):,}" if row['tokens'] is not None else '未提供'
    cost = f"{row['actual_cost']:,.6f} USD" if row['actual_cost'] is not None else '未提供'
    return f"{row['model']}  |  Tokens {tokens}  |  实际花费 {cost}"


def read_avatar(path):
    try:
        with Image.open(path) as source:
            if source.width * source.height > 25_000_000:
                raise ValueError('图片过大，请选择不超过 2500 万像素的图片。')
            return ImageOps.exif_transpose(source).convert('RGBA')
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ValueError('无法读取图片，请选择有效的 PNG、JPG 或 WebP 图片。') from None


def store_avatar(image):
    # Copy into local app data; deleting the original will not break the pet.
    folder = CONFIG.parent / 'images'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid.uuid4().hex + '.png')
    image.save(path, format='PNG')
    return str(path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(cfg):
    path = endpoint(cfg['url'], cfg.get('api_path', '/v1/usage'))
    window = None
    if cfg.get('usage_enabled', True):
        window = usage_window(cfg)
        path += '?' + urlencode(window['params'])
    req = urllib.request.Request(path, headers={
        'Authorization': 'Bearer ' + cfg['key'], 'Accept': 'application/json', 'User-Agent': 'APIBalancePet/1.0'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('接口响应过大。')
        payload = json.loads(raw)
        balance = parse_balance(payload)
        report = summarize_usage(payload, window) if window else None
        return (*balance, report)
    except urllib.error.HTTPError as e:
        reasons = {401: 'API Key 无效，请检查设置。', 403: '此 Key 没有查询权限。',
                   404: '没有找到余额接口，请检查地址。', 429: '查询太频繁，请稍后再试。'}
        raise ValueError(reasons.get(e.code, f'查询失败（HTTP {e.code}），请稍后再试。')) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('网络连接失败，请检查网络或请求地址。') from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('站点返回的不是 JSON 余额数据。') from None


class Pet:
    def __init__(self, preview=False):
        self.preview = preview
        self.cfg = DEFAULT.copy() if preview else load_config()
        self.root = tk.Tk()
        self.root.tk.call('tk', 'scaling', 96 / 72)
        self.root.option_add('*Font', '{Microsoft YaHei UI} 10')
        self.root.title('APIBalancePet')
        self.root.overrideredirect(True)
        self.root.configure(bg='#ff00ff')
        self.root.wm_attributes('-transparentcolor', '#ff00ff')
        self.root.wm_attributes('-topmost', bool(self.cfg['topmost']))
        self.width, self.height = 186, 338
        self.root.geometry(f'{self.width}x{self.height}+{max(0,self.root.winfo_screenwidth()-240)}+{max(0,self.root.winfo_screenheight()-430)}')
        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height, bg='#ff00ff', highlightthickness=0, bd=0)
        self.canvas.pack()
        self.root.update_idletasks()
        self.pic = self.canvas.create_image(self.width//2, self.height//2)
        self.appearance_warning = ''
        try: initial_image = read_avatar(self.cfg.get('image_path') or ROOT / 'avatar.png')
        except ValueError:
            initial_image = read_avatar(ROOT / 'avatar.png')
            self.appearance_warning = '自定义图片不可用，已恢复默认角色。'
        self.apply_avatar(initial_image, self.cfg.get('pet_size', 100))
        self.balance_state = dict(label='等待设置 API Key',amount='尚未查询',status='右键角色可打开设置',color='#4A3E68')
        self.usage_report = None
        self.bubble = ThoughtBubble(self)
        self.canvas.bind('<ButtonPress-1>', self.drag_start)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.left_release)
        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label='刷新余额', command=self.refresh)
        self.menu.add_command(label='设置', command=self.settings)
        self.menu.add_separator()
        self.menu.add_command(label='退出', command=self.root.destroy)
        self.canvas.bind('<Button-3>', self.right_click)
        self.results = queue.Queue()
        self.busy = False
        self.generation = 0
        self.next_query = time.monotonic() + 1
        self.dialog = None
        self.frame = 0
        self.root.after(80,self.tick)
        if preview:
            self.show_result(('演示余额（模拟数据）','12.3400 USD',Decimal('12.34'),'', summarize_usage({'model_stats': [{'model':'演示模型（非真实数据）','total_tokens':1024,'actual_cost':'0.001'}]}, usage_window(self.cfg))))

    def apply_avatar(self, image, size):
        scale = max(30, min(200, int(float(size)))) / 100
        factor = min(180*scale/image.width, 326*scale/image.height)
        rendered = image.resize((max(1,round(image.width*factor)),max(1,round(image.height*factor))),Image.Resampling.LANCZOS)
        rendered.putalpha(rendered.getchannel('A').point(lambda alpha:255 if alpha>=128 else 0))
        self.avatar = ImageTk.PhotoImage(rendered)
        old_width, old_height = self.width, self.height
        self.width, self.height = rendered.width+12, rendered.height+12
        self.canvas.configure(width=self.width,height=self.height)
        self.canvas.itemconfigure(self.pic,image=self.avatar)
        self.canvas.coords(self.pic,self.width//2,self.height//2)
        x = self.root.winfo_x() + (old_width-self.width)//2
        y = self.root.winfo_y() + old_height-self.height
        x = min(max(0,x),max(0,self.root.winfo_screenwidth()-self.width))
        y = min(max(0,y),max(0,self.root.winfo_screenheight()-self.height))
        self.root.geometry(f'{self.width}x{self.height}+{x}+{y}')

    def show_usage(self, report=None):
        self.usage_report = report
        self.bubble.render()

    def update_balance(self, label=None, amount=None, status=None, color=None):
        for key,value in [('label',label),('amount',amount),('status',status),('color',color)]:
            if value is not None: self.balance_state[key] = value
        self.bubble.render()

    def drag_start(self,e):
        self.anchor = (e.x_root-self.root.winfo_x(), e.y_root-self.root.winfo_y())
        self.press = (e.x_root, e.y_root)
        self.dragged = False
        self.cloud_was_visible = self.bubble.visible

    def drag(self,e):
        if abs(e.x_root-self.press[0])+abs(e.y_root-self.press[1]) > 5:
            self.dragged = True
        if not self.dragged: return
        self.bubble.hide()
        x = min(max(0,e.x_root-self.anchor[0]),max(0,self.root.winfo_screenwidth()-self.width))
        y = min(max(0,e.y_root-self.anchor[1]),max(0,self.root.winfo_screenheight()-self.height))
        self.root.geometry(f'+{x}+{y}')

    def left_release(self,e):
        if self.dragged: return
        self.menu.unpost()
        if self.cloud_was_visible:
            self.bubble.hide()
            return
        if self.cfg['key']: self.refresh()
        self.bubble.show()

    def right_click(self,e):
        self.bubble.hide()
        try: self.menu.tk_popup(e.x_root,e.y_root)
        finally: self.menu.grab_release()

    def tick(self):
        self.bubble.poll()
        self.frame += 1
        self.canvas.coords(self.pic,self.width//2,self.height//2+math.sin(self.frame/9)*3)
        try:
            generation, result, error = self.results.get_nowait()
            self.busy = False
            if generation == self.generation:
                if error:
                    self.update_balance('本次查询失败', '暂不可用', error, '#ab5369')
                    self.show_usage()
                else: self.show_result(result)
        except queue.Empty: pass
        if not self.preview and self.cfg['key'] and time.monotonic() >= self.next_query and not self.busy:
            self.refresh()
        self.root.after(80,self.tick)

    def show_result(self,result):
        label, value, n, detail, usage = result
        low = n is not None and n <= number(self.cfg['threshold'])
        status = detail or ('更新于 '+time.strftime('%H:%M:%S'))
        self.update_balance(label+(' · 余额偏低' if low else ''), value, status, '#b34d68' if low else '#4a3e68')
        self.show_usage(usage)

    def refresh(self):
        if self.preview or self.busy: return
        if not self.cfg['key']:
            self.update_balance('等待设置 API Key','尚未查询','暂无模型用量数据')
            return
        self.busy = True
        self.next_query = time.monotonic()+int(self.cfg['interval'])
        self.update_balance(status='正在查询…',color='#4a3e68')
        cfg, generation = self.cfg.copy(), self.generation
        def worker():
            try: self.results.put((generation,fetch(cfg),None))
            except ValueError as e: self.results.put((generation,None,str(e)))
            except Exception: self.results.put((generation,None,'查询失败，请检查设置后重试。'))
        threading.Thread(target=worker,daemon=True).start()

    def settings(self):
        self.bubble.hide()
        if self.dialog and self.dialog.winfo_exists(): self.dialog.lift(); return
        d = self.dialog = tk.Toplevel(self.root)
        d.title('APIBalancePet · 设置')
        d.geometry('570x560')
        d.minsize(530,520)
        d.attributes('-topmost',True)
        outer = ttk.Frame(d,padding=18); outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='余额桌宠设置',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w',pady=(0,12))
        notebook = ttk.Notebook(outer); notebook.pack(fill='both',expand=True)
        connection = ttk.Frame(notebook,padding=16)
        appearance = ttk.Frame(notebook,padding=16)
        usage_tab = ttk.Frame(notebook,padding=16)
        for frame,title in [(connection,'接口连接'),(appearance,'图片与大小'),(usage_tab,'用量显示')]:
            notebook.add(frame,text=title)
        variables = {}
        fields = [('url','请求地址（HTTPS 站点地址）'),('api_path','余额接口路径'),('key','API Key（在本机加密保存）'),('interval','自动刷新间隔 / 秒（60～86400）'),('threshold','低余额提示阈值（接口货币单位）')]
        for name,title in fields:
            ttk.Label(connection,text=title).pack(anchor='w',pady=(6,3))
            value = variables[name] = tk.StringVar(value=str(self.cfg.get(name,DEFAULT[name])))
            ttk.Entry(connection,textvariable=value,show='●' if name=='key' else '').pack(fill='x')
            if name=='api_path':
                tk.Label(connection,text='  留空时默认使用 /v1/usage  ·  路径从站点根目录开始',bg='#ECEEF2',fg='#686E7B',anchor='w',pady=5).pack(fill='x',pady=(4,0))
        ttk.Label(appearance,text='选择桌宠图片',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w')
        ttk.Label(appearance,text='图片只导入本机，支持 PNG / JPG / WebP。\n透明 PNG / WebP 可保留透明背景；动图使用第一帧。',wraplength=470).pack(anchor='w',pady=(6,12))
        chosen = {'path': self.cfg.get('image_path',''), 'new': False}
        try: original = read_avatar(chosen['path'] or ROOT/'avatar.png')
        except ValueError:
            original = read_avatar(ROOT/'avatar.png')
            chosen['path'] = ''
        draft_image = {'value':original}
        image_name = tk.StringVar(value=Path(chosen['path']).name if chosen['path'] else '内置角色图片')
        row = ttk.Frame(appearance);row.pack(fill='x')
        size = tk.DoubleVar(value=float(self.cfg.get('pet_size',100)))
        size_text = tk.StringVar(value=f'{int(size.get())}%')
        def preview_size(*_):
            size_text.set(f'{round(size.get())}%')
            self.apply_avatar(draft_image['value'],round(size.get()))
        def choose_image():
            path = filedialog.askopenfilename(parent=d,title='选择桌宠图片',filetypes=[('图片','*.png *.jpg *.jpeg *.webp'),('所有文件','*.*')])
            if not path: return
            try: image = read_avatar(path)
            except ValueError as e: messagebox.showerror('无法导入',str(e),parent=d);return
            chosen.update(path=path,new=True)
            draft_image['value'] = image
            image_name.set(Path(path).name)
            preview_size()
        def reset_image():
            chosen.update(path='',new=False)
            draft_image['value'] = read_avatar(ROOT/'avatar.png')
            image_name.set('内置角色图片');preview_size()
        ttk.Button(row,text='导入图片…',command=choose_image).pack(side='left')
        ttk.Button(row,text='恢复默认图片',command=reset_image).pack(side='left',padx=10)
        ttk.Label(appearance,textvariable=image_name,wraplength=460).pack(anchor='w',pady=(8,18))
        ttk.Label(appearance,text='桌宠大小（实时预览）',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w')
        ttk.Scale(appearance,from_=30,to=200,variable=size,orient='horizontal').pack(fill='x',pady=(10,5))
        ttk.Label(appearance,textvariable=size_text).pack(anchor='w')
        ttk.Label(appearance,text='30%                                      100%                                      200%').pack(anchor='w')
        size.trace_add('write',preview_size)
        top = tk.BooleanVar(value=self.cfg['topmost'])
        ttk.Checkbutton(appearance,text='始终置顶',variable=top).pack(anchor='w',pady=18)
        if self.appearance_warning:
            ttk.Label(appearance,text=self.appearance_warning,foreground='#A24957',wraplength=460).pack(anchor='w')
        usage = tk.BooleanVar(value=bool(self.cfg.get('usage_enabled',True)))
        ttk.Label(usage_tab,text='左键菜单用量明细',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w')
        ttk.Checkbutton(usage_tab,text='显示模型名称、Token 数与实际花费',variable=usage).pack(anchor='w',pady=14)
        ttk.Label(usage_tab,text='统计范围').pack(anchor='w',pady=(6,5))
        current_period = next((k for k,v in PERIODS.items() if v==self.cfg.get('usage_period')),'近24小时')
        period = tk.StringVar(value=current_period)
        picker = ttk.Combobox(usage_tab,textvariable=period,values=list(PERIODS),state='readonly',width=20)
        picker.pack(anchor='w')
        def set_usage_state(*_): picker.configure(state='readonly' if usage.get() else 'disabled')
        usage.trace_add('write',set_usage_state);set_usage_state()
        tk.Label(usage_tab,text='当前接口按自然日返回模型汇总。\n\n近24小时：暂以今日汇总展示，菜单明确标注；\n近7天 / 30天：含今天的 7 / 30 个自然日。\n\n无法据此确定最后一笔请求的模型或精确时间。\n实际花费仅取接口的 actual_cost；缺失显示“未提供”。',justify='left',bg='#ECEEF2',fg='#686E7B',padx=12,pady=12,wraplength=445).pack(fill='x',pady=18)
        ttk.Label(usage_tab,text='仅统计当前 API Key；关闭后菜单只显示余额。\n自定义接口需返回兼容的余额和 model_stats 字段。',wraplength=460).pack(anchor='w')
        footer = ttk.Frame(outer);footer.pack(fill='x',pady=(14,0))
        def cancel():
            self.apply_avatar(original,self.cfg.get('pet_size',100))
            d.destroy()
        def save():
            try:
                cfg = self.cfg.copy()
                cfg.update({k:v.get().strip() for k,v in variables.items()})
                cfg['api_path'] = cfg['api_path'] or '/v1/usage'
                if cfg['url']: endpoint(cfg['url'],cfg['api_path'])
                elif cfg['key']: raise ValueError('填写 API Key 后，也需要填写请求地址。')
                if any(c.isspace() for c in cfg['key']): raise ValueError('API Key 不能含空格或换行。')
                cfg['interval'] = int(cfg['interval'])
                if not 60<=cfg['interval']<=86400: raise ValueError('刷新间隔需为 60～86400 秒。')
                if number(cfg['threshold'])<0: raise ValueError('阈值不能小于 0。')
                cfg['pet_size'] = max(30,min(200,round(size.get())))
                cfg['image_path'] = store_avatar(draft_image['value']) if chosen['new'] else chosen['path']
                cfg['usage_enabled'],cfg['usage_period'],cfg['topmost'] = usage.get(),PERIODS[period.get()],top.get()
                save_config(cfg)
            except (ValueError,OSError) as e:
                messagebox.showerror('无法保存',str(e),parent=d);return
            self.cfg = cfg
            self.apply_avatar(draft_image['value'],cfg['pet_size'])
            self.root.attributes('-topmost',cfg['topmost'])
            self.generation += 1
            self.next_query = 0
            self.update_balance('等待新查询','—','右键可设置接口',color='#4a3e68')
            self.show_usage()
            d.destroy()
            self.refresh()
        ttk.Label(footer,text='外观可单独保存，无需先填写 API Key。').pack(side='left')
        ttk.Button(footer,text='保存',command=save).pack(side='right')
        ttk.Button(footer,text='取消',command=cancel).pack(side='right',padx=8)
        d.protocol('WM_DELETE_WINDOW',cancel)


if __name__ == '__main__':
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    app = Pet(preview='--preview' in sys.argv)
    if '--smoke-test' in sys.argv:
        app.root.after(1600,app.root.destroy)
    app.root.mainloop()
