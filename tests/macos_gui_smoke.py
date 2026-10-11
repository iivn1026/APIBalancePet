"""Run on a Mac desktop: .venv/bin/python tests/macos_gui_smoke.py."""
import ctypes
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import balance_pet as core
from mac_pet import QApplication, Pet, QImage, QTimer, Qt
from platform_support import _message

application = QApplication([])
application.setQuitOnLastWindowClosed(False)
pet = Pet(preview=True)
errors = []


def verify():
    try:
        pet.bubble.reveal()
        application.processEvents()
        for widget in (pet, pet.bubble):
            assert widget.windowFlags() & Qt.WindowType.FramelessWindowHint
            image = QImage(widget.size(), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            widget.render(image)
            assert image.pixelColor(0, 0).alpha() == 0
            assert any(image.pixelColor(x, y).alpha() > 0
                       for x in range(0, image.width(), 10)
                       for y in range(0, image.height(), 10))
            native = _message(int(widget.winId()), 'window')
            assert not _message(native, 'styleMask', ctypes.c_ulong) & 1
            assert not _message(native, 'isOpaque', ctypes.c_bool)
        original_size = pet.size()
        pet.settings()
        application.processEvents()
        assert pet.dialog.isVisible()
        pet.apply_avatar(core.read_avatar(core.ROOT/'avatar.png'), 50)
        pet.dialog.reject()
        application.processEvents()
        assert pet.dialog is None
        assert pet.size() == original_size
    except Exception as error:
        errors.append(error)
    finally:
        application.quit()


QTimer.singleShot(300, verify)
application.exec()
if errors:
    raise errors[0]
print('Passed: transparent pixels, visible content, native borderless windows, settings cancellation.')
