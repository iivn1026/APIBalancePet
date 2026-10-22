"""Exercise menu bar UI and account editing with mock data, no real Keychain/network."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
import queue
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPalette,QColor
from PySide6.QtWidgets import QApplication
from mac_pet import Monitor, appearance, balance_title
from PySide6.QtWidgets import QLabel

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
appearance(app)
monitor = Monitor(preview=True)
errors = []


def verify():
    try:
        assert monitor.tray.isVisible()
        monitor.show_panel()
        assert monitor.panel.isVisible()
        monitor.settings()
        dialog = monitor.dialog
        assert dialog.isVisible()
        first_id = dialog.draft['accounts'][0]['id']
        dialog.fields['name'].setText('改名账户')
        dialog.add()
        dialog.fields['name'].setText('第三个连接')
        dialog.fields['url'].setText('https://third.example.com')
        dialog.fields['key'].setText('third-secret')
        dialog.select(0)
        assert dialog.fields['name'].text() == '改名账户'
        dialog.list.setCurrentRow(2)
        dialog.remove()
        assert len(dialog.draft['accounts']) == 2
        dialog.reject()
        assert len(monitor.data['accounts']) == 2
        assert monitor.data['accounts'][0]['name'] == '工作账户'
        assert monitor.dialog is None
        monitor.settings()
        monitor.dialog.fields['name'].setText('保存账户')
        monitor.dialog.save()
        assert monitor.data['accounts'][0]['name'] == '保存账户'
        monitor.preview = False
        with patch.object(monitor, 'jobs', queue.Queue()):
            monitor.refresh_all()
            jobs = [monitor.jobs.get_nowait(), monitor.jobs.get_nowait()]
        assert jobs[0][2]['url'] != jobs[1][2]['url']
        assert jobs[0][0] != jobs[1][0]
        assert jobs[0][2]['key'] == 'demo'
        monitor.results.put((first_id, monitor.generation-1, None, 'stale failure'))
        monitor.tick()
        assert not monitor.states[first_id].get('error')
        monitor.preview = True
        sample = Monitor(preview=True)
        sample.show_panel()
        assert sample.tray.item.button().title().strip() == '128.45 USD'
        sample.panel.selection.setCurrentIndex(1)
        assert sample.tray.item.button().title().strip() == '3.21 USD'
        sample.panel.selection.setCurrentIndex(0)
        assert sample.tray.item.button().title().strip() == '128.45 USD'
        for label in sample.panel.findChildren(QLabel):
            assert label.font().pointSizeF() >= 14, (label.text(), label.font().pointSizeF())
        sample.panel.grab().save(str(Path(__file__).resolve().parents[1]/'build/menubar-panel.png'))
        sample.settings()
        sample.dialog.grab().save(str(Path(__file__).resolve().parents[1]/'build/menubar-settings.png'))
        light = QPalette(app.palette())
        light.setColor(QPalette.ColorRole.Window, QColor('#f2f2f7'))
        light.setColor(QPalette.ColorRole.WindowText, QColor('#1d1d1f'))
        light.setColor(QPalette.ColorRole.Base, QColor('white'))
        light.setColor(QPalette.ColorRole.Text, QColor('#1d1d1f'))
        app.setPalette(light)
        appearance(app)
        app.processEvents()
        assert '#42424a' in app.styleSheet()
        sample.dialog.grab().save(str(Path(__file__).resolve().parents[1]/'build/menubar-settings-light.png'))
        sample.panel.grab().save(str(Path(__file__).resolve().parents[1]/'build/menubar-panel-light.png'))
        sample.tray.hide()
        print('Passed: tray, panel, add/switch/remove/save/cancel, query isolation, stale result handling.')
    except Exception as error:
        errors.append(error)
    finally:
        monitor.tray.hide()
        app.quit()


QTimer.singleShot(300, verify)
app.exec()
if errors: raise errors[0]
