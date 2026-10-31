"""Lien entre le robot et le vrai monde : fenêtre BlueStacks, capture, souris."""
import time
from . import winapi


class WindowBackend:
    def __init__(self, cfg, stop_flag=None):
        self.cfg = cfg
        self.rect = None
        self._stop = stop_flag or (lambda: False)

    def locate(self):
        r = winapi.find_window(self.cfg["window_title_contains"])
        self.rect = r[1] if r else None
        return self.rect

    def grab(self):
        """Image BGR de la fenêtre BlueStacks (None si la fenêtre est introuvable)."""
        rect = self.locate()
        if rect is None:
            return None
        return winapi.grab_rect(rect)

    def click(self, x, y, count=1):
        """(x, y) en coordonnées de l'image capturée -> clic réel à l'écran."""
        if self.rect is None:
            self.locate()
        if self.rect is None:
            return
        winapi.click_screen(self.rect[0] + x, self.rect[1] + y, count, self.cfg["click_interval_ms"] / 1000.0)

    def sleep(self, seconds):
        """Pause interrompue immédiatement par l'arrêt (F12 / bouton)."""
        end = time.time() + seconds
        while time.time() < end:
            if self.stopped():
                return
            time.sleep(min(0.05, max(0.0, end - time.time())))

    def stopped(self):
        return self._stop() or winapi.key_pressed(winapi.VK_F12)
