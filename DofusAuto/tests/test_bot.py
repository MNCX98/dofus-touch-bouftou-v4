import os, cv2, numpy as np
from collections import deque
import bot as botmod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = lambda n: cv2.imread(os.path.join(ROOT, "tests", "fixtures", n + ".png"))


class FakeBackend:
    """Joue une suite d'écrans prévus à l'avance et note tous les clics."""
    def __init__(self, frames):
        self.frames, self.clicks, self.last = deque(frames), [], None

    def grab(self):
        if self.frames:
            self.last = self.frames.popleft()
        return self.last

    def click(self, x, y, count=1):
        self.clicks.append((x, y, count))

    def sleep(self, s):
        pass

    def stopped(self):
        return False


def make_bot(frames, **over):
    cfg = {"window_title_contains": "BlueStacks", "threshold": 0.8, "button_threshold": 0.95,
           "scan_interval_ms": 0, "cooldown_after_click_s": 4.0, "click_count": 2, "click_interval_ms": 0,
           "save_diagnostics": False, "spells_per_turn": 2, "spell_wait_s": 0, "target_wait_s": 0,
           "cast_wait_s": 0, "end_turn_cooldown_s": 3.0, "cell_w": 86, "cell_h": 43,
           "fight_end_timeout_s": 0.05, "stop_on_fight_end": True}
    cfg.update(over)
    fb = FakeBackend(frames)
    return botmod.Bot(fb, cfg, botmod.Assets(os.path.join(ROOT, "assets")), diag_dir="/tmp"), fb


def test_placement_clique_pret():
    b, fb = make_bot([FIX("06")])
    b.step()
    assert fb.clicks == [(846, 239, 1)]


def test_tour_complet_deux_sorts_puis_fin_du_tour():
    f06, f09, f11 = FIX("06"), FIX("09"), FIX("11")
    # 1 écran de départ + (écran de tour, confirmation) x2 + écran final pour « Fin du tour »
    b, fb = make_bot([f09, f11, f09, f11, f09])
    b.step()
    spell, coche, fin = (1640, 674), (1085, 658), (846, 239)
    c = [(x, y) for x, y, _ in fb.clicks]
    assert c[0] == spell and abs(c[1][0] - 975) < 8 and abs(c[1][1] - 808) < 8   # 1er sort : monstre le plus proche
    assert c[2] == coche
    assert c[3] == spell and abs(c[4][0] - 975) < 8 and c[5] == coche            # 2e sort
    assert c[6] == fin and len(c) == 7                                           # puis Fin du tour


def test_tour_adverse_ne_clique_pas():
    b, fb = make_bot([FIX("17")])
    b.step()
    assert fb.clicks == [] and b.state == "TOUR ADVERSE"


def test_fin_du_combat_arrete_le_robot():
    import time
    b, fb = make_bot([FIX("17"), np.zeros((1020, 1920, 3), np.uint8)])
    b.step()
    time.sleep(0.1)
    b.step()
    assert b.finished and fb.clicks == []


def test_phase1_clique_le_monstre():
    # l'écran de combat contient un chef de guerre : sans interface de combat, il serait cliqué
    img = FIX("09").copy()
    img[150:300, 0:1300] = 0                                     # efface la bande du haut (pas d'interface)
    b, fb = make_bot([img])
    b.step()
    assert len(fb.clicks) == 1 and fb.clicks[0][2] == 2
    assert abs(fb.clicks[0][0] - 1281) < 6 and abs(fb.clicks[0][1] - 757) < 6


def test_mode_creature_placement_et_tour_adverse():
    A = cv2.imread(os.path.join(ROOT, "tests", "fixtures", "creature_placement.png"))
    B = cv2.imread(os.path.join(ROOT, "tests", "fixtures", "creature_tour_adverse.png"))
    b, fb = make_bot([A])
    b.step()
    assert len(fb.clicks) == 1 and abs(fb.clicks[0][0] - 372) <= 2 and abs(fb.clicks[0][1] - 238) <= 2
    b, fb = make_bot([B])
    b.step()
    assert fb.clicks == [] and b.state == "TOUR ADVERSE"
