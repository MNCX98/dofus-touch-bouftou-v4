import os, cv2, pytest
from core import vision as V

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = lambda n: cv2.imread(os.path.join(ROOT, "tests", "fixtures", n + ".png"))
UI = lambda n: V.load_template(os.path.join(ROOT, "assets", "ui", n + ".png"), n)
BT = 0.95


@pytest.fixture(scope="module")
def screens():
    return {n: FIX(n) for n in ("06", "09", "11", "17")}


def test_pret_seulement_au_placement(screens):
    t = UI("pret")
    assert V.match(screens["06"], t).score >= BT
    for n in ("09", "11", "17"):
        assert V.match(screens[n], t).score < BT       # le bouton Fin du tour ne doit PAS passer pour Prêt


def test_fin_du_tour_actif_seulement_a_mon_tour(screens):
    t = UI("fin_tour_actif")
    for n in ("09", "11"):
        m = V.match(screens[n], t)
        assert m.score >= BT and abs(m.cx - 846) <= 2 and abs(m.cy - 239) <= 2
    for n in ("06", "17"):
        assert V.match(screens[n], t).score < BT


def test_bouton_gris_tour_adverse(screens):
    t = UI("fin_tour_gris")
    assert V.match(screens["17"], t).score >= BT
    for n in ("06", "09", "11"):
        assert V.match(screens[n], t).score < BT


def test_bandeaux_et_coche(screens):
    assert V.match(screens["09"], UI("banniere_a_toi_de_jouer")).score >= 0.8
    assert V.match(screens["17"], UI("banniere_a_toi_de_jouer")).score < 0.8
    assert V.match(screens["17"], UI("banniere_fin_du_tour")).score >= 0.8
    assert V.match(screens["09"], UI("banniere_fin_du_tour")).score < 0.8
    ck = V.match(screens["11"], UI("coche_valider"))
    assert ck.score >= 0.8 and (ck.cx, ck.cy) == (1085, 658)
    for n in ("06", "09", "17"):
        assert V.match(screens[n], UI("coche_valider")).score < 0.8


def test_sort_coagulation(screens):
    sp = V.load_template(os.path.join(ROOT, "assets", "spells", "coagulation.png"))
    for n in ("09", "11", "17"):
        m = V.match(screens[n], sp, (1500, 180, 1900, 760))
        assert m.score >= 0.8 and abs(m.cx - 1640) <= 2 and abs(m.cy - 674) <= 2
    assert V.match(screens["06"], sp, (1500, 180, 1900, 760)).score < 0.8


def test_anneaux_ennemis_et_joueur(screens):
    rings = V.find_enemy_rings(screens["09"])
    assert len(rings) == 4
    p = V.find_player_ring(screens["09"])
    assert p is not None and abs(p[0] - 851) < 8 and abs(p[1] - 781) < 8
    # avec les cases violettes de portée affichées, on ne prend pas de fausses cibles
    assert all(c[1] > 600 for c in V.find_enemy_rings(screens["11"]))
    assert V.find_player_ring(screens["11"], near=p[:2]) is not None


def test_ennemi_le_plus_proche(screens):
    p = V.find_player_ring(screens["09"])
    order = V.sort_by_distance(p[:2], V.find_enemy_rings(screens["09"]))
    assert abs(order[0][0] - 975) < 8 and abs(order[0][1] - 808) < 8


def test_monstre_carte_avec_masque(screens):
    mons = V.load_folder(os.path.join(ROOT, "assets", "monsters", "chef_de_guerre"))
    assert len(mons) == 4 and all(m.mask is not None for m in mons)
    m = V.best_of(screens["09"], mons, V.map_area(screens["09"].shape))
    assert m.score >= 0.9 and abs(m.x - 1246) <= 3 and abs(m.y - 735) <= 3


# ---------- mode créature (fenêtre plus petite, sans panneau de pub) ----------
@pytest.fixture(scope="module")
def creature():
    return {"A": FIX("creature_placement"), "B": FIX("creature_tour_adverse")}


def test_creature_boutons_et_sort(creature):
    A, B = creature["A"], creature["B"]
    assert V.match(A, UI("pret"), V.ui_band(A.shape)).score >= BT
    assert V.match(B, UI("pret"), V.ui_band(B.shape)).score < BT
    assert V.match(B, UI("fin_tour_gris"), V.ui_band(B.shape)).score >= BT
    assert V.match(B, UI("fin_tour_actif"), V.ui_band(B.shape)).score < BT
    sp = V.load_template(os.path.join(ROOT, "assets", "spells", "coagulation.png"))
    m = V.match(B, sp, V.spell_area(B.shape))
    assert m.score >= 0.8 and abs(m.cx - 1320) <= 2 and abs(m.cy - 629) <= 2
    assert V.match(A, sp, V.spell_area(A.shape)).score < 0.8


def test_creature_anneaux_et_plus_proche(creature):
    B = creature["B"]
    rings = V.find_enemy_rings(B)
    assert len(rings) == 2
    p = V.find_player_ring(B)
    assert p is not None and abs(p[0] - 529) < 8 and abs(p[1] - 781) < 8
    order = V.sort_by_distance(p[:2], rings)
    assert abs(order[0][0] - 441) < 8 and abs(order[0][1] - 738) < 8        # pion de gauche : le plus proche


def test_creature_pion_sur_la_carte(creature, screens):
    pion = V.load_folder(os.path.join(ROOT, "assets", "monsters", "pion"))
    assert len(pion) == 2 and all(m.mask is not None for m in pion)      # normal + miroir
    for img, spots in ((creature["B"], [(572, 660), (442, 727)]), (creature["A"], [(578, 703), (451, 770)])):
        for sx, sy in spots:                                               # chaque pion est reconnu...
            m = V.best_of(img, pion, (sx - 50, sy - 50, sx + 50, sy + 50), fast=False)
            assert m.score >= 0.8 and abs(m.cx - sx) < 12 and abs(m.cy - sy) < 12, (sx, sy, m)
        # ...et rien d'autre n'est pris pour un pion ailleurs sur la carte
        img2 = img.copy()
        for sx, sy in spots:
            img2[sy - 40:sy + 40, sx - 40:sx + 40] = 128
        assert V.best_of(img2, pion, V.map_area(img.shape)).score < 0.8
