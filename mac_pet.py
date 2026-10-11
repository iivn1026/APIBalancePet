"""macOS translucent Qt windows; share the existing query and storage logic."""
import io
import math
import queue
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QCursor
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QDialog, QVBoxLayout,
    QHBoxLayout, QFormLayout, QTabWidget, QLineEdit, QCheckBox,
    QComboBox, QLabel, QPushButton, QSlider, QFileDialog, QMessageBox)

import balance_pet as core
from thought_bubble import cloud_image, placement


def qimage(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return QImage.fromData(buffer.getvalue())


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def showEvent(self, event):
        super().showEvent(event)
        from platform_support import clear_native_background
        clear_native_background(self.winId())

    def topmost(self, enabled):
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(enabled))
        if visible:
            self.show()


class Bubble(Overlay):
    def __init__(self, pet):
        super().__init__()
        self.pet = pet
        self.page = 0
        self.pressed = False
        self.setWindowTitle('APIBalancePet · 余额气泡')

    def reveal(self):
        self.page = 0
        self.update_content()
        self.show()
        self.raise_()
        self.activateWindow()

    def turn(self, delta):
        rows = (self.pet.usage_report or {}).get('rows', [])
        self.page = (self.page + delta) % max(1, math.ceil(len(rows)/2))
        self.update_content()

    def update_content(self):
        report = self.pet.usage_report
        rows = report.get('rows', []) if report else []
        enabled = self.pet.cfg.get('usage_enabled', True)
        body = 202 if not enabled else 295 if not rows else 326 if len(rows) == 1 else 380
        screen = self.pet.screen().availableGeometry()
        p = self.pet.geometry()
        mode, x, y, width, height = placement(p.x()-screen.x(), p.y()-screen.y(), p.width(), p.height(), screen.width(), screen.height(), body)
        anchor = p.x()-screen.x()+p.width()//2-x if mode in ('above', 'below') else p.y()-screen.y()+30-y
        background, self.offset = cloud_image(body, mode, anchor)
        self.background = qimage(background)
        self.topmost(self.pet.cfg['topmost'])
        self.setGeometry(screen.x()+x, screen.y()+y, width, height)
        self.page = min(self.page, max(0, math.ceil(len(rows)/2)-1))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawImage(0, 0, self.background)
        ox, oy = self.offset
        def text(x, y, value, size=10, color='#51466C', bold=False, left=False, width=315):
            font = QFont('PingFang SC', size)
            font.setBold(bold)
            painter.setFont(font)
            painter.setPen(QColor(color))
            rect = QRectF(x+ox if left else x+ox-width/2, y+oy-15, width, 30)
            alignment = Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft if left else Qt.AlignmentFlag.AlignHCenter)
            painter.drawText(rect, int(alignment), value)
        def button(x, y, value):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#EEE7F8'))
            painter.drawEllipse(QRectF(x+ox-14, y+oy-13, 28, 26))
            text(x, y, value)
        state = self.pet.balance_state
        text(210, 44, '让我想一想…', 9, '#8C819E')
        button(352, 48, '×')
        text(210, 76, state['label'])
        text(210, 109, state['amount'], 23 if len(state['amount']) < 21 else 17, state['color'], True, width=325)
        text(210, 142, state['status'], 8, '#8C819E')
        if not self.pet.cfg.get('usage_enabled', True):
            return
        painter.setPen(QColor('#E4DCED'))
        painter.drawLine(65+ox, 164+oy, 355+ox, 164+oy)
        report = self.pet.usage_report
        if report:
            text(210, 185, report['title'], 9, bold=True)
            text(210, 205, report['range'], 8, '#8C819E')
            text(210, 223, report['note'], 8, '#8C819E')
        else:
            text(210, 189, '最近用量', bold=True)
        rows = report.get('rows', []) if report else []
        if not rows:
            text(210, 250, report['message'] if report else '等待查询后，在这里查看用量', 9, '#8C819E')
        for i, row in enumerate(rows[self.page*2:self.page*2+2]):
            model = row['model']
            text(70, 245+i*50, model if len(model) <= 35 else model[:33]+'…', 9, bold=True, left=True, width=285)
            tokens = f"{int(row['tokens']):,}" if row['tokens'] is not None else '未提供'
            cost = f"{row['actual_cost']:,.6f} USD" if row['actual_cost'] is not None else '未提供'
            text(70, 265+i*50, f'Tokens {tokens}   ·   实际花费 {cost}', 8, '#8C819E', left=True, width=285)
        pages = max(1, math.ceil(len(rows)/2))
        if pages > 1:
            button(159, 347, '‹')
            text(210, 347, f'{self.page+1} / {pages}', 8)
            button(261, 347, '›')

    def mousePressEvent(self, event):
        point = event.position()
        x, y = point.x()-self.offset[0], point.y()-self.offset[1]
        if abs(x-352) < 16 and abs(y-48) < 16:
            self.hide()
        elif abs(y-347) < 16:
            if abs(x-159) < 16: self.turn(-1)
            elif abs(x-261) < 16: self.turn(1)

    def wheelEvent(self, event):
        self.turn(-1 if event.angleDelta().y() > 0 else 1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()


class Pet(Overlay):
    def __init__(self, preview=False):
        super().__init__()
        self.preview = preview
        self.cfg = core.DEFAULT.copy() if preview else core.load_config()
        self.setWindowTitle('APIBalancePet')
        self.balance_state = dict(label='等待设置 API Key', amount='尚未查询', status='右键角色可打开设置', color='#4A3E68')
        self.usage_report = None
        self.bubble = Bubble(self)
        self.results = queue.Queue()
        self.busy = False
        self.generation = 0
        self.next_query = time.monotonic()+1
        self.frame = 0
        self.dialog = None
        self.topmost(self.cfg['topmost'])
        try:
            image = core.read_avatar(self.cfg.get('image_path') or core.ROOT/'avatar.png')
        except ValueError:
            image = core.read_avatar(core.ROOT/'avatar.png')
        self.apply_avatar(image, self.cfg['pet_size'])
        area = self.screen().availableGeometry()
        self.move(area.right()-self.width()-50, area.bottom()-self.height()-50)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(80)
        self.show()
        if preview:
            self.show_result(('演示余额（模拟数据）', '12.3400 USD', Decimal('12.34'), '', core.summarize_usage({'model_stats': [{'model': '演示模型（非真实数据）', 'total_tokens': 1024, 'actual_cost': '0.001'}]}, core.usage_window(self.cfg))))

    def apply_avatar(self, image, size):
        scale = max(30, min(200, int(size)))/100
        factor = min(180*scale/image.width, 326*scale/image.height)
        image = image.resize((max(1, round(image.width*factor)), max(1, round(image.height*factor))), core.Image.Resampling.LANCZOS)
        self.avatar = qimage(image)
        self.resize(image.width+12, image.height+12)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawImage(6, 6+round(math.sin(self.frame/9)*3), self.avatar)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton or event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.bubble.hide()
            menu = QMenu(self)
            menu.addAction('刷新余额', self.refresh)
            menu.addAction('设置', self.settings)
            menu.addSeparator()
            menu.addAction('退出', QApplication.instance().quit)
            menu.exec(event.globalPosition().toPoint())
            self.press = None
            return
        self.press = event.globalPosition().toPoint()
        self.origin = self.pos()
        self.dragged = False

    def mouseMoveEvent(self, event):
        if not getattr(self, 'press', None): return
        delta = event.globalPosition().toPoint()-self.press
        if delta.manhattanLength() > 5: self.dragged = True
        if self.dragged:
            self.bubble.hide()
            position = self.origin+delta
            area = self.screen().availableGeometry()
            self.move(max(area.left(), min(position.x(), area.right()-self.width()+1)), max(area.top(), min(position.y(), area.bottom()-self.height()+1)))

    def mouseReleaseEvent(self, event):
        if not getattr(self, 'press', None): return
        self.press = None
        if self.dragged: return
        if self.bubble.isVisible(): self.bubble.hide()
        else:
            if self.cfg['key']: self.refresh()
            self.bubble.reveal()

    def tick(self):
        self.frame += 1
        self.update()
        from platform_support import mouse_buttons
        buttons = any(mouse_buttons())
        if self.bubble.isVisible() and buttons and not self.bubble.pressed:
            position = QCursor.pos()
            if not self.geometry().contains(position) and not self.bubble.geometry().contains(position):
                self.bubble.hide()
        self.bubble.pressed = buttons
        try:
            generation, result, error = self.results.get_nowait()
            self.busy = False
            if generation == self.generation:
                if error:
                    self.balance_state = dict(label='本次查询失败', amount='暂不可用', status=error, color='#ab5369')
                    self.usage_report = None
                    self.bubble.update_content()
                else: self.show_result(result)
        except queue.Empty: pass
        if not self.preview and self.cfg['key'] and not self.busy and time.monotonic() >= self.next_query:
            self.refresh()

    def show_result(self, result):
        label, value, number, detail, usage = result
        low = number is not None and number <= core.number(self.cfg['threshold'])
        self.balance_state = dict(label=label+(' · 余额偏低' if low else ''), amount=value, status=detail or '更新于 '+time.strftime('%H:%M:%S'), color='#b34d68' if low else '#4a3e68')
        self.usage_report = usage
        self.bubble.update_content()

    def refresh(self):
        if self.preview or self.busy or not self.cfg['key']: return
        self.busy = True
        self.next_query = time.monotonic()+int(self.cfg['interval'])
        self.balance_state['status'] = '正在查询…'
        self.bubble.update_content()
        cfg, generation = self.cfg.copy(), self.generation
        def worker():
            try: self.results.put((generation, core.fetch(cfg), None))
            except ValueError as error: self.results.put((generation, None, str(error)))
            except Exception: self.results.put((generation, None, '查询失败，请检查设置后重试。'))
        threading.Thread(target=worker, daemon=True).start()

    def settings(self):
        self.bubble.hide()
        if self.dialog:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        dialog = self.dialog = QDialog(self)
        dialog.setWindowTitle('APIBalancePet · 设置')
        dialog.resize(570, 560)
        outer = QVBoxLayout(dialog)
        tabs = QTabWidget()
        outer.addWidget(tabs)
        connection, appearance, usage = QWidget(), QWidget(), QWidget()
        for widget, title in ((connection, '接口连接'), (appearance, '图片与大小'), (usage, '用量显示')):
            tabs.addTab(widget, title)
        form = QFormLayout(connection)
        fields = {}
        for name, label in (('url', '请求地址（HTTPS）'), ('api_path', '余额接口路径'), ('key', 'API Key（系统钥匙串）'), ('interval', '刷新间隔 / 秒（60～86400）'), ('threshold', '低余额阈值')):
            field = fields[name] = QLineEdit(str(self.cfg[name]))
            if name == 'key': field.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow(label, field)
        form.addRow(QLabel('路径留空时默认 /v1/usage，从站点根目录开始。'))
        layout = QVBoxLayout(appearance)
        layout.addWidget(QLabel('导入 PNG / JPG / WebP；透明背景保留，动图使用第一帧。'))
        try:
            original = core.read_avatar(self.cfg.get('image_path') or core.ROOT/'avatar.png')
        except ValueError:
            original = core.read_avatar(core.ROOT/'avatar.png')
        draft = dict(image=original, path=self.cfg.get('image_path', ''), new=False)
        image_label = QLabel(Path(draft['path']).name if draft['path'] else '内置角色图片')
        layout.addWidget(image_label)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(30, 200)
        slider.setValue(int(self.cfg['pet_size']))
        size_label = QLabel(f'{slider.value()}%')
        def resize(value):
            size_label.setText(f'{value}%')
            self.apply_avatar(draft['image'], value)
        slider.valueChanged.connect(resize)
        def choose():
            path, _ = QFileDialog.getOpenFileName(dialog, '选择桌宠图片', '', '图片 (*.png *.jpg *.jpeg *.webp)')
            if not path: return
            try: image = core.read_avatar(path)
            except ValueError as error:
                QMessageBox.warning(dialog, '无法导入', str(error)); return
            draft.update(image=image, path=path, new=True)
            image_label.setText(Path(path).name)
            resize(slider.value())
        def reset():
            draft.update(image=core.read_avatar(core.ROOT/'avatar.png'), path='', new=False)
            image_label.setText('内置角色图片')
            resize(slider.value())
        for text, callback in (('导入图片…', choose), ('恢复默认图片', reset)):
            button = QPushButton(text); button.clicked.connect(callback); layout.addWidget(button)
        layout.addWidget(slider); layout.addWidget(size_label)
        top = QCheckBox('始终置顶'); top.setChecked(self.cfg['topmost']); layout.addWidget(top)
        layout.addStretch()
        usage_layout = QVBoxLayout(usage)
        enabled = QCheckBox('显示模型名称、Token 数与实际花费')
        enabled.setChecked(self.cfg['usage_enabled'])
        period = QComboBox(); period.addItems(list(core.PERIODS))
        period.setCurrentIndex(list(core.PERIODS.values()).index(self.cfg['usage_period']))
        period.setEnabled(enabled.isChecked()); enabled.toggled.connect(period.setEnabled)
        usage_layout.addWidget(enabled); usage_layout.addWidget(period)
        note = QLabel('接口按自然日返回模型汇总。\n近24小时展示今日汇总，非滚动24小时。\n近7天 / 30天包含今天。\n实际花费仅取 actual_cost，缺失显示“未提供”。\n无法确定最后一笔请求的模型或精确时间。')
        note.setWordWrap(True); usage_layout.addWidget(note); usage_layout.addStretch()
        buttons = QHBoxLayout(); outer.addLayout(buttons)
        buttons.addWidget(QLabel('外观可单独保存，无需填写 Key。'))
        saved = [False]
        def save():
            try:
                cfg = dict(self.cfg, **{name: field.text().strip() for name, field in fields.items()})
                cfg['api_path'] = cfg['api_path'] or '/v1/usage'
                if cfg['url']: core.endpoint(cfg['url'], cfg['api_path'])
                elif cfg['key']: raise ValueError('填写 API Key 后，也需要填写请求地址。')
                if any(c.isspace() for c in cfg['key']): raise ValueError('API Key 不能含空格或换行。')
                cfg['interval'] = int(cfg['interval'])
                if not 60 <= cfg['interval'] <= 86400: raise ValueError('刷新间隔需为 60～86400 秒。')
                if core.number(cfg['threshold']) < 0: raise ValueError('阈值不能小于 0。')
                cfg.update(pet_size=slider.value(), topmost=top.isChecked(), usage_enabled=enabled.isChecked(), usage_period=core.PERIODS[period.currentText()])
                cfg['image_path'] = core.store_avatar(draft['image']) if draft['new'] else draft['path']
                core.save_config(cfg)
            except (ValueError, OSError) as error:
                QMessageBox.warning(dialog, '无法保存', str(error)); return
            self.cfg = cfg
            self.generation += 1
            self.next_query = 0
            self.topmost(cfg['topmost'])
            self.usage_report = None
            self.balance_state = dict(label='等待新查询', amount='—', status='右键可设置接口', color='#4a3e68')
            saved[0] = True
            dialog.accept()
            self.refresh()
        cancel, submit = QPushButton('取消'), QPushButton('保存')
        cancel.clicked.connect(dialog.reject); submit.clicked.connect(save)
        buttons.addWidget(cancel); buttons.addWidget(submit)
        def finished():
            if not saved[0]: self.apply_avatar(original, self.cfg['pet_size'])
            self.dialog = None
            dialog.deleteLater()
        dialog.finished.connect(finished)
        dialog.show()


def main():
    application = QApplication(sys.argv)
    application.setQuitOnLastWindowClosed(False)
    application.setFont(QFont('PingFang SC', 10))
    pet = Pet(preview='--preview' in sys.argv)
    if '--smoke-test' in sys.argv:
        QTimer.singleShot(200, pet.bubble.reveal)
        QTimer.singleShot(700, pet.settings)
        QTimer.singleShot(1200, lambda: pet.dialog.reject() if pet.dialog else None)
        QTimer.singleShot(1600, application.quit)
    return application.exec()


if __name__ == '__main__':
    raise SystemExit(main())
