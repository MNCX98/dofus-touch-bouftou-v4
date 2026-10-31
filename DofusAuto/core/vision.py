"""Reconnaissance d'images (OpenCV). Aucune dépendance à Windows : testable partout."""
import os, unicodedata
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class Match:
    score: float
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    name: str = ""

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2


@dataclass
class Template:
    name: str
    image: np.ndarray
    mask: np.ndarray = None


def load_template(path, name=None):
    data = np.fromfile(path, dtype=np.uint8)           # gère les accents dans les chemins
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("image illisible : " + path)
    name = name or os.path.splitext(os.path.basename(path))[0]
    mask = None
    if img.ndim == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3]
        if alpha.min() < 255:
            mask = cv2.merge([alpha, alpha, alpha])
        img = img[:, :, :3]
    elif img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return Template(name, np.ascontiguousarray(img), mask)


def load_folder(folder):
    out = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(".png"):
                out.append(load_template(os.path.join(folder, f)))
    return out


def match(frame, tpl, region=None):
    """Meilleure position du modèle dans l'image. region = (x0, y0, x1, y1) en pixels."""
    ox = oy = 0
    sub = frame
    if region is not None:
        x0, y0, x1, y1 = region
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
        sub = frame[y0:y1, x0:x1]
        ox, oy = x0, y0
    th, tw = tpl.image.shape[:2]
    if sub.shape[0] < th or sub.shape[1] < tw:
        return Match(0.0, name=tpl.name)
    if tpl.mask is not None:
        res = cv2.matchTemplate(sub, tpl.image, cv2.TM_CCOEFF_NORMED, mask=tpl.mask)
    else:
        res = cv2.matchTemplate(sub, tpl.image, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    _, mx, _, loc = cv2.minMaxLoc(res)
    return Match(float(min(mx, 1.0)), loc[0] + ox, loc[1] + oy, tw, th, tpl.name)


def match_fast(frame, tpl, region=None, scale=0.5, margin=10, coarse_min=0.55):
    """Recherche en deux temps : image réduite (rapide) puis affinage à pleine taille.
    Même résultat que match() mais ~15 fois plus rapide pour les modèles à masque."""
    ox = oy = 0
    sub = frame
    if region is not None:
        x0, y0, x1, y1 = region
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
        sub = frame[y0:y1, x0:x1]
        ox, oy = x0, y0
    th, tw = tpl.image.shape[:2]
    if sub.shape[0] < th or sub.shape[1] < tw:
        return Match(0.0, name=tpl.name)
    small = cv2.resize(sub, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    t_img = cv2.resize(tpl.image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    t_mask = None if tpl.mask is None else cv2.resize(tpl.mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if small.shape[0] < t_img.shape[0] or small.shape[1] < t_img.shape[1]:
        return match(frame, tpl, region)
    if t_mask is not None:
        res = cv2.matchTemplate(small, t_img, cv2.TM_CCOEFF_NORMED, mask=t_mask)
    else:
        res = cv2.matchTemplate(small, t_img, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    _, mx, _, loc = cv2.minMaxLoc(res)
    if mx < coarse_min:
        return Match(float(max(mx, 0.0)), 0, 0, tw, th, tpl.name)
    cx, cy = int(loc[0] / scale), int(loc[1] / scale)
    rx0, ry0 = max(0, cx - margin), max(0, cy - margin)
    rx1, ry1 = min(sub.shape[1], cx + tw + margin), min(sub.shape[0], cy + th + margin)
    fine = match(sub, tpl, (rx0, ry0, rx1, ry1))
    return Match(fine.score, fine.x + ox, fine.y + oy, tw, th, tpl.name)


def best_of(frame, templates, region=None, fast=True):
    best = Match(0.0)
    for t in templates:
        m = match_fast(frame, t, region) if fast else match(frame, t, region)
        if m.score > best.score:
            best = m
    return best


# ---------- zones de l'écran (relatives à la taille de la fenêtre) ----------
def game_left(w):
    """Bord gauche du jeu : la grande fenêtre (1920) a un panneau de pub de 320 px à gauche."""
    return 320 if w >= 1800 else 0


def map_area(shape):
    """Zone de la carte (hors panneaux latéraux)."""
    h, w = shape[:2]
    return (game_left(w), 0, max(0, w - 300), h)


def ui_band(shape):
    """Bande du haut où se trouvent Prêt / Fin du tour."""
    h, w = shape[:2]
    return (0, 100, min(w, 1300), min(h, 330))


def spell_area(shape):
    """Zone de la barre de sorts (à droite)."""
    h, w = shape[:2]
    return (max(0, w - 440), 90, w, max(0, h - 150))


def _combat_roi(shape):
    """Zone où chercher les anneaux : la carte, sans la chronologie et les boutons orange en haut à gauche."""
    h, w = shape[:2]
    gl = game_left(w)
    roi = np.zeros((h, w), np.uint8)
    x0, y0, x1, y1 = map_area(shape)
    roi[y0:y1, x0:x1] = 1
    roi[0:330, gl:gl + 620] = 0
    roi[0:600, gl:gl + 125] = 0
    return roi


def _components(mask, min_area, roi):
    mask = mask * roi
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 9)))
    n, _, st, cen = cv2.connectedComponentsWithStats(mask)
    out = []
    for i in range(1, n):
        if st[i][4] >= min_area:
            out.append((int(cen[i][0]), int(cen[i][1]), int(st[i][2]), int(st[i][3]), int(st[i][4])))
    return out


def find_enemy_rings(frame):
    """Anneaux bleus (ennemis). Retourne [(cx, cy, w, h, aire)]. Ignore les cases violettes de portée."""
    rgb = frame[:, :, ::-1].astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    m = ((b - r > 110) & (b > 150) & (g > 70) & (g < 200) & (b - g > 40) & (g - r > 70)).astype(np.uint8) * 255
    return [c for c in _components(m, 150, _combat_roi(frame.shape)) if 40 <= c[2] <= 90 and 12 <= c[3] <= 45]


def find_player_ring(frame, near=None):
    """Anneau rouge du joueur. Si `near` est donné, garde le candidat le plus proche."""
    rgb = frame[:, :, ::-1].astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    m = ((r > 130) & (g < 75) & (b < 65) & (r - g > 90)).astype(np.uint8) * 255
    cands = [c for c in _components(m, 150, _combat_roi(frame.shape)) if 22 <= c[2] <= 80 and 14 <= c[3] <= 50]
    if not cands:
        return None
    if near is not None:
        cands.sort(key=lambda c: (c[0] - near[0]) ** 2 + (c[1] - near[1]) ** 2)
        c = cands[0]
        return c if (c[0] - near[0]) ** 2 + (c[1] - near[1]) ** 2 < 80 ** 2 else None
    cands.sort(key=lambda c: -c[4])
    return cands[0]


def cell_distance(a, b, cell_w=86, cell_h=43):
    """Distance en cases (vue isométrique 2:1) entre deux points de l'écran."""
    return max(abs(a[0] - b[0]) / (cell_w / 2.0), abs(a[1] - b[1]) / (cell_h / 2.0))


def sort_by_distance(player, targets, cell_w=86, cell_h=43):
    return sorted(targets, key=lambda t: cell_distance(player, (t[0], t[1]), cell_w, cell_h))


def annotate(frame, items):
    """items = [(Match ou (x,y,w,h), label, (b,g,r))] -> copie annotée."""
    out = frame.copy()
    for box, label, color in items:
        if isinstance(box, Match):
            x, y, w, h = box.x, box.y, box.w, box.h
        else:
            x, y, w, h = box
        label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 3)
        cv2.putText(out, label, (x, max(15, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    return out
