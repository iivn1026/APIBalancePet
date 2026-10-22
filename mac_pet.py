"""macOS menu bar balance monitor with native controls and Keychain accounts."""
import copy
import queue
import sys
import threading
import time
from decimal import Decimal
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QCursor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap, QPalette, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu, QDialog,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QToolButton, QLineEdit,
    QCheckBox, QComboBox, QSpinBox, QListWidget, QScrollArea, QFrame, QStackedWidget,
    QDialogButtonBox, QMessageBox)

import balance_pet as core
import mac_accounts as storage
from mac_status import NativeTray


def title(text, size=15, bold=False):
    label = QLabel(text)
    font = label.font()
    font.setPointSize(size)
    font.setBold(bold)
    label.setFont(font)
    return label


def secondary(text):
    label = QLabel(text)
    font = label.font()
    font.setPointSize(14)
    label.setFont(font)
    label.setObjectName('secondary')
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def button(text, callback):
    control = QPushButton(text)
    control.clicked.connect(callback)
    return control


def balance_title(result):
    if not result: return '—'
    _, display, value, _, _ = result
    if value is None: return display
    unit = display.rsplit(' ', 1)[-1]
    places = 4 if 0 < abs(value) < Decimal('0.01') else 2
    return f'{value:,.{places}f} {unit}'


def tray_icon(dark=False):
    image = QPixmap(44, 44)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor('white' if dark else 'black'), 3.2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(5, 10, 34, 26), 6, 6)
    painter.drawLine(9, 10, 31, 6)
    painter.drawRoundedRect(QRectF(27, 20, 13, 9), 3, 3)
    painter.drawPoint(32, 24)
    painter.end()
    image.setDevicePixelRatio(2)
    icon = QIcon(image)
    icon.setIsMask(True)
    return icon


def appearance(app):
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSize(14)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    if app.font() != font: app.setFont(font)
    for widget_class in ('QLabel', 'QLineEdit', 'QPushButton', 'QToolButton', 'QComboBox', 'QSpinBox', 'QCheckBox', 'QListWidget'):
        if app.font(widget_class) != font: app.setFont(font, widget_class)
    dark = app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    sheet = '''
        QLabel { color: %s; }
        QLabel#secondary { color: %s; }
        QFrame#accountCard { background: %s; border: 1px solid %s; border-radius: 12px; }
        QLabel#lowBalance { color: %s; }
        QLineEdit { color: %s; background: %s; border: 1px solid %s;
                    border-radius: 6px; padding: 5px 8px; min-height: 24px;
                    selection-background-color: #0a64d8; selection-color: white; }
        QLineEdit:focus { border: 2px solid #0a84ff; padding: 4px 7px; }
        QLineEdit { placeholder-text-color: %s; }
        QListWidget { border: 1px solid %s; border-radius: 8px; }
        QListWidget::item { padding: 10px 8px; }
        QListWidget::item:selected { color: white; background: #0a64d8; }
        QPushButton, QToolButton { color: %s; background: %s; border: 1px solid %s;
                                 border-radius: 6px; padding: 5px 10px; min-height: 22px; }
        QPushButton:hover, QToolButton:hover { border-color: #0a84ff; }
        QPushButton:default { color: white; background: #0a64d8; border-color: #0a64d8; }
        QPushButton:disabled, QToolButton:disabled { color: %s; background: %s; }
        QCheckBox, QComboBox, QSpinBox { color: %s; }
        QComboBox, QSpinBox { min-height: 28px; }
        QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
    ''' % (('#f5f5f7', '#c5c5cb', '#252527', '#525256', '#ffb454', '#f5f5f7', '#1c1c1e', '#636368', '#b5b5bc', '#525256',
             '#f5f5f7', '#48484c', '#75757d', '#a8a8ad', '#353538', '#f5f5f7')
           if dark else ('#1d1d1f', '#42424a', '#ffffff', '#cacacf', '#925000', '#1d1d1f', '#ffffff', '#a9a9b0', '#62626b', '#cacacf',
                         '#1d1d1f', '#ffffff', '#a9a9b0', '#686871', '#e5e5e9', '#1d1d1f'))
    if app.styleSheet() != sheet: app.setStyleSheet(sheet)


class Settings(QDialog):
    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.draft = copy.deepcopy(monitor.data)
        self.current = -1
        self.setWindowTitle('API 余额 · 设置 · 1.2.0')
        self.resize(860, 650)
        self.setMinimumSize(780, 590)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        heading = title('连接与偏好设置', 22, True)
        outer.addWidget(heading)
        outer.addWidget(secondary('分别管理不同服务商或不同 API Key 的余额。'))
        body = QHBoxLayout()
        outer.addLayout(body, 1)
        sidebar = QVBoxLayout()
        body.addLayout(sidebar, 1)
        self.list = QListWidget()
        self.list.setMinimumWidth(190)
        sidebar.addWidget(self.list, 1)
        actions = QHBoxLayout()
        actions.addWidget(button('添加连接', self.add))
        self.remove_button = button('移除', self.remove)
        actions.addWidget(self.remove_button)
        sidebar.addLayout(actions)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 3)
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch()
        empty_layout.addWidget(title('添加第一个连接', 18, True))
        empty_layout.addWidget(secondary('填写 HTTPS 地址和 API Key，余额将出现在菜单栏面板中。'))
        empty_layout.addWidget(button('添加连接', self.add))
        empty_layout.addStretch()
        self.pages.addWidget(empty)
        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        form = QFormLayout()
        form.setSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields = {}
        for name, label, placeholder in (
            ('name', '连接名称', '例如：工作账户'),
            ('url', 'API 地址', 'https://example.com'),
            ('api_path', '余额接口路径', '/v1/usage'),
            ('key', 'API Key', '保存在 macOS 钥匙串'),
            ('threshold', '低余额阈值', '5')):
            field = QLineEdit()
            field.setPlaceholderText(placeholder)
            if name == 'key': field.setEchoMode(QLineEdit.EchoMode.Password)
            self.fields[name] = field
            form.addRow(label, field)
        self.enabled = QCheckBox('启用此连接')
        form.addRow('', self.enabled)
        self.show_key = QCheckBox('显示密钥')
        self.show_key.toggled.connect(lambda checked: self.fields['key'].setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        form.addRow('', self.show_key)
        editor_layout.addLayout(form)
        self.key_note = secondary('')
        editor_layout.addWidget(self.key_note)
        editor_layout.addWidget(secondary('地址和密钥可以不同。接口需返回兼容的余额字段；支持自定义路径，不会自动适配不同服务商的响应格式。'))
        editor_layout.addStretch()
        editor_scroll = QScrollArea()
        editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setWidget(editor)
        self.pages.addWidget(editor_scroll)
        prefs = QHBoxLayout()
        self.interval = QSpinBox()
        self.interval.setRange(60, 86400)
        self.interval.setValue(int(self.draft['interval']))
        self.interval.setSuffix(' 秒')
        prefs.addWidget(QLabel('自动刷新'))
        prefs.addWidget(self.interval)
        self.usage = QCheckBox('显示模型用量')
        self.usage.setChecked(self.draft['usage_enabled'])
        prefs.addWidget(self.usage)
        self.period = QComboBox()
        for label, value in core.PERIODS.items(): self.period.addItem(label, value)
        self.period.setCurrentIndex(max(0, self.period.findData(self.draft['usage_period'])))
        self.period.setEnabled(self.usage.isChecked())
        self.usage.toggled.connect(self.period.setEnabled)
        prefs.addWidget(self.period)
        prefs.addStretch()
        outer.addLayout(prefs)
        outer.addWidget(secondary('仅查询已启用的连接。取消或关闭窗口不会保存修改。'))
        footer = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        footer.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        footer.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        footer.accepted.connect(self.save)
        footer.rejected.connect(self.reject)
        outer.addWidget(footer)
        for item in self.draft['accounts']: self.list.addItem(item['name'])
        self.list.currentRowChanged.connect(self.select)
        if self.draft['accounts']: self.list.setCurrentRow(0)
        else: self.select(-1)
        self.fields['name'].textEdited.connect(self.rename)

    def flush(self):
        if not 0 <= self.current < len(self.draft['accounts']): return
        item = self.draft['accounts'][self.current]
        for key, field in self.fields.items():
            value = field.text().strip()
            if key == 'key' and item['key'] is None and not value: continue
            item[key] = value
        item['api_path'] = item['api_path'] or '/v1/usage'
        item['enabled'] = self.enabled.isChecked()

    def select(self, row):
        self.flush()
        self.current = row
        valid = 0 <= row < len(self.draft['accounts'])
        self.remove_button.setEnabled(valid)
        self.pages.setCurrentIndex(1 if valid else 0)
        if not valid: return
        item = self.draft['accounts'][row]
        self.show_key.setChecked(False)
        for key, field in self.fields.items(): field.setText(item.get(key) or '')
        self.enabled.setChecked(item['enabled'])
        self.key_note.setText(item.get('key_error', '密钥加密保存在系统钥匙串中。') + (' 留空将保留原密钥。' if item['key'] is None else ''))

    def rename(self, text):
        if self.current >= 0: self.list.item(self.current).setText(text or '未命名连接')

    def add(self):
        self.flush()
        item = storage.account('新连接')
        self.draft['accounts'].append(item)
        self.list.addItem(item['name'])
        self.list.setCurrentRow(len(self.draft['accounts'])-1)
        self.fields['name'].setFocus()
        self.fields['name'].selectAll()

    def remove(self):
        row = self.current
        if row < 0: return
        self.current = -1
        self.draft['accounts'].pop(row)
        self.list.takeItem(row)
        if self.draft['accounts']:
            next_row = min(row, len(self.draft['accounts'])-1)
            self.list.setCurrentRow(next_row)
            self.select(next_row)
        else: self.select(-1)

    def save(self):
        self.flush()
        self.draft.update(interval=self.interval.value(), usage_enabled=self.usage.isChecked(), usage_period=self.period.currentData())
        try:
            if self.monitor.preview: storage.validate(self.draft)
            else: storage.save(self.draft)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, '无法保存', str(error))
            return
        self.monitor.configure(self.draft)
        self.accept()


class Panel(QDialog):
    def __init__(self, monitor):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.monitor = monitor
        self.setWindowTitle('API 余额')
        self.setAutoFillBackground(True)
        self.setFixedWidth(460)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 12)
        outer.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(title('API 余额', 22, True))
        header.addStretch()
        self.refresh_button = button('全部刷新', monitor.refresh_all)
        header.addWidget(self.refresh_button)
        outer.addLayout(header)
        self.summary = secondary('')
        outer.addWidget(self.summary)
        selection = QHBoxLayout()
        selection.addWidget(QLabel('菜单栏显示'))
        self.selection = QComboBox()
        self.selection.setMinimumWidth(200)
        self.selection.setAccessibleName('菜单栏余额账户')
        selection.addWidget(self.selection, 1)
        self.selection.currentIndexChanged.connect(self.select_balance)
        outer.addLayout(selection)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll, 1)
        footer = QHBoxLayout()
        footer.addWidget(button('管理连接…', monitor.settings))
        footer.addStretch()
        footer.addWidget(secondary('1.2.0'))
        footer.addWidget(button('退出', QApplication.instance().quit))
        outer.addLayout(footer)
        self.rebuild()

    def select_balance(self, index):
        identifier = self.selection.itemData(index)
        if identifier: self.monitor.select_account(identifier)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Window))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Midlight), 1))
        painter.setBrush(self.palette().color(QPalette.ColorRole.Window))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 14, 14)

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(1.0)

    def rebuild(self):
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        accounts = self.monitor.data['accounts']
        enabled = sum(bool(item['enabled']) for item in accounts)
        self.selection.blockSignals(True)
        self.selection.clear()
        for item in accounts:
            if item['enabled']: self.selection.addItem(item['name'], item['id'])
        selected = self.monitor.display_account()
        self.selection.setCurrentIndex(self.selection.findData(selected['id']) if selected else -1)
        self.selection.setEnabled(self.selection.count() > 0)
        self.selection.blockSignals(False)
        self.summary.setText(('演示模式 · 模拟余额，不发起请求' if self.monitor.preview else f'{len(accounts)} 个连接 · {enabled} 个已启用'))
        self.refresh_button.setEnabled(any(item['enabled'] and item['key'] for item in accounts) and not any(state.get('busy') for state in self.monitor.states.values()))
        if not accounts:
            layout.addWidget(title('所有余额，一眼可见', 17, True))
            layout.addWidget(secondary('添加 API 地址和密钥，即可在这里查看每个连接的余额与模型用量。'))
            layout.addWidget(button('添加连接', self.monitor.settings))
        for item in accounts:
            card = QFrame()
            card.setObjectName('accountCard')
            content = QVBoxLayout(card)
            content.setContentsMargins(14, 12, 14, 12)
            content.setSpacing(5)
            row = QHBoxLayout()
            name = title(item['name'], 15, True)
            name.setTextFormat(Qt.TextFormat.PlainText)
            name.setWordWrap(True)
            row.addWidget(name, 1)
            state = self.monitor.states.get(item['id'], {})
            refresh = QToolButton()
            refresh.setText('刷新')
            refresh.setAccessibleName('刷新 '+item['name'])
            refresh.setEnabled(bool(item['enabled'] and item['key']) and not state.get('busy', False))
            refresh.clicked.connect(lambda checked=False, identifier=item['id']: self.monitor.refresh(identifier))
            row.addWidget(refresh)
            content.addLayout(row)
            content.addWidget(secondary(urlsplit(item['url']).netloc))
            result = state.get('result')
            if result:
                label, amount, value, detail, usage = result
                content.addWidget(secondary(label))
                amount_label = title(amount, 28, True)
                amount_label.setTextFormat(Qt.TextFormat.PlainText)
                if value is not None and value <= core.number(item['threshold']): amount_label.setObjectName('lowBalance')
                content.addWidget(amount_label)
                if detail: content.addWidget(secondary(detail))
                if usage and self.monitor.data['usage_enabled']:
                    toggle = QToolButton()
                    toggle.setText('模型用量  ▾')
                    toggle.setCheckable(True)
                    details = QWidget()
                    detail_layout = QVBoxLayout(details)
                    detail_layout.setContentsMargins(0, 4, 0, 0)
                    detail_layout.addWidget(secondary(usage['range']+'\n'+usage['note']))
                    for model in usage['rows']:
                        detail_layout.addWidget(secondary(core.usage_row_text(model)))
                    if not usage['rows']: detail_layout.addWidget(secondary(usage['message']))
                    details.setVisible(False)
                    toggle.toggled.connect(details.setVisible)
                    content.addWidget(toggle)
                    content.addWidget(details)
            else:
                content.addWidget(title('—', 28, True))
            if not item['enabled']: status = '已停用'
            elif item.get('key_error'): status = item['key_error']
            elif not item['key']: status = '尚未填写 API Key'
            elif state.get('busy'): status = '正在刷新…'
            elif state.get('error'): status = state['error'] + ('\n显示上次成功结果 · '+state['updated'] if result else '')
            elif state.get('updated'): status = '更新于 '+state['updated']
            else: status = '等待查询'
            content.addWidget(secondary(status))
            layout.addWidget(card)
        layout.addStretch()
        old = self.scroll.takeWidget()
        self.scroll.setWidget(body)
        if old: old.deleteLater()
        self.resize(460, min(690, max(320, len(accounts)*235+205)))

    def reveal(self):
        self.rebuild()
        rect = self.monitor.tray.geometry()
        screen = (QApplication.screenAt(rect.center()) if rect.isValid() else None) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.resize(self.width(), min(self.height(), area.height()-16))
        x = rect.center().x()-self.width()//2 if rect.isValid() else area.right()-self.width()-12
        y = max(area.top()+6, rect.bottom()+6) if rect.isValid() else area.top()+6
        self.move(max(area.left()+8, min(x, area.right()-self.width()-8)), min(y, area.bottom()-self.height()-8))
        self.show()
        self.raise_()
        self.activateWindow()


class Monitor:
    def __init__(self, preview=False):
        self.preview = preview
        self.data = storage.load() if not preview else dict(storage.PREFERENCES, accounts=[
            storage.account('工作账户', url='https://work.example.com', key='demo'),
            storage.account('个人账户', url='https://personal.example.com', key='demo')])
        self.states = {}
        self.generation = 0
        self.jobs = queue.Queue()
        self.results = queue.Queue()
        self.dialog = None
        self.tray = NativeTray()
        self.tray.setToolTip('APIBalancePet · API 余额')
        self.update_icon()
        self.menu = QMenu()
        self.menu.addAction('查看余额', self.show_panel)
        self.menu.addAction('全部刷新', self.refresh_all)
        self.menu.addSeparator()
        self.menu.addAction('设置…', self.settings).setShortcut(QKeySequence('Ctrl+,'))
        self.menu.addAction('重新读取钥匙串', self.reload)
        self.menu.addSeparator()
        self.menu.addAction('退出 APIBalancePet', QApplication.instance().quit)
        self.tray.activated.connect(self.activate)
        self.panel = Panel(self)
        self.tray.show()
        self.next_refresh = time.monotonic()+1
        for _ in range(4): threading.Thread(target=self.worker, daemon=True).start()
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(200)
        QApplication.instance().paletteChanged.connect(self.update_icon)
        if preview:
            for index, item in enumerate(self.data['accounts']):
                amount = Decimal('128.45') if index == 0 else Decimal('3.21')
                self.states[item['id']] = dict(result=('钱包余额', f'{amount} USD', amount, '', core.summarize_usage({'model_stats':[dict(model='示例模型', total_tokens=128000, actual_cost='0.36')]}, core.usage_window(self.data))), updated='12:30:00')
        self.panel.rebuild()
        self.update_status()

    def update_icon(self, *args):
        self.tray.setIcon(tray_icon(QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128))
        appearance(QApplication.instance())

    def display_account(self):
        enabled = [item for item in self.data['accounts'] if item['enabled']]
        return next((item for item in enabled if item['id'] == self.data.get('menubar_account')), enabled[0] if enabled else None)

    def select_account(self, identifier):
        if not self.preview:
            try: storage.save_selection(identifier)
            except (OSError, ValueError):
                QMessageBox.warning(self.panel, '无法保存选择', '无法保存菜单栏账户，请检查配置文件权限。')
                return
        self.data['menubar_account'] = identifier
        self.update_status()

    def update_status(self):
        item = self.display_account()
        if not item:
            self.tray.setTitle('—')
            self.tray.setToolTip('API 余额 · 请添加或启用连接')
            return
        state = self.states.get(item['id'], {})
        amount = balance_title(state.get('result'))
        stale = bool(state.get('error') or item.get('key_error'))
        self.tray.setTitle(amount + (' !' if stale else ''))
        note = state.get('error') or item.get('key_error') or ('正在刷新' if state.get('busy') else '')
        self.tray.setToolTip(item['name'] + ' · ' + amount + ('\n'+note if note else '') + ('\n上次更新 '+state['updated'] if state.get('updated') else ''))

    def activate(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Context:
            self.panel.hide()
            self.menu.popup(QCursor.pos())
            return
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.panel.isVisible(): self.panel.hide()
            else: self.show_panel()

    def show_panel(self): self.panel.reveal()

    def settings(self):
        self.panel.hide()
        if not self.dialog:
            self.dialog = Settings(self)
            self.dialog.finished.connect(self.close_settings)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def close_settings(self):
        dialog, self.dialog = self.dialog, None
        dialog.deleteLater()

    def configure(self, data):
        self.data = copy.deepcopy(data)
        self.generation += 1
        self.states = {}
        self.next_refresh = time.monotonic()+int(data['interval'])
        self.panel.rebuild()
        self.update_status()
        self.refresh_all()

    def reload(self):
        if self.preview: return
        try: self.configure(storage.load())
        except OSError as error: QMessageBox.warning(None, '无法读取配置', str(error))

    def refresh_all(self):
        for item in self.data['accounts']: self.refresh(item['id'], rebuild=False)
        self.panel.rebuild()
        self.update_status()
        self.next_refresh = time.monotonic()+int(self.data['interval'])

    def refresh(self, identifier, rebuild=True):
        if self.preview: return
        item = next((item for item in self.data['accounts'] if item['id'] == identifier), None)
        if not item or not item['enabled'] or not item['key']: return
        state = self.states.setdefault(identifier, {})
        if state.get('busy'): return
        state['busy'] = True
        config = dict(core.DEFAULT, **{k: v for k, v in self.data.items() if k in core.DEFAULT})
        config.update({k: item[k] for k in ('url', 'api_path', 'key', 'threshold')})
        self.jobs.put((identifier, self.generation, config))
        self.update_status()
        if rebuild: self.panel.rebuild()

    def worker(self):
        while True:
            identifier, generation, config = self.jobs.get()
            try:
                if generation != self.generation: continue
                try: result, error = core.fetch(config), None
                except ValueError as failure: result, error = None, str(failure)
                except Exception: result, error = None, '查询失败，请检查连接设置。'
                self.results.put((identifier, generation, result, error))
            finally: self.jobs.task_done()

    def tick(self):
        changed = False
        while True:
            try: identifier, generation, result, error = self.results.get_nowait()
            except queue.Empty: break
            if generation != self.generation: continue
            state = self.states.setdefault(identifier, {})
            state.update(busy=False, error=error)
            if result: state.update(result=result, updated=time.strftime('%H:%M:%S'))
            changed = True
        if changed:
            self.panel.rebuild()
            self.update_status()
        if not self.preview and time.monotonic() >= self.next_refresh: self.refresh_all()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('APIBalancePet')
    app.setQuitOnLastWindowClosed(False)
    appearance(app)
    if not QSystemTrayIcon.isSystemTrayAvailable() and '--smoke-test' not in sys.argv:
        QMessageBox.critical(None, '菜单栏不可用', '当前桌面环境不支持菜单栏图标。')
        return 1
    try: monitor = Monitor(preview='--preview' in sys.argv)
    except OSError as error:
        QMessageBox.critical(None, '无法启动', str(error))
        return 1
    if '--smoke-test' in sys.argv:
        QTimer.singleShot(200, monitor.show_panel)
        QTimer.singleShot(600, monitor.settings)
        QTimer.singleShot(1100, lambda: monitor.dialog.reject() if monitor.dialog else None)
        QTimer.singleShot(1500, app.quit)
    app.aboutToQuit.connect(monitor.tray.hide)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
