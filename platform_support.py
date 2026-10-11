"""Small native desktop differences; no network or credential access."""
import ctypes
import sys

MACOS = sys.platform == 'darwin'
FONT = 'PingFang SC' if MACOS else 'Microsoft YaHei UI'
BACKGROUND = 'systemTransparent' if MACOS else '#ff00ff'


def transparent_window(window, tool=False):
    window.configure(bg=BACKGROUND)
    if MACOS:
        window.wm_attributes('-transparent', True)
    else:
        window.wm_attributes('-transparentcolor', BACKGROUND)
        if tool:
            window.wm_attributes('-toolwindow', True)


if MACOS:
    _objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
    _objc.objc_getClass.argtypes = [ctypes.c_char_p]
    _objc.objc_getClass.restype = ctypes.c_void_p
    _objc.sel_registerName.argtypes = [ctypes.c_char_p]
    _objc.sel_registerName.restype = ctypes.c_void_p

    def _message(receiver, selector, result=ctypes.c_void_p, *arguments):
        call = ctypes.CFUNCTYPE(result, ctypes.c_void_p, ctypes.c_void_p,
                                *(kind for kind, value in arguments))(('objc_msgSend', _objc))
        return call(receiver, _objc.sel_registerName(selector.encode()),
                    *(value for kind, value in arguments))

    def clear_native_background(view_id):
        """Qt winId is an NSView; clear its owning NSWindow after creation."""
        window = _message(int(view_id), 'window')
        if window:
            clear = _message(_objc.objc_getClass(b'NSColor'), 'clearColor')
            _message(window, 'setOpaque:', None, (ctypes.c_bool, False))
            _message(window, 'setBackgroundColor:', None, (ctypes.c_void_p, clear))
            _message(window, 'setHasShadow:', None, (ctypes.c_bool, False))

    _events = ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
    _button_state = _events.CGEventSourceButtonState
    _button_state.argtypes = [ctypes.c_int, ctypes.c_uint32]
    _button_state.restype = ctypes.c_bool


def mouse_buttons():
    if MACOS:
        return tuple(bool(_button_state(0, button)) for button in (0, 1))
    return tuple(bool(ctypes.windll.user32.GetAsyncKeyState(button) & 0x8001)
                 for button in (1, 2))
