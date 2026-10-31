import os, sys, time, logging, threading
import cv2
from PySide6.QtCore import Qt, QObject, Signal, QTimer, QThread
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QPlainTextEdit, QLabel, QDoubleSpinBox, QSpinBox, QGridLayout)
from core import config as cfgmod, diagnostics as diag, winapi
from core.backend import WindowBackend
import bot as botmod

VERSION = "0.4"
log = logging.getLogger("dofusauto")


class _LogBridge(logging.Handler, QObject):
    message = Signal(str)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, record):
        self.message.emit(self.format(record))


class Worker(QThread):
    """Exécute une tâche (robot, séquence, test…) hors du fil de l'interface."""
    done = Signal()
    image = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.fn()
        except Exception:
            log.exception("Erreur")
        self.done.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DofusAuto %s" % VERSION)
        self.resize(900, 760)
        self.cfg = cfgmod.load()
        self.stop_flag = False
        self.worker = None
        self.assets = None
        self._pending = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        self.status = QLabel("Prêt.  Arrêt d'urgence : F12")
        self.status.setStyleSheet("font-weight:bold; padding:4px;")
        root.addWidget(self.status)

        grid = QGridLayout()
        self.btn = {}
        defs = [("capture", "Enregistrer une capture", self.on_capture),
                ("test", "Tester la détection (sans clic)", self.on_test),
                ("sequence", "Enregistrer une séquence", self.on_sequence),
                ("start", "Démarrer", self.on_start),
                ("stop", "Arrêter", self.on_stop),
                ("reload", "Recharger les images", self.on_reload),
                ("folder", "Dossier des captures", self.on_folder)]
        for i, (key, text, fn) in enumerate(defs):
            b = QPushButton(text)
            b.clicked.connect(fn)
            self.btn[key] = b
            grid.addWidget(b, i // 4, i % 4)
        self.btn["stop"].setEnabled(False)
        root.addLayout(grid)

        opt = QHBoxLayout()
        opt.addWidget(QLabel("Seuil de confiance :"))
        self.sp_thr = QDoubleSpinBox(); self.sp_thr.setRange(0.5, 0.99); self.sp_thr.setSingleStep(0.01)
        self.sp_thr.setValue(float(self.cfg["threshold"])); opt.addWidget(self.sp_thr)
        opt.addWidget(QLabel("Clics :"))
        self.sp_clicks = QSpinBox(); self.sp_clicks.setRange(1, 3); self.sp_clicks.setValue(int(self.cfg["click_count"]))
        opt.addWidget(self.sp_clicks)
        opt.addWidget(QLabel("Sorts par tour :"))
        self.sp_spells = QSpinBox(); self.sp_spells.setRange(1, 6); self.sp_spells.setValue(int(self.cfg["spells_per_turn"]))
        opt.addWidget(self.sp_spells)
        opt.addStretch()
        root.addLayout(opt)

        self.preview = QLabel("Aperçu : lance « Tester la détection » pour voir ce que le programme voit.")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(300)
        self.preview.setStyleSheet("background:#222; color:#aaa;")
        root.addWidget(self.preview, 3)

        self.logbox = QPlainTextEdit(); self.logbox.setReadOnly(True)
        root.addWidget(self.logbox, 2)

        self.bridge = _LogBridge()
        self.bridge.message.connect(self.logbox.appendPlainText)
        log.addHandler(self.bridge)
        log.setLevel(logging.INFO)
        try:
            fh = logging.FileHandler(os.path.join(diag.logs_dir(), "dofusauto.log"), encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(fh)
        except OSError:
            pass

        self.f12 = QTimer(self); self.f12.timeout.connect(self._poll_f12); self.f12.start(100)
        self.on_reload()
        log.info("DofusAuto %s — prêt.", VERSION)

    # ---------- utilitaires ----------
    def _apply_settings(self):
        self.cfg["threshold"] = round(self.sp_thr.value(), 2)
        self.cfg["click_count"] = self.sp_clicks.value()
        self.cfg["spells_per_turn"] = self.sp_spells.value()
        try:
            cfgmod.save(self.cfg)
        except OSError:
            pass

    def _poll_f12(self):
        if self.worker and self.worker.isRunning() and winapi.key_pressed(winapi.VK_F12):
            self.stop_flag = True

    def _backend(self):
        return WindowBackend(self.cfg, lambda: self.stop_flag)

    def _busy(self, busy, label=None):
        for k in ("capture", "test", "sequence", "start", "reload"):
            self.btn[k].setEnabled(not busy)
        self.btn["stop"].setEnabled(busy)
        self.status.setText(label or "Prêt.  Arrêt d'urgence : F12")

    def _run(self, fn, label):
        if self.worker and self.worker.isRunning():
            return
        self._apply_settings()
        self.stop_flag = False
        self._busy(True, label)
        self.worker = Worker(fn)
        self.worker.done.connect(self._worker_done)      # méthode de la fenêtre : exécutée dans le fil de l'interface
        self.worker.start()

    def _worker_done(self):
        self._busy(False)
        if self._pending is not None:
            self.show_image(self._pending)
            self._pending = None

    def show_image(self, frame):
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qi = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        pm = QPixmap.fromImage(qi).scaled(self.preview.width(), self.preview.height(),
                                          Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)

    # ---------- boutons ----------
    def on_reload(self):
        try:
            self.assets = botmod.Assets()
            log.info("Images chargées : %d monstre(s), sort %s.", len(self.assets.monsters),
                     "Coagulation" if self.assets.spell else "(aucun)")
        except Exception as e:
            log.error("Impossible de charger les images : %s", e)

    def on_capture(self):
        def job():
            f = self._backend().grab()
            if f is None:
                log.warning("Fenêtre « %s » introuvable.", self.cfg["window_title_contains"])
                return
            diag.save_capture(f)
        self._run(job, "Capture…")

    def on_test(self):
        def job():
            f = self._backend().grab()
            if f is None:
                log.warning("Fenêtre « %s » introuvable.", self.cfg["window_title_contains"])
                return
            img, lines = diag.detect_all(f, self.assets, self.cfg)
            for l in lines:
                log.info(l)
            p = os.path.join(diag.logs_dir(), "test_%s.png" % time.strftime("%Y%m%d_%H%M%S"))
            diag._imwrite(p, img)
            log.info("Image annotée : %s", p)
            self._pending = img
        self._pending = None
        self._run(job, "Test de détection…")

    def on_sequence(self):
        be = self._backend()
        self._run(lambda: diag.record_sequence(be, self.cfg["sequence_seconds"], be.stopped), "Séquence en cours…")

    def on_start(self):
        be = self._backend()
        robot = botmod.Bot(be, self.cfg, self.assets)
        self.robot = robot
        self._run(robot.run, "ROBOT ACTIF — F12 pour arrêter")

    def on_stop(self):
        self.stop_flag = True
        log.info("Arrêt demandé…")

    def on_folder(self):
        d = diag.captures_dir()
        if winapi.IS_WINDOWS:
            os.startfile(d)
        else:
            log.info("Dossier : %s", d)

    def closeEvent(self, e):
        self.stop_flag = True
        if self.worker:
            self.worker.wait(3000)
        super().closeEvent(e)


def run():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
