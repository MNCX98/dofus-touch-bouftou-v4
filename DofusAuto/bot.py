"""Machine à états : phase 1 (recherche de monstre) -> placement -> phase 2 (combat)."""
import os, time, logging
import cv2
from core import vision as V
from core.config import base_dir

log = logging.getLogger("dofusauto")


class Assets:
    def __init__(self, root=None):
        root = root or os.path.join(base_dir(), "assets")
        ui = lambda n: V.load_template(os.path.join(root, "ui", n + ".png"), n)
        self.pret = ui("pret")
        self.fin_actif = ui("fin_tour_actif")
        self.fin_gris = ui("fin_tour_gris")
        self.coche = ui("coche_valider")
        self.ban_jouer = ui("banniere_a_toi_de_jouer")
        self.ban_fin = ui("banniere_fin_du_tour")
        spells = V.load_folder(os.path.join(root, "spells"))
        self.spell = spells[0] if spells else None
        # tous les sous-dossiers de monstres (chef_de_guerre, pion, ...)
        mroot = os.path.join(root, "monsters")
        self.monsters = []
        if os.path.isdir(mroot):
            for d in sorted(os.listdir(mroot)):
                self.monsters += V.load_folder(os.path.join(mroot, d))


class Bot:
    def __init__(self, backend, cfg, assets, diag_dir=None):
        self.b, self.cfg, self.a = backend, cfg, assets
        self.diag_dir = diag_dir or os.path.join(base_dir(), "logs")
        self.state = "CARTE"
        self.in_fight = False
        self.last_fight_seen = 0.0
        self.last_click_t = 0.0        # dernier clic sur un monstre (carte)
        self.last_ready_t = 0.0
        self.last_end_turn_t = 0.0
        self.player_pos = None
        self.turns_played = 0
        self.finished = False           # vrai quand le robot s'arrête de lui-même

    # ---------- utilitaires ----------
    def _diag(self, frame, items, tag):
        if not self.cfg.get("save_diagnostics", True) or frame is None:
            return
        try:
            os.makedirs(self.diag_dir, exist_ok=True)
            name = "diag_%s_%s.png" % (time.strftime("%Y%m%d_%H%M%S"), tag)
            cv2.imwrite(os.path.join(self.diag_dir, name), V.annotate(frame, items))
        except Exception as e:                       # un problème de disque ne doit pas stopper le robot
            log.warning("diagnostic non enregistré : %s", e)

    def detect_ui(self, frame):
        bt = self.cfg["button_threshold"]
        res = {
            "pret": V.match(frame, self.a.pret, V.ui_band(frame.shape)),
            "fin_actif": V.match(frame, self.a.fin_actif, V.ui_band(frame.shape)),
            "fin_gris": V.match(frame, self.a.fin_gris, V.ui_band(frame.shape)),
        }
        res["pret_ok"] = res["pret"].score >= bt
        res["fin_actif_ok"] = res["fin_actif"].score >= bt
        res["fin_gris_ok"] = res["fin_gris"].score >= bt
        return res

    # ---------- une étape de la boucle ----------
    def step(self):
        frame = self.b.grab()
        if frame is None:
            log.warning("Fenêtre « %s » introuvable (visible, non réduite ?)", self.cfg["window_title_contains"])
            return
        if not getattr(self, "_size_logged", False):
            log.info("Fenêtre BlueStacks capturée : %dx%d pixels.", frame.shape[1], frame.shape[0])
            self._size_logged = True
        now = time.time()
        ui = self.detect_ui(frame)

        if ui["pret_ok"]:
            self._placement(frame, ui, now)
        elif ui["fin_actif_ok"]:
            self._mon_tour(frame, ui, now)
        elif ui["fin_gris_ok"]:
            self.in_fight, self.last_fight_seen = True, now
            self.state = "TOUR ADVERSE"
        elif self.in_fight:
            self.state = "COMBAT (interface non reconnue)"
            if now - self.last_fight_seen > self.cfg["fight_end_timeout_s"]:
                self._fin_combat(frame)
        else:
            self._recherche(frame, now)

    # ---------- phase 1 ----------
    def _recherche(self, frame, now):
        self.state = "RECHERCHE"
        if now - self.last_click_t < self.cfg["cooldown_after_click_s"]:
            return
        m = V.best_of(frame, self.a.monsters, V.map_area(frame.shape))
        if m.score >= self.cfg["threshold"]:
            log.info("Monstre « %s » trouvé (confiance %.2f) en (%d, %d) : clic x%d",
                     m.name, m.score, m.cx, m.cy, self.cfg["click_count"])
            self._diag(frame, [(m, "%s %.2f" % (m.name, m.score), (0, 255, 0))], "monstre")
            self.b.click(m.cx, m.cy, self.cfg["click_count"])
            self.last_click_t = now
        else:
            log.debug("Aucun monstre (meilleur score %.2f)", m.score)

    # ---------- placement ----------
    def _placement(self, frame, ui, now):
        self.in_fight, self.last_fight_seen = True, now
        self.state = "PLACEMENT"
        if now - self.last_ready_t < 3.0:
            return
        m = ui["pret"]
        log.info("Placement : clic sur « Prêt » (confiance %.2f)", m.score)
        self._diag(frame, [(m, "Pret %.2f" % m.score, (0, 255, 0))], "pret")
        self.b.click(m.cx, m.cy, 1)
        self.last_ready_t = now

    # ---------- phase 2 : mon tour ----------
    def _mon_tour(self, frame, ui, now):
        self.in_fight, self.last_fight_seen = True, now
        self.state = "MON TOUR"
        if now - self.last_end_turn_t < self.cfg["end_turn_cooldown_s"]:
            return
        self.turns_played += 1
        log.info("— Tour %d : à moi de jouer —", self.turns_played)
        self._jouer_tour(frame)

    def _jouer_tour(self, frame):
        cfg = self.cfg
        cw, ch = cfg["cell_w"], cfg["cell_h"]
        ring = V.find_player_ring(frame, near=self.player_pos)
        if ring is not None:
            self.player_pos = (ring[0], ring[1])
        enemies = V.find_enemy_rings(frame)
        diag = []
        if self.player_pos:
            diag.append(((self.player_pos[0] - 30, self.player_pos[1] - 15, 60, 30), "moi", (0, 0, 255)))
        for e in enemies:
            diag.append(((e[0] - 30, e[1] - 12, 60, 24), "ennemi", (255, 128, 0)))

        if not self.player_pos:
            log.warning("Mon personnage (anneau rouge) n'est pas reconnu : je ne peux pas choisir le plus proche.")
        if not enemies:
            log.warning("Aucun ennemi détecté : je termine simplement le tour.")
        self._diag(frame, diag, "tour%d" % self.turns_played)

        if enemies and self.player_pos:
            enemies = V.sort_by_distance(self.player_pos, enemies, cw, ch)
        elif enemies:
            enemies = sorted(enemies, key=lambda e: e[1])

        for i in range(cfg["spells_per_turn"] if enemies else 0):
            if self.b.stopped():
                return
            if i > 0:                                  # nouvelle photo : l'ennemi a pu mourir
                frame = self.b.grab()
                if frame is None:
                    break
                fresh = V.find_enemy_rings(frame)
                if fresh and self.player_pos:
                    enemies = V.sort_by_distance(self.player_pos, fresh, cw, ch)
                elif not fresh:
                    log.info("Plus aucun ennemi visible : j'arrête les sorts.")
                    break
            if not self._lancer_sort(frame, enemies[0], i + 1):
                break
        self._fin_de_tour()

    def _lancer_sort(self, frame, target, n):
        cfg = self.cfg
        sp = V.match(frame, self.a.spell, V.spell_area(frame.shape)) if self.a.spell is not None else None
        if sp is None or sp.score < cfg["threshold"]:
            log.warning("Sort %d : icône de Coagulation non reconnue (confiance %.2f) — "
                        "plus de PA ou barre de sorts différente.", n, sp.score if sp else 0.0)
            return False
        log.info("Sort %d : clic sur Coagulation (%.2f), puis sur l'ennemi le plus proche en (%d, %d)",
                 n, sp.score, target[0], target[1])
        self.b.click(sp.cx, sp.cy, 1)
        self.b.sleep(cfg["spell_wait_s"])
        self.b.click(target[0], target[1], 1)
        self.b.sleep(cfg["target_wait_s"])
        f2 = self.b.grab()
        if f2 is not None:
            ck = V.match(f2, self.a.coche, V.map_area(f2.shape))
            if ck.score >= cfg["threshold"]:
                log.info("Confirmation du sort : clic sur la coche verte (%.2f)", ck.score)
                self._diag(f2, [(ck, "coche %.2f" % ck.score, (0, 255, 0))], "coche")
                self.b.click(ck.cx, ck.cy, 1)
            else:
                log.info("Pas de fenêtre de confirmation (%.2f) : le sort est peut-être parti directement.", ck.score)
                self._diag(f2, [], "sans_coche")
        self.b.sleep(cfg["cast_wait_s"])
        return True

    def _fin_de_tour(self):
        frame = self.b.grab()
        if frame is None:
            return
        m = V.match(frame, self.a.fin_actif, V.ui_band(frame.shape))
        if m.score >= self.cfg["button_threshold"]:
            log.info("Clic sur « Fin du tour » (%.2f)", m.score)
            self.b.click(m.cx, m.cy, 1)
        else:
            log.info("Bouton « Fin du tour » plus actif (%.2f) : rien à faire.", m.score)
        self.last_end_turn_t = time.time()

    # ---------- fin du combat ----------
    def _fin_combat(self, frame):
        log.info("Interface de combat disparue depuis %.0f s : le combat semble terminé.", self.cfg["fight_end_timeout_s"])
        try:
            os.makedirs(self.diag_dir, exist_ok=True)
            p = os.path.join(self.diag_dir, "fin_combat_%s.png" % time.strftime("%Y%m%d_%H%M%S"))
            cv2.imwrite(p, frame)
            log.info("Capture enregistrée : %s (envoie-la moi pour la phase 6)", p)
        except Exception:
            pass
        self.in_fight = False
        if self.cfg.get("stop_on_fight_end", True):
            log.info("Arrêt : la gestion de la fin de combat (phase 6) n'est pas encore disponible.")
            self.finished = True

    def run(self):
        log.info("Robot démarré. Arrêt : F12 ou bouton « Arrêter ».")
        while not self.b.stopped() and not self.finished:
            t0 = time.time()
            try:
                self.step()
            except Exception:
                log.exception("Erreur pendant une étape (le robot continue)")
            self.b.sleep(max(0.05, self.cfg["scan_interval_ms"] / 1000.0 - (time.time() - t0)))
        log.info("Robot arrêté.")
