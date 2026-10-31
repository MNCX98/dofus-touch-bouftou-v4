"""Outils de test : capture, séquence + planche-contact, test de détection sans clic."""
import os, time, logging
import cv2
import numpy as np
from . import vision as V
from .config import base_dir

log = logging.getLogger("dofusauto")


def _imwrite(path, img, params=None):
    ok, buf = cv2.imencode(os.path.splitext(path)[1], img, params or [])
    if ok:
        buf.tofile(path)
    return ok


def captures_dir():
    d = os.path.join(base_dir(), "captures")
    os.makedirs(d, exist_ok=True)
    return d


def logs_dir():
    d = os.path.join(base_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


def save_capture(frame):
    p = os.path.join(captures_dir(), "capture_%s.png" % time.strftime("%Y%m%d_%H%M%S"))
    _imwrite(p, frame)
    log.info("Capture enregistrée : %s (taille %dx%d)", p, frame.shape[1], frame.shape[0])
    return p


def contact_sheet(frames, path, cols=7, thumb_w=274):
    """Planche-contact numérotée (comme planche.jpg)."""
    if not frames:
        return None
    h0, w0 = frames[0].shape[:2]
    tw, th = thumb_w, int(thumb_w * h0 / w0)
    rows = (len(frames) + cols - 1) // cols
    sheet = np.full((rows * th, cols * tw, 3), 30, np.uint8)
    for i, f in enumerate(frames):
        t = cv2.resize(f, (tw, th), interpolation=cv2.INTER_AREA)
        cv2.putText(t, str(i + 1), (4, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(t, str(i + 1), (4, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 1, cv2.LINE_AA)
        r, c = divmod(i, cols)
        sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = t
    _imwrite(path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return path


def record_sequence(backend, seconds, stopped=lambda: False):
    folder = os.path.join(captures_dir(), "sequence_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(folder, exist_ok=True)
    log.info("Séquence : 1 capture par seconde pendant %d s -> %s", seconds, folder)
    frames, t0 = [], time.time()
    for i in range(int(seconds)):
        if stopped():
            break
        f = backend.grab()
        if f is not None:
            frames.append(f)
            _imwrite(os.path.join(folder, "%02d.png" % (i + 1)), f)
        wait = t0 + i + 1 - time.time()
        if wait > 0:
            backend.sleep(wait)
    sheet = contact_sheet(frames, os.path.join(folder, "planche.jpg"))
    log.info("Séquence terminée : %d images. Planche : %s", len(frames), sheet)
    return folder


def detect_all(frame, assets, cfg):
    """Teste toute la reconnaissance SANS cliquer. Retourne (image annotée, lignes de texte)."""
    items, lines = [], []
    bt, th = cfg["button_threshold"], cfg["threshold"]
    for label, tpl, thr, region, col in (
        ("Prêt", assets.pret, bt, V.ui_band(frame.shape), (0, 200, 0)),
        ("Fin du tour (actif)", assets.fin_actif, bt, V.ui_band(frame.shape), (0, 200, 0)),
        ("Fin du tour (grisé)", assets.fin_gris, bt, V.ui_band(frame.shape), (160, 160, 160)),
        ("Bandeau À toi de jouer", assets.ban_jouer, th, None, (0, 200, 200)),
        ("Bandeau Fin du tour", assets.ban_fin, th, None, (0, 200, 200)),
        ("Coche de confirmation", assets.coche, th, None, (0, 200, 0)),
    ):
        m = V.match(frame, tpl, region)
        ok = m.score >= thr
        lines.append("%-24s %s  confiance %.2f (seuil %.2f)" % (label, "TROUVÉ " if ok else "absent ", m.score, thr))
        if ok:
            items.append((m, "%s %.2f" % (label, m.score), col))
    if assets.spell is not None:
        m = V.match(frame, assets.spell, V.spell_area(frame.shape))
        ok = m.score >= th
        lines.append("%-24s %s  confiance %.2f" % ("Sort Coagulation", "TROUVÉ " if ok else "absent ", m.score))
        if ok:
            items.append((m, "Coagulation %.2f" % m.score, (0, 200, 0)))
    mon = V.best_of(frame, assets.monsters, V.map_area(frame.shape))
    ok = mon.score >= th
    lines.append("%-24s %s  confiance %.2f (%s)" % ("Monstre (carte)", "TROUVÉ " if ok else "absent ", mon.score, mon.name))
    if ok:
        items.append((mon, "%s %.2f" % (mon.name, mon.score), (0, 255, 0)))
    player = V.find_player_ring(frame)
    enemies = V.find_enemy_rings(frame)
    lines.append("Combat : joueur %s, %d ennemi(s) vu(s)" % ("vu" if player else "non vu", len(enemies)))
    if player:
        items.append(((player[0] - 30, player[1] - 15, 60, 30), "moi", (0, 0, 255)))
    if player and enemies:
        order = V.sort_by_distance(player[:2], enemies, cfg["cell_w"], cfg["cell_h"])
        for k, e in enumerate(order):
            d = V.cell_distance(player[:2], e[:2], cfg["cell_w"], cfg["cell_h"])
            items.append(((e[0] - 30, e[1] - 12, 60, 24), "%s %.1f cases" % ("CIBLE" if k == 0 else "ennemi", d),
                          (0, 255, 255) if k == 0 else (255, 128, 0)))
        lines.append("Cible choisie (la plus proche) : (%d, %d) à %.1f cases" % (
            order[0][0], order[0][1], V.cell_distance(player[:2], order[0][:2], cfg["cell_w"], cfg["cell_h"])))
    elif enemies:
        for e in enemies:
            items.append(((e[0] - 30, e[1] - 12, 60, 24), "ennemi", (255, 128, 0)))
    return V.annotate(frame, items), lines
