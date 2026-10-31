import json, os, sys

def base_dir():
    """Dossier de l'application (à côté du .exe, ou racine du projet en développement)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "window_title_contains": "BlueStacks",
    "threshold": 0.8,              # monstres sur la carte, bandeaux, coche, sort
    "button_threshold": 0.95,      # boutons Prêt / Fin du tour (très stricts : ils se ressemblent)
    "scan_interval_ms": 500,
    "cooldown_after_click_s": 4.0,
    "click_count": 2,
    "click_interval_ms": 200,
    "sequence_seconds": 40,
    "save_diagnostics": True,
    # --- phase 2 : combat ---
    "spells_per_turn": 2,
    "spell_wait_s": 0.6,           # pause après le clic sur le sort
    "target_wait_s": 0.9,          # pause après le clic sur la cible (attente de la coche)
    "cast_wait_s": 1.2,            # pause après le lancement (animation)
    "end_turn_cooldown_s": 3.0,
    "cell_w": 86,                  # largeur d'une case en pixels (calcul des distances)
    "cell_h": 43,
    "fight_end_timeout_s": 10.0,   # plus d'interface de combat pendant ce temps = combat terminé
    "stop_on_fight_end": True,     # la phase 6 (fin de combat) n'existe pas encore
}

def config_path():
    return os.path.join(base_dir(), "config.json")

def load():
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg

def save(cfg):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
