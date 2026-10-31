"""Accès Windows (ctypes uniquement, aucune dépendance externe) : fenêtre, capture, souris, F12.
Le module s'importe aussi sous Linux (pour les tests) ; les fonctions échouent alors proprement."""
import sys, time, ctypes
import numpy as np

IS_WINDOWS = sys.platform.startswith("win")
VK_F12 = 0x7B

if IS_WINDOWS:
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    try:                                   # coordonnées réelles en pixels (écrans mis à l'échelle)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


    HANDLE = ctypes.c_void_p
    user32.GetDC.restype, user32.GetDC.argtypes = HANDLE, [HANDLE]
    user32.ReleaseDC.argtypes = [HANDLE, HANDLE]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    gdi32.CreateCompatibleDC.restype, gdi32.CreateCompatibleDC.argtypes = HANDLE, [HANDLE]
    gdi32.CreateCompatibleBitmap.restype = HANDLE
    gdi32.CreateCompatibleBitmap.argtypes = [HANDLE, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype, gdi32.SelectObject.argtypes = HANDLE, [HANDLE, HANDLE]
    gdi32.BitBlt.argtypes = [HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_uint32]
    gdi32.DeleteObject.argtypes = [HANDLE]
    gdi32.DeleteDC.argtypes = [HANDLE]
    gdi32.GetDIBits.argtypes = [HANDLE, HANDLE, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_uint]


def _need_windows():
    if not IS_WINDOWS:
        raise RuntimeError("Cette fonction n'existe que sous Windows.")


def find_window(title_contains, exclude_prefix="DofusAuto"):
    """Retourne (hwnd, (left, top, right, bottom)) de la plus grande fenêtre visible, ou None."""
    _need_windows()
    found = []
    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        if title_contains.lower() in title.lower() and not title.startswith(exclude_prefix):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            w, h = r.right - r.left, r.bottom - r.top
            if w > 200 and h > 200:
                found.append((w * h, hwnd, (r.left, r.top, r.right, r.bottom)))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    if not found:
        return None
    found.sort(reverse=True)
    return found[0][1], found[0][2]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


def grab_rect(rect):
    """Capture un rectangle de l'écran (left, top, right, bottom) -> image BGR (numpy)."""
    _need_windows()
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    hdc = user32.GetDC(0)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
    gdi32.BitBlt(mdc, 0, 0, w, h, hdc, left, top, SRCCOPY | CAPTUREBLT)
    bi = _BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = w, -h            # négatif = de haut en bas
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.SelectObject(mdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(0, hdc)
    img = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 4)
    return np.ascontiguousarray(img[:, :, :3])


def click_screen(x, y, count=1, interval_s=0.2):
    """Clic gauche avec la vraie souris, aux coordonnées écran."""
    _need_windows()
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.06)
    for i in range(count):
        user32.mouse_event(0x0002, 0, 0, 0, 0)   # bouton gauche enfoncé
        time.sleep(0.05)
        user32.mouse_event(0x0004, 0, 0, 0, 0)   # relâché
        if i < count - 1:
            time.sleep(interval_s)


def key_pressed(vk=VK_F12):
    if not IS_WINDOWS:
        return False
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)
