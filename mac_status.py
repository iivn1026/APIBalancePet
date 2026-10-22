"""Native macOS status item with a template image and crisp system-rendered text."""
import AppKit
from Foundation import NSObject, NSData
from PySide6.QtCore import QObject, Signal, QRect, QBuffer, QIODevice
from PySide6.QtWidgets import QSystemTrayIcon


class StatusTarget(NSObject):
    def clicked_(self, sender):
        event = AppKit.NSApplication.sharedApplication().currentEvent()
        context = event and event.type() in (AppKit.NSEventTypeRightMouseDown, AppKit.NSEventTypeRightMouseUp)
        if self.callback:
            self.callback(QSystemTrayIcon.ActivationReason.Context if context else QSystemTrayIcon.ActivationReason.Trigger)


class NativeTray(QObject):
    activated = Signal(object)

    def __init__(self):
        super().__init__()
        self.bar = AppKit.NSStatusBar.systemStatusBar()
        self.item = self.bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        self.item.setVisible_(False)
        self.target = StatusTarget.alloc().init()
        self.target.callback = self.activated.emit
        button = self.item.button()
        button.setTarget_(self.target)
        button.setAction_('clicked:')
        button.sendActionOn_(AppKit.NSEventMaskLeftMouseUp | AppKit.NSEventMaskRightMouseUp)
        button.setImagePosition_(AppKit.NSImageLeft)
        button.setFont_(AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(13, AppKit.NSFontWeightMedium))

    def setIcon(self, icon):
        pixmap = icon.pixmap(44, 44)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, 'PNG')
        data = bytes(buffer.data())
        native = AppKit.NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(data, len(data)))
        native.setSize_((18, 18))
        native.setTemplate_(True)
        self.item.button().setImage_(native)

    def setTitle(self, value):
        self.item.button().setTitle_(' '+value if value else '')

    def setToolTip(self, value): self.item.button().setToolTip_(value)
    def show(self): self.item.setVisible_(True)
    def hide(self): self.item.setVisible_(False)
    def isVisible(self): return bool(self.item.isVisible())

    def geometry(self):
        button = self.item.button()
        window = button.window()
        if not window: return QRect()
        rect = window.convertRectToScreen_(button.convertRect_toView_(button.bounds(), None))
        top = AppKit.NSScreen.screens()[0].frame().size.height
        return QRect(round(rect.origin.x), round(top-rect.origin.y-rect.size.height), round(rect.size.width), round(rect.size.height))
