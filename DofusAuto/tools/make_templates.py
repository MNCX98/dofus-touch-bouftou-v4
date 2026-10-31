"""Découpe les images de référence (boutons, bandeaux, coche) à partir des captures
complètes de tests/fixtures. À relancer seulement si l'interface du jeu change."""
import os, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
OUT = os.path.join(ROOT, "assets", "ui")
CROPS = {
    "pret":                    ("06", (778, 218, 136, 42)),
    "fin_tour_actif":          ("09", (778, 218, 136, 42)),
    "fin_tour_gris":           ("17", (697, 218, 136, 42)),
    "banniere_a_toi_de_jouer": ("09", (640, 500, 640, 75)),
    "banniere_fin_du_tour":    ("17", (705, 500, 505, 75)),
    "coche_valider":           ("11", (1056, 631, 58, 54)),
}
os.makedirs(OUT, exist_ok=True)
for name, (src, (x, y, w, h)) in CROPS.items():
    im = cv2.imread(os.path.join(FIX, src + ".png"))
    cv2.imwrite(os.path.join(OUT, name + ".png"), im[y:y + h, x:x + w])
    print("ok", name)
