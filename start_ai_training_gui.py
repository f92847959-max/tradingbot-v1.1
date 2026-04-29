"""GoldBot AI Training Starter - Tkinter GUI.

Native Tk-App, keine externen Abhaengigkeiten. Startet `start_ai_training.py`
mit den eingestellten Argumenten als Subprozess und zeigt den Live-Output.

Layout:
    - Tab "Essentiell": Target, Timeframes, Primary, Count, CSV-Modus, Start/Stop
    - Tab "Advanced":   alle weiteren Argumente von start_ai_training.py
    - unten:            Live-Log + Statuszeile + zusammengebauter Befehl

Konfiguration wird in ~/.goldbot_starter.json gespeichert und beim Start geladen.

Aufruf:
    python start_ai_training_gui.py
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable


# Konstanten
def _find_repo_root(start: Path) -> Path:
    """Walk up parents until we find the GoldBot repo (scripts/train_models.py)."""
    cur = start.resolve()
    for _ in range(8):
        if (cur / "scripts" / "train_models.py").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.resolve()


GUI_DIR = Path(__file__).resolve().parent
ROOT = _find_repo_root(GUI_DIR)
TRAINING_SCRIPT = ROOT / "start_ai_training.py"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
VENV_PYTHON_NIX = ROOT / ".venv" / "bin" / "python"
CONFIG_FILE = Path.home() / ".goldbot_starter.json"

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
TARGETS = ["core", "exit", "all"]

DEFAULTS: dict[str, Any] = {
    "target": "all",
    "timeframes": ["5m", "15m", "1h"],
    "primary": "5m",
    "count": 0,
    "min_candles": 0,
    "output": "ai_engine/saved_models",
    "save_csv_dir": "data",
    "min_data_months": 6,
    "max_holding": 15,
    "tp_atr_mult": 2.0,
    "sl_atr_mult": 1.5,
    "no_dynamic_atr": False,
    "dry_run": False,
    "use_csv_if_present": True,
    "exit_csv": "data/exit_ai_snapshots.csv",
    "exit_required": False,
    "exit_min_samples": 500,
    "exit_purge_gap": 12,
    "exit_min_train_samples": 120,
    "exit_min_test_samples": 40,
    "loop_iterations": 1,
    "loop_interval_min": 0.0,
    "loop_refetch": False,
    "loop_refetch_years": 2,
    "rebuild_exit_snapshots": False,
    "snapshot_timeframe": "5m",
    "snapshot_stride": 4,
}


# Persistenz
def load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            return {**DEFAULTS, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_config(cfg: dict[str, Any]) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"warn: konnte config nicht speichern: {exc}")


def repo_python() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    if VENV_PYTHON_NIX.exists():
        return str(VENV_PYTHON_NIX)
    return sys.executable


# Befehlskonstruktion
def build_command(cfg: dict[str, Any]) -> list[str]:
    cmd: list[str] = [
        repo_python(),
        str(TRAINING_SCRIPT),
        "--target", cfg["target"],
        "--timeframes", ",".join(cfg["timeframes"]),
        "--primary-timeframe", cfg["primary"],
        "--output", cfg["output"],
        "--save-csv-dir", cfg["save_csv_dir"],
        "--min-data-months", str(cfg["min_data_months"]),
        "--max-holding", str(cfg["max_holding"]),
        "--tp-atr-mult", str(cfg["tp_atr_mult"]),
        "--sl-atr-mult", str(cfg["sl_atr_mult"]),
    ]
    if int(cfg["count"]) > 0:
        cmd += ["--count", str(cfg["count"])]
    if int(cfg["min_candles"]) > 0:
        cmd += ["--min-candles", str(cfg["min_candles"])]
    if cfg["use_csv_if_present"]:
        cmd.append("--use-csv-if-present")
    if cfg["target"] != "core":
        cmd += [
            "--exit-csv", cfg["exit_csv"],
            "--exit-min-samples", str(cfg["exit_min_samples"]),
            "--exit-purge-gap", str(cfg["exit_purge_gap"]),
            "--exit-min-train-samples", str(cfg["exit_min_train_samples"]),
            "--exit-min-test-samples", str(cfg["exit_min_test_samples"]),
        ]
        if cfg["target"] == "all" and cfg["exit_required"]:
            cmd.append("--exit-required")
    if cfg["no_dynamic_atr"]:
        cmd.append("--no-dynamic-atr")
    if cfg["dry_run"]:
        cmd.append("--train-dry-run")

    cmd += [
        "--loop-iterations", str(int(cfg["loop_iterations"])),
        "--loop-interval-min", str(float(cfg["loop_interval_min"])),
    ]
    if cfg["loop_refetch"]:
        cmd += [
            "--loop-refetch",
            "--loop-refetch-years", str(int(cfg["loop_refetch_years"])),
        ]
    if cfg["rebuild_exit_snapshots"]:
        cmd += [
            "--rebuild-exit-snapshots",
            "--snapshot-timeframe", cfg["snapshot_timeframe"],
            "--snapshot-stride", str(int(cfg["snapshot_stride"])),
        ]
    return cmd


def quote_command(cmd: list[str]) -> str:
    return " ".join(f'"{p}"' if " " in p else p for p in cmd)


# Validierung
def validate(cfg: dict[str, Any]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    if not cfg["timeframes"]:
        issues.append(("err", "Mindestens ein Timeframe noetig."))
    if cfg["target"] in ("core", "all"):
        if cfg["primary"] not in cfg["timeframes"]:
            issues.append(("err",
                           "Primary-Timeframe muss in den Timeframes enthalten sein."))
    if int(cfg["min_data_months"]) < 1:
        issues.append(("err", "Min data months muss >= 1 sein."))
    if int(cfg["count"]) > 0 and int(cfg["min_candles"]) > 0 \
            and int(cfg["count"]) < int(cfg["min_candles"]):
        issues.append(("warn",
                       f"count ({cfg['count']}) < min-candles ({cfg['min_candles']}) "
                       f"- wird hochgesetzt."))
    if cfg["target"] in ("exit", "all") and not cfg["exit_csv"].strip():
        issues.append(("err", "Exit-CSV-Pfad fehlt."))
    if cfg["target"] == "exit":
        path = ROOT / cfg["exit_csv"]
        if not path.exists():
            issues.append(("err", f"Exit-CSV nicht gefunden: {path}"))
    elif cfg["target"] == "all":
        path = ROOT / cfg["exit_csv"]
        if not path.exists() and not cfg["rebuild_exit_snapshots"]:
            level = "err" if cfg["exit_required"] else "warn"
            label = "ERR" if cfg["exit_required"] else "wird geskippt"
            issues.append((level,
                           f"Exit-CSV nicht gefunden ({label}): {path.name}"))
    if cfg["rebuild_exit_snapshots"] and cfg["target"] in ("exit", "all"):
        snap_csv = ROOT / cfg["save_csv_dir"] / f"gold_{cfg['snapshot_timeframe']}.csv"
        if not snap_csv.exists():
            issues.append(("err",
                           "Snapshot-Quelle fehlt: " + str(snap_csv.name)))
    if int(cfg["loop_iterations"]) < 0:
        issues.append(("err", "Loop-Iterationen muss >= 0 sein."))
    if float(cfg["loop_interval_min"]) < 0:
        issues.append(("err", "Loop-Interval muss >= 0 sein."))
    if cfg["use_csv_if_present"] and cfg["target"] in ("core", "all"):
        save_dir = ROOT / cfg["save_csv_dir"]
        missing = []
        for tf in cfg["timeframes"]:
            csv = save_dir / f"gold_{tf.replace(' ', '_')}.csv"
            if not csv.exists():
                missing.append(tf)
        if missing:
            issues.append(("warn",
                           "use-csv-if-present aktiv, aber CSVs fehlen fuer: "
                           f"{', '.join(missing)} - faellt auf Broker zurueck."))
    return issues


# App
class TrainingStarterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GoldBot - AI Training Starter")
        self.root.geometry("1180x880")
        self.root.minsize(940, 700)

        self.cfg = load_config()
        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.reader_thread: threading.Thread | None = None

        self._init_style()
        self._build_ui()
        self._refresh_command()
        self._refresh_validation()
        self.root.after(100, self._drain_log_queue)
        self.root.after(300, self._update_summary)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # Style
    def _init_style(self) -> None:
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        bg = "#15171c"
        bg2 = "#1c1f25"
        fg = "#e8e6df"
        mute = "#7d8390"
        gold = "#d6a44a"
        line = "#2c3038"
        self.root.configure(bg=bg)
        s.configure(".", background=bg, foreground=fg, fieldbackground=bg2,
                    bordercolor=line, lightcolor=line, darkcolor=line,
                    font=("Consolas", 10))
        s.configure("TFrame", background=bg)
        s.configure("TLabel", background=bg, foreground=fg)
        s.configure("Mute.TLabel", background=bg, foreground=mute,
                    font=("Consolas", 9))
        s.configure("Help.TLabel", background=bg, foreground=mute,
                    font=("Consolas", 8, "italic"))
        s.configure("Header.TLabel", background=bg, foreground=gold,
                    font=("Consolas", 9, "bold"))
        s.configure("TLabelframe", background=bg, foreground=mute, bordercolor=line)
        s.configure("TLabelframe.Label", background=bg, foreground=mute,
                    font=("Consolas", 9, "bold"))
        s.configure("TNotebook", background=bg, borderwidth=0)
        s.configure("TNotebook.Tab", background=bg2, foreground=mute,
                    padding=(14, 7), font=("Consolas", 10))
        s.map("TNotebook.Tab",
              background=[("selected", bg)],
              foreground=[("selected", gold)])
        s.configure("TButton", background=bg2, foreground=fg, padding=6,
                    bordercolor=line)
        s.map("TButton", background=[("active", line)])
        s.configure("Gold.TButton", background=gold, foreground="#1a1408",
                    font=("Consolas", 10, "bold"), padding=8)
        s.map("Gold.TButton", background=[("active", "#e6b35a"),
                                          ("disabled", bg2)],
              foreground=[("disabled", mute)])
        s.configure("Danger.TButton", foreground="#d96755", padding=8)
        s.configure("TEntry", fieldbackground=bg2, foreground=fg,
                    bordercolor=line, insertcolor=fg)
        s.configure("TCombobox", fieldbackground=bg2, foreground=fg,
                    bordercolor=line)
        s.configure("TCheckbutton", background=bg, foreground=fg)
        self._colors = {"bg": bg, "bg2": bg2, "fg": fg, "mute": mute,
                        "gold": gold, "line": line}

    # UI Aufbau
    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=(14, 10))
        top.pack(fill="x")
        ttk.Label(top, text="* GOLDBOT . AI TRAINING STARTER",
                  style="Header.TLabel").pack(side="left")
        ttk.Label(top, text="capital.com OR pre-fetched Dukascopy CSV",
                  style="Mute.TLabel").pack(side="right")

        self.banner = tk.Label(self.root, text="", anchor="w",
                               font=("Consolas", 10), padx=14, pady=6)
        self.banner.pack(fill="x")

        # Main PanedWindow for resizable layout
        self.paned = ttk.PanedWindow(self.root, orient="vertical")
        self.paned.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        # Top part (Notebook)
        self.nb_container = ttk.Frame(self.paned)
        self.paned.add(self.nb_container, weight=1)

        self.nb = ttk.Notebook(self.nb_container)
        self.nb.pack(fill="both", expand=True)

        self.tab_essential = ttk.Frame(self.nb, padding=14)
        self.tab_advanced = ttk.Frame(self.nb, padding=14)
        self.nb.add(self.tab_essential, text="  Essentiell  ")
        self.nb.add(self.tab_advanced, text="  Advanced  ")

        self._build_essential_tab(self.tab_essential)
        self._build_advanced_tab(self.tab_advanced)

        # Bottom part (Log Area)
        self.log_container = ttk.Frame(self.paned)
        self.paned.add(self.log_container, weight=0)

        self._build_log_area(self.log_container)
        self._build_summary_area()
        self._build_footer()

    # Essentiell Tab
    def _build_essential_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        # Target
        f_target = ttk.LabelFrame(parent, text="TARGET", padding=10)
        f_target.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.var_target = tk.StringVar(value=self.cfg["target"])
        for i, t in enumerate(TARGETS):
            ttk.Radiobutton(f_target, text=t, value=t, variable=self.var_target,
                            command=self._refresh).grid(row=0, column=i, padx=8,
                                                         sticky="w")
        ttk.Label(
            f_target,
            text=("core = nur Indikator-Modelle (XGBoost/LightGBM je TF). "
                  "exit = nur Exit-AI Specialist. all = beides parallel."),
            style="Help.TLabel", wraplength=480, justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

        # Count
        f_count = ttk.LabelFrame(parent, text="COUNT (Kerzen je Timeframe vom Broker)",
                                 padding=10)
        f_count.grid(row=0, column=1, sticky="nsew", pady=(0, 8))
        self.var_count = tk.StringVar(value=str(self.cfg["count"] or ""))
        e = ttk.Entry(f_count, textvariable=self.var_count, width=12)
        e.grid(row=0, column=0, sticky="w")
        e.bind("<KeyRelease>", lambda *_: self._refresh())
        for i, n in enumerate([0, 5000, 12000, 50000]):
            label = "auto" if n == 0 else str(n)
            ttk.Button(f_count, text=label,
                       command=lambda n=n: (self.var_count.set(str(n)), self._refresh())
                       ).grid(row=0, column=i + 1, padx=4)
        ttk.Label(
            f_count,
            text=("0 / leer = automatisch aus 'Min data months'. "
                  "Sonst feste Anzahl Kerzen pro Broker-Fetch. "
                  "Wird auf Min hochgesetzt falls zu klein."),
            style="Help.TLabel", wraplength=480, justify="left",
        ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(8, 0))

        # Timeframes
        f_tf = ttk.LabelFrame(parent, text="TIMEFRAMES (Primary = Hauptmodell)",
                              padding=10)
        f_tf.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        self.tf_vars: dict[str, tk.BooleanVar] = {}
        self.var_primary = tk.StringVar(value=self.cfg["primary"])
        for i, tf in enumerate(TIMEFRAMES):
            v = tk.BooleanVar(value=tf in self.cfg["timeframes"])
            self.tf_vars[tf] = v
            ttk.Checkbutton(f_tf, text=tf, variable=v,
                            command=self._refresh).grid(row=0, column=i, padx=6,
                                                         sticky="w")
        ttk.Label(f_tf, text="Primary:", style="Mute.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        self.cmb_primary = ttk.Combobox(f_tf, textvariable=self.var_primary,
                                        values=TIMEFRAMES, width=8, state="readonly")
        self.cmb_primary.grid(row=1, column=1, columnspan=3, sticky="w", pady=(8, 0))
        self.cmb_primary.bind("<<ComboboxSelected>>", lambda *_: self._refresh())
        ttk.Label(
            f_tf,
            text=("Jeder ausgewaehlte Timeframe trainiert ein eigenes Modell "
                  "(parallel). Primary landet im OUTPUT-Root, andere unter "
                  "<output>/timeframes/<tf>/. Mehr TFs = mehr RAM/CPU gleichzeitig."),
            style="Help.TLabel", wraplength=900, justify="left",
        ).grid(row=2, column=0, columnspan=8, sticky="w", pady=(8, 0))

        # CSV-Modus + Output zusammen
        f_data = ttk.LabelFrame(parent, text="DATEN-QUELLE", padding=10)
        f_data.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        f_data.columnconfigure(1, weight=1)

        self.var_use_csv = tk.BooleanVar(value=self.cfg["use_csv_if_present"])
        ttk.Checkbutton(
            f_data,
            text="Vorgefertigte CSVs bevorzugen (--use-csv-if-present)",
            variable=self.var_use_csv,
            command=self._refresh,
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            f_data,
            text=("AN: nutzt vorhandene data/gold_<tf>.csv (zB von "
                  "scripts/fetch_bulk_history.py). Kein Broker-Login. "
                  "AUS: holt frisch via Capital.com (--broker)."),
            style="Help.TLabel", wraplength=900, justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))

        ttk.Label(f_data, text="Output dir:", style="Mute.TLabel").grid(
            row=2, column=0, sticky="w")
        self.var_output = tk.StringVar(value=self.cfg["output"])
        oe = ttk.Entry(f_data, textvariable=self.var_output)
        oe.grid(row=2, column=1, sticky="ew", padx=(8, 0))
        oe.bind("<KeyRelease>", lambda *_: self._refresh())
        ttk.Button(f_data, text="...", width=4,
                   command=lambda: self._pick_dir(self.var_output)
                   ).grid(row=2, column=2, padx=(6, 0))
        ttk.Label(
            f_data,
            text=("Wo das primaere Modell gespeichert wird. "
                  "Versionierte Subdirs (v001_<ts>/) werden automatisch angelegt."),
            style="Help.TLabel", wraplength=900, justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # Actions
        f_act = ttk.Frame(parent)
        f_act.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for i in range(4): f_act.columnconfigure(i, weight=1)

        self.btn_start = ttk.Button(f_act, text=">  TRAINING STARTEN",
                                    style="Gold.TButton", command=self.start_training)
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=6)

        self.btn_loop_exit = ttk.Button(f_act, text="∞  EXIT-AI LOOP",
                                        style="Gold.TButton", command=self.start_exit_loop)
        self.btn_loop_exit.grid(row=0, column=1, sticky="ew", padx=(6, 6), ipady=6)

        self.btn_dry = ttk.Button(f_act, text="?  Befehl",
                                  command=self.show_command_dialog)
        self.btn_dry.grid(row=0, column=2, padx=(6, 6), ipady=6)

        self.btn_stop = ttk.Button(f_act, text="X  STOP",
                                   style="Danger.TButton", command=self.stop_training,
                                   state="disabled")
        self.btn_stop.grid(row=0, column=3, padx=(6, 0), ipady=6)

    # Advanced Tab
    def _build_advanced_tab(self, parent: ttk.Frame) -> None:
        for i in range(3):
            parent.columnconfigure(i, weight=1)

        # Daten / Modelle
        f1 = ttk.LabelFrame(parent, text="DATEN / MODELLE", padding=10)
        f1.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        self.var_min_candles = tk.StringVar(value=str(self.cfg["min_candles"] or ""))
        self.var_save_csv = tk.StringVar(value=self.cfg["save_csv_dir"])
        self.var_min_months = tk.StringVar(value=str(self.cfg["min_data_months"]))
        self._make_field(
            f1, 0, "Min candles (0 = auto)", self.var_min_candles,
            help_text=("Min-Anzahl je Timeframe. 0/leer = automatisch aus Min Months. "
                       "Erzwingt 'Insufficient candles' Fehler im Trainer wenn unter."),
        )
        self._make_field(
            f1, 1, "Save-CSV-Dir", self.var_save_csv,
            picker=lambda: self._pick_dir(self.var_save_csv),
            help_text=("Verzeichnis fuer Broker-Snapshots UND fuer "
                       "--use-csv-if-present (sucht hier nach gold_<tf>.csv)."),
        )
        self._make_field(
            f1, 2, "Min data months", self.var_min_months,
            help_text=("Mindest-History fuer Training. 6 = TRAIN-07-konform. "
                       "Wird in min-candles per TF umgerechnet."),
        )

        # Strategie
        f2 = ttk.LabelFrame(parent, text="STRATEGIE", padding=10)
        f2.grid(row=0, column=1, sticky="nsew", padx=6, pady=(0, 8))
        self.var_max_hold = tk.StringVar(value=str(self.cfg["max_holding"]))
        self.var_tp = tk.StringVar(value=str(self.cfg["tp_atr_mult"]))
        self.var_sl = tk.StringVar(value=str(self.cfg["sl_atr_mult"]))
        self.var_no_dyn_atr = tk.BooleanVar(value=self.cfg["no_dynamic_atr"])
        self.var_dry_run = tk.BooleanVar(value=self.cfg["dry_run"])
        self._make_field(
            f2, 0, "Max holding (bars)", self.var_max_hold,
            help_text=("Max. Bars die ein Trade fuer Label-Generierung offen sein darf. "
                       "Beeinflusst direkt Win-Rate und Datensatz-Groesse."),
        )
        self._make_field(
            f2, 1, "TP x ATR", self.var_tp,
            help_text=("Take-Profit als Vielfaches der ATR (Volatilitaet). "
                       "2.0 = 2x ATR. Hoeher = weniger Wins, mehr R."),
        )
        self._make_field(
            f2, 2, "SL x ATR", self.var_sl,
            help_text=("Stop-Loss als Vielfaches der ATR. 1.5 = 1.5x ATR. "
                       "Niedriger = engerer Stop, mehr Stop-Outs."),
        )
        ttk.Checkbutton(f2, text="Disable dynamic ATR (--no-dynamic-atr)",
                        variable=self.var_no_dyn_atr,
                        command=self._refresh
                        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(
            f2, text="An: legacy-Modus mit festen Pip-TP/SL statt ATR-basiert.",
            style="Help.TLabel", wraplength=320, justify="left",
        ).grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(f2, text="Dry-run (--train-dry-run)",
                        variable=self.var_dry_run,
                        command=self._refresh
                        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(
            f2, text="An: Pipeline simulieren ohne Modelle zu speichern.",
            style="Help.TLabel", wraplength=320, justify="left",
        ).grid(row=9, column=0, columnspan=2, sticky="w")

        # Exit-AI
        f3 = ttk.LabelFrame(parent, text="EXIT-AI", padding=10)
        f3.grid(row=0, column=2, sticky="nsew", padx=(6, 0), pady=(0, 8))
        self.var_exit_csv = tk.StringVar(value=self.cfg["exit_csv"])
        self.var_exit_required = tk.BooleanVar(value=self.cfg["exit_required"])
        self.var_exit_min_samples = tk.StringVar(value=str(self.cfg["exit_min_samples"]))
        self.var_exit_purge = tk.StringVar(value=str(self.cfg["exit_purge_gap"]))
        self.var_exit_min_train = tk.StringVar(value=str(self.cfg["exit_min_train_samples"]))
        self.var_exit_min_test = tk.StringVar(value=str(self.cfg["exit_min_test_samples"]))
        self._make_field(
            f3, 0, "Exit CSV", self.var_exit_csv,
            picker=lambda: self._pick_file(self.var_exit_csv),
            help_text=("Pfad zur Snapshot-CSV mit echten Trade-Exit-Daten "
                       "(timestamp, direction, entry_price, future_*_r, ...)."),
        )
        self._make_field(
            f3, 1, "Min samples", self.var_exit_min_samples,
            help_text="Min-Zeilen in der CSV bevor Training startet (Sanity-Check).",
        )
        self._make_field(
            f3, 2, "Purge gap (bars)", self.var_exit_purge,
            help_text=("Luecke zwischen Train- und Test-Set in Bars. "
                       "Verhindert Daten-Leakage durch Auto-Korrelation."),
        )
        self._make_field(
            f3, 3, "Min train samples", self.var_exit_min_train,
            help_text="Mindest-Anzahl Trainings-Zeilen pro Walk-Forward-Fenster.",
        )
        self._make_field(
            f3, 4, "Min test samples", self.var_exit_min_test,
            help_text="Mindest-Anzahl Test-Zeilen pro Walk-Forward-Fenster.",
        )
        ttk.Checkbutton(
            f3, text="Hard-fail wenn Exit-CSV fehlt (--exit-required)",
            variable=self.var_exit_required, command=self._refresh,
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(
            f3,
            text=("Nur bei target=all relevant. Aus = Skip + Warnung wenn CSV fehlt. "
                  "An = Abbruch."),
            style="Help.TLabel", wraplength=320, justify="left",
        ).grid(row=11, column=0, columnspan=2, sticky="w")

        # Snapshot-Generator innerhalb Exit-AI Frame
        self.var_rebuild_snapshots = tk.BooleanVar(value=self.cfg["rebuild_exit_snapshots"])
        ttk.Checkbutton(
            f3, text="Exit-Snapshots automatisch bauen (--rebuild-exit-snapshots)",
            variable=self.var_rebuild_snapshots, command=self._refresh,
        ).grid(row=12, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(
            f3,
            text=("AN: vor jedem Exit-AI-Job baut scripts/build_exit_snapshots.py "
                  "die CSV neu aus dem unten gewaehlten OHLCV-Timeframe. "
                  "AUS: nutzt vorhandene Exit-CSV (oder skippt)."),
            style="Help.TLabel", wraplength=320, justify="left",
        ).grid(row=13, column=0, columnspan=2, sticky="w")

        ttk.Label(f3, text="Snapshot-Quelle (TF):", style="Mute.TLabel").grid(
            row=14, column=0, sticky="w", pady=(6, 2))
        self.var_snapshot_tf = tk.StringVar(value=self.cfg["snapshot_timeframe"])
        ttk.Combobox(f3, textvariable=self.var_snapshot_tf, values=TIMEFRAMES,
                     width=8, state="readonly").grid(row=15, column=0, sticky="w")
        ttk.Label(f3, text="Stride:", style="Mute.TLabel").grid(
            row=14, column=1, sticky="w", pady=(6, 2))
        self.var_snapshot_stride = tk.StringVar(value=str(self.cfg["snapshot_stride"]))
        ttk.Entry(f3, textvariable=self.var_snapshot_stride, width=6).grid(
            row=15, column=1, sticky="w")
        ttk.Label(
            f3,
            text=("TF: 5m=Standard (~50k Snapshots), 15m=schneller (~12k). "
                  "Stride: oeffne virtuellen Trade alle N Bars (4 = haeufig)."),
            style="Help.TLabel", wraplength=320, justify="left",
        ).grid(row=16, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Loop frame (zweite Row im Advanced)
        f4 = ttk.LabelFrame(parent, text="LOOP (autonomer Dauer-Trainings-Modus)",
                            padding=10)
        f4.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 8))
        f4.columnconfigure(1, weight=1)
        f4.columnconfigure(3, weight=1)

        self.var_loop_iter = tk.StringVar(value=str(self.cfg["loop_iterations"]))
        self.var_loop_interval = tk.StringVar(value=str(self.cfg["loop_interval_min"]))
        self.var_loop_refetch = tk.BooleanVar(value=self.cfg["loop_refetch"])
        self.var_loop_refetch_years = tk.StringVar(value=str(self.cfg["loop_refetch_years"]))

        ttk.Label(f4, text="Iterationen (0 = unendlich):",
                  style="Mute.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(f4, textvariable=self.var_loop_iter, width=8).grid(
            row=0, column=1, sticky="w", padx=(8, 16))
        ttk.Label(f4, text="Pause zwischen Iterationen (min):",
                  style="Mute.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(f4, textvariable=self.var_loop_interval, width=8).grid(
            row=0, column=3, sticky="w", padx=(8, 0))

        ttk.Checkbutton(
            f4, text="Vor jedem Lauf neue Daten von Dukascopy ziehen "
                     "(--loop-refetch)",
            variable=self.var_loop_refetch, command=self._refresh,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(f4, text="Refetch Jahre:", style="Mute.TLabel").grid(
            row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(f4, textvariable=self.var_loop_refetch_years, width=6).grid(
            row=1, column=3, sticky="w", padx=(8, 0), pady=(8, 0))

        ttk.Label(
            f4,
            text=("Iterationen=1 (Default): einmal trainieren wie bisher. "
                  "0 = laeuft endlos (Stop-Button beendet). "
                  "Refetch: nutzt fetch_bulk_history.py (resume-aware) bevor "
                  "neu trainiert wird - ideal fuer 'taegliches Update'."),
            style="Help.TLabel", wraplength=900, justify="left",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        for var in (self.var_loop_iter, self.var_loop_interval,
                    self.var_loop_refetch_years, self.var_snapshot_stride,
                    self.var_snapshot_tf):
            try:
                var.trace_add("write", lambda *_: self._refresh())
            except Exception:
                pass

        # Reset
        ttk.Button(parent, text="Auf Defaults zuruecksetzen",
                   command=self.reset_defaults
                   ).grid(row=2, column=0, sticky="w", pady=(4, 0))

    def _make_field(self, parent, row, label, var, picker=None,
                    help_text: str | None = None) -> None:
        parent.columnconfigure(0, weight=1)
        base_row = row * 3
        ttk.Label(parent, text=label, style="Mute.TLabel").grid(
            row=base_row, column=0, sticky="w", pady=(6 if row else 0, 2))
        e = ttk.Entry(parent, textvariable=var)
        e.grid(row=base_row + 1, column=0, sticky="ew")
        e.bind("<KeyRelease>", lambda *_: self._refresh())
        if picker:
            ttk.Button(parent, text="...", width=4, command=picker
                       ).grid(row=base_row + 1, column=1, padx=(4, 0))
        if help_text:
            ttk.Label(parent, text=help_text, style="Help.TLabel",
                      wraplength=320, justify="left",
                      ).grid(row=base_row + 2, column=0, columnspan=2,
                             sticky="w", pady=(2, 0))

    # Log + Footer
    def _build_log_area(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="LIVE LOG", padding=8)
        f.pack(fill="both", expand=True)
        self.txt_log = tk.Text(f, height=12, bg=self._colors["bg2"],
                               fg=self._colors["fg"],
                               insertbackground=self._colors["fg"],
                               font=("Consolas", 9), borderwidth=0,
                               wrap="none")
        sb = ttk.Scrollbar(f, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set, state="disabled")
        self.txt_log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.txt_log.tag_config("err", foreground="#d96755")
        self.txt_log.tag_config("ok", foreground="#7fc26b")
        self.txt_log.tag_config("info", foreground=self._colors["gold"])
        self.txt_log.tag_config("mute", foreground=self._colors["mute"])

    def _build_summary_area(self) -> None:
        f = ttk.LabelFrame(self.root, text="TRAININGS-ZUSAMMENFASSUNG (Lernfaktor)",
                           padding=8)
        f.pack(fill="x", padx=12, pady=(8, 0))

        bar = tk.Frame(f, bg=self._colors["bg"])
        bar.pack(fill="x")
        self.lbl_lernfaktor = tk.Label(
            bar, text="Lernfaktor: -",
            font=("Consolas", 16, "bold"),
            bg=self._colors["bg"], fg=self._colors["mute"], padx=8, pady=2,
        )
        self.lbl_lernfaktor.pack(side="left")
        self.lbl_summary_hint = tk.Label(
            bar,
            text="(% Verbesserung des Profit-Factor ggue. vorheriger Version / Baseline)",
            bg=self._colors["bg"], fg=self._colors["mute"],
            font=("Consolas", 8, "italic"),
        )
        self.lbl_summary_hint.pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Aktualisieren",
                   command=self._update_summary).pack(side="right")

        self.txt_summary = tk.Text(
            f, height=8, bg=self._colors["bg2"], fg=self._colors["fg"],
            insertbackground=self._colors["fg"],
            font=("Consolas", 9), borderwidth=0, wrap="word",
        )
        self.txt_summary.pack(fill="x", pady=(6, 0))
        self.txt_summary.tag_config("up", foreground="#7fc26b")
        self.txt_summary.tag_config("down", foreground="#d96755")
        self.txt_summary.tag_config("mute", foreground=self._colors["mute"])
        self.txt_summary.tag_config("hdr", foreground=self._colors["gold"],
                                    font=("Consolas", 9, "bold"))
        self.txt_summary.configure(state="disabled")

    # Summary helpers
    @staticmethod
    def _list_versions(parent: Path) -> list[Path]:
        if not parent.exists() or not parent.is_dir():
            return []
        return sorted(
            (p for p in parent.iterdir()
             if p.is_dir() and p.name.startswith("v")),
            key=lambda p: p.name,
        )

    def _read_core_metrics(self, version_dir: Path) -> dict | None:
        report_path = version_dir / "training_report.json"
        if not report_path.exists():
            return None
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        agg = report.get("aggregate", {}) or {}
        best = agg.get("best_model", "xgboost")
        m = agg.get(best) or agg.get("xgboost") or {}
        if not m:
            return None
        return {
            "pf": float(m.get("profit_factor", 0.0) or 0.0),
            "wr": float(m.get("win_rate", 0.0) or 0.0),
            "sharpe": float(m.get("sharpe", 0.0) or 0.0),
            "trades": int(m.get("n_trades", 0) or 0),
            "model": best,
        }

    def _read_exit_metrics(self, version_dir: Path) -> dict | None:
        comp_path = version_dir / "exit_ai_comparison_report.json"
        promo_path = version_dir / "exit_ai_promotion_artifact.json"
        if not comp_path.exists():
            return None
        try:
            report = json.loads(comp_path.read_text(encoding="utf-8"))
            promo = (json.loads(promo_path.read_text(encoding="utf-8"))
                     if promo_path.exists() else {})
        except Exception:
            return None
        comp = report.get("comparison", {}) or {}
        base = comp.get("baseline", {}) or {}
        cand = comp.get("exit_ai_candidate", {}) or {}
        deltas = report.get("deltas", {}) or {}
        pf_base = float(base.get("profit_factor_proxy", 0.0) or 0.0)
        pf_cand = float(cand.get("profit_factor_proxy", 0.0) or 0.0)
        pf_delta = float(deltas.get("profit_factor_delta", 0.0) or 0.0)
        pf_lift_pct = (pf_delta / pf_base * 100.0) if pf_base > 0 else 0.0
        dd_base = float(base.get("max_drawdown_proxy", 0.0) or 0.0)
        dd_delta = float(deltas.get("drawdown_delta", 0.0) or 0.0)
        dd_better_pct = (-dd_delta / dd_base * 100.0) if dd_base > 0 else 0.0
        ret_base = float(base.get("trade_retention", 0.0) or 0.0)
        ret_delta = float(deltas.get("trade_retention_delta", 0.0) or 0.0)
        ret_pct = (ret_delta / ret_base * 100.0) if ret_base > 0 else 0.0
        return {
            "pf_base": pf_base,
            "pf_cand": pf_cand,
            "pf_lift_pct": pf_lift_pct,
            "dd_better_pct": dd_better_pct,
            "ret_pct": ret_pct,
            "promotion": str(promo.get("promotion_status", "unknown")),
            "windows": int(report.get("window_count", 0) or 0),
        }

    def _update_summary(self) -> None:
        if not hasattr(self, "txt_summary"):
            return
        cfg = self._gather_cfg()
        output_dir = ROOT / cfg["output"]
        timeframes = list(cfg["timeframes"]) or ["5m"]
        primary = cfg["primary"]

        lines: list[tuple[str, str | None]] = []
        weighted_lift = 0.0
        weight_sum = 0.0
        per_part: list[tuple[str, float]] = []

        if cfg["target"] in ("core", "all"):
            lines.append(("CORE-AI  -  Profit-Factor: aktuell vs vorherige Version\n",
                          "hdr"))
            for tf in timeframes:
                tf_dir = output_dir if tf == primary else (
                    output_dir / "timeframes" / tf.replace(" ", "_"))
                versions = [v for v in self._list_versions(tf_dir)
                            if (v / "training_report.json").exists()]
                if not versions:
                    lines.append(
                        (f"  {tf:4s}  noch keine Reports unter {tf_dir.name}\n",
                         "mute"))
                    continue
                cur_metrics = self._read_core_metrics(versions[-1])
                if cur_metrics is None:
                    lines.append((f"  {tf:4s}  Report unlesbar\n", "mute"))
                    continue
                if len(versions) < 2:
                    lines.append(
                        (f"  {tf:4s}  PF {cur_metrics['pf']:.3f}  "
                         f"WR {cur_metrics['wr'] * 100:.1f}%  "
                         f"Sharpe {cur_metrics['sharpe']:.2f}  "
                         f"({cur_metrics['trades']} trades, {cur_metrics['model']})  "
                         f"[Erster Run - keine Vergleichsbasis]\n", None))
                    continue
                prev_metrics = self._read_core_metrics(versions[-2])
                if prev_metrics is None or prev_metrics["pf"] <= 0:
                    lines.append(
                        (f"  {tf:4s}  Vorherige Version unlesbar\n", "mute"))
                    continue
                lift = ((cur_metrics["pf"] - prev_metrics["pf"])
                        / prev_metrics["pf"] * 100.0)
                tag = "up" if lift >= 0 else "down"
                sign = "+" if lift >= 0 else ""
                lines.append(
                    (f"  {tf:4s}  PF {prev_metrics['pf']:.3f} -> "
                     f"{cur_metrics['pf']:.3f}  {sign}{lift:.1f}%  "
                     f"WR {cur_metrics['wr'] * 100:.1f}%  "
                     f"Sharpe {cur_metrics['sharpe']:.2f}  "
                     f"({cur_metrics['trades']} trades)\n", tag))
                trades = max(cur_metrics["trades"], 1)
                weighted_lift += lift * trades
                weight_sum += trades
                per_part.append((f"core-{tf}", lift))

        if cfg["target"] in ("exit", "all"):
            lines.append(("\nEXIT-AI  -  Lift gegenueber Regel-basierter Baseline\n",
                          "hdr"))
            exit_dir = output_dir / "specialists" / "exit_ai"
            versions = [v for v in self._list_versions(exit_dir)
                        if (v / "exit_ai_comparison_report.json").exists()]
            if not versions:
                lines.append(("  noch keine Exit-AI Reports gefunden\n", "mute"))
            else:
                metrics = self._read_exit_metrics(versions[-1])
                if metrics is None:
                    lines.append(("  Report unlesbar\n", "mute"))
                else:
                    tag = "up" if metrics["pf_lift_pct"] >= 0 else "down"
                    sign = "+" if metrics["pf_lift_pct"] >= 0 else ""
                    promo = metrics["promotion"].upper()
                    promo_tag = ("up" if promo == "APPROVED"
                                 else "down" if promo == "REJECTED"
                                 else "mute")
                    lines.append(
                        (f"  PF  Baseline {metrics['pf_base']:.3f} -> "
                         f"Candidate {metrics['pf_cand']:.3f}  "
                         f"{sign}{metrics['pf_lift_pct']:.1f}%  "
                         f"({metrics['windows']} windows)\n", tag))
                    lines.append((f"  Promotion-Status: ", "mute"))
                    lines.append((f"{promo}\n", promo_tag))
                    dd_sign = "+" if metrics["dd_better_pct"] >= 0 else ""
                    ret_sign = "+" if metrics["ret_pct"] >= 0 else ""
                    lines.append(
                        (f"  Drawdown {dd_sign}{metrics['dd_better_pct']:.1f}% "
                         f"besser   "
                         f"Trade-Retention {ret_sign}{metrics['ret_pct']:.1f}%\n",
                         "mute"))
                    weighted_lift += metrics["pf_lift_pct"] * 1000.0
                    weight_sum += 1000.0
                    per_part.append(("exit-ai", metrics["pf_lift_pct"]))

        if not lines:
            lines.append(("Keine Trainingsdaten gefunden. "
                          "Starte ein Training und klicke 'Aktualisieren'.\n",
                          "mute"))

        self.txt_summary.configure(state="normal")
        self.txt_summary.delete("1.0", "end")
        for text, tag in lines:
            self.txt_summary.insert("end", text, (tag,) if tag else ())
        self.txt_summary.configure(state="disabled")

        if weight_sum > 0:
            overall = weighted_lift / weight_sum
            sign = "+" if overall >= 0 else ""
            color = "#7fc26b" if overall >= 0 else "#d96755"
            self.lbl_lernfaktor.config(
                text=f"Lernfaktor: {sign}{overall:.1f}%",
                fg=color,
            )
        else:
            self.lbl_lernfaktor.config(text="Lernfaktor: -",
                                       fg=self._colors["mute"])

    def _build_footer(self) -> None:
        f = tk.Frame(self.root, bg=self._colors["bg2"])
        f.pack(fill="x", padx=0, pady=(8, 0))
        self.lbl_status = tk.Label(f, text="* idle", bg=self._colors["bg2"],
                                   fg=self._colors["mute"],
                                   font=("Consolas", 9, "bold"),
                                   padx=14, pady=8)
        self.lbl_status.pack(side="left")
        self.lbl_cmd = tk.Label(f, text="", bg=self._colors["bg2"],
                                fg=self._colors["mute"], font=("Consolas", 9),
                                anchor="w", justify="left")
        self.lbl_cmd.pack(side="left", fill="x", expand=True, padx=(8, 8))
        ttk.Button(f, text="Copy", command=self.copy_command).pack(
            side="right", padx=(0, 14), pady=6)

    # Safe converters - kein TclError mehr beim Tippen
    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            text = str(value).strip()
            if not text:
                return default
            return int(float(text))
        except (ValueError, TypeError, tk.TclError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            text = str(value).strip()
            if not text:
                return default
            return float(text)
        except (ValueError, TypeError, tk.TclError):
            return default

    # State sync
    def _gather_cfg(self) -> dict[str, Any]:
        return {
            "target": self.var_target.get(),
            "timeframes": [tf for tf, v in self.tf_vars.items() if v.get()],
            "primary": self.var_primary.get(),
            "count": self._safe_int(self.var_count.get()),
            "min_candles": self._safe_int(self.var_min_candles.get()),
            "output": self.var_output.get(),
            "save_csv_dir": self.var_save_csv.get(),
            "min_data_months": self._safe_int(self.var_min_months.get(), 6),
            "max_holding": self._safe_int(self.var_max_hold.get(), 15),
            "tp_atr_mult": self._safe_float(self.var_tp.get(), 2.0),
            "sl_atr_mult": self._safe_float(self.var_sl.get(), 1.5),
            "no_dynamic_atr": bool(self.var_no_dyn_atr.get()),
            "dry_run": bool(self.var_dry_run.get()),
            "use_csv_if_present": bool(self.var_use_csv.get()),
            "exit_csv": self.var_exit_csv.get(),
            "exit_required": bool(self.var_exit_required.get()),
            "exit_min_samples": self._safe_int(self.var_exit_min_samples.get(), 500),
            "exit_purge_gap": self._safe_int(self.var_exit_purge.get(), 12),
            "exit_min_train_samples": self._safe_int(self.var_exit_min_train.get(), 120),
            "exit_min_test_samples": self._safe_int(self.var_exit_min_test.get(), 40),
            "loop_iterations": self._safe_int(self.var_loop_iter.get(), 1),
            "loop_interval_min": self._safe_float(self.var_loop_interval.get(), 0.0),
            "loop_refetch": bool(self.var_loop_refetch.get()),
            "loop_refetch_years": self._safe_int(self.var_loop_refetch_years.get(), 2),
            "rebuild_exit_snapshots": bool(self.var_rebuild_snapshots.get()),
            "snapshot_timeframe": self.var_snapshot_tf.get() or "5m",
            "snapshot_stride": self._safe_int(self.var_snapshot_stride.get(), 4),
        }

    def _refresh(self) -> None:
        self._refresh_command()
        self._refresh_validation()

    def _refresh_command(self) -> None:
        try:
            cfg = self._gather_cfg()
            self.lbl_cmd.config(text=quote_command(build_command(cfg)))
        except Exception as exc:
            self.lbl_cmd.config(text=f"(fehler: {exc})")

    def _refresh_validation(self) -> None:
        cfg = self._gather_cfg()
        issues = validate(cfg)
        if not issues:
            self.banner.config(text="* Konfiguration valide. Bereit zum Start.",
                               bg="#1f3023", fg="#7fc26b")
            if self.proc is None:
                self.btn_start.state(["!disabled"])
            return
        worst = "err" if any(lvl == "err" for lvl, _ in issues) else "warn"
        text = "  .  ".join(m for _, m in issues)
        if worst == "err":
            self.banner.config(text=f"X {text}", bg="#3a1c1c", fg="#e89888")
            self.btn_start.state(["disabled"])
            self.btn_loop_exit.state(["disabled"])
        else:
            self.banner.config(text=f"! {text}", bg="#3a311c", fg="#e8c888")
            if self.proc is None:
                self.btn_start.state(["!disabled"])
                self.btn_loop_exit.state(["!disabled"])

    # Pickers
    def _pick_dir(self, var: tk.StringVar) -> None:
        initial = ROOT / var.get() if var.get() else ROOT
        d = filedialog.askdirectory(
            initialdir=str(initial) if initial.exists() else str(ROOT))
        if d:
            try:
                rel = os.path.relpath(d, ROOT)
                var.set(rel.replace("\\", "/"))
            except ValueError:
                var.set(d)
            self._refresh()

    def _pick_file(self, var: tk.StringVar) -> None:
        f = filedialog.askopenfilename(initialdir=str(ROOT),
                                       filetypes=[("CSV", "*.csv"),
                                                  ("Alle", "*.*")])
        if f:
            try:
                rel = os.path.relpath(f, ROOT)
                var.set(rel.replace("\\", "/"))
            except ValueError:
                var.set(f)
            self._refresh()

    # Training Lifecycle
    def start_exit_loop(self) -> None:
        """Helper to start infinite Exit-AI training cycle with one click."""
        if not messagebox.askyesno("Exit-AI Loop", "Möchtest du das Exit-AI Dauer-Training starten? (Endlos-Schleife)"):
            return
        self.var_target.set("exit")
        self.var_loop_iter.set("0") # infinite
        self.var_rebuild_snapshots.set(True)
        self._refresh()
        self.start_training()

    def start_training(self) -> None:
        cfg = self._gather_cfg()
        if any(lvl == "err" for lvl, _ in validate(cfg)):
            messagebox.showerror("Fehler",
                                 "Konfiguration ungueltig - siehe Banner.")
            return
        if not TRAINING_SCRIPT.exists():
            messagebox.showerror("Fehler",
                                 f"start_ai_training.py nicht gefunden:\n"
                                 f"{TRAINING_SCRIPT}")
            return
        save_config(cfg)
        cmd = build_command(cfg)
        self._log(f"$ {quote_command(cmd)}\n", tag="info")
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except Exception as exc:
            messagebox.showerror("Fehler",
                                 f"Konnte Prozess nicht starten:\n{exc}")
            self.proc = None
            return
        self.btn_start.state(["disabled"])
        self.btn_loop_exit.state(["disabled"])
        self.btn_stop.state(["!disabled"])
        self.lbl_status.config(text="* running", fg=self._colors["gold"])
        self.reader_thread = threading.Thread(
            target=self._read_proc_output, daemon=True)
        self.reader_thread.start()

    def stop_training(self) -> None:
        if self.proc is None:
            return
        self._log("\n[stop] sende terminate() ...\n", tag="mute")
        try:
            self.proc.terminate()
        except Exception:
            pass
        threading.Thread(target=self._kill_if_alive, daemon=True).start()

    def _kill_if_alive(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._log("[stop] timeout - sende kill()\n", tag="err")
            try:
                self.proc.kill()
            except Exception:
                pass

    def _read_proc_output(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self.log_queue.put(line)
        rc = self.proc.wait()
        self.log_queue.put(f"\n[exit] code={rc}\n")
        self.log_queue.put(f"__DONE__:{rc}")

    def _drain_log_queue(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line.startswith("__DONE__:"):
                    rc = int(line.split(":", 1)[1])
                    self._on_proc_done(rc)
                    continue
                lower = line.lower()
                tag = "err" if ("error" in lower or "fail" in lower
                                or "traceback" in lower) else None
                if "ok" in lower and "finished" in lower:
                    tag = "ok"
                if "warn" in lower or "skipped" in lower:
                    tag = "info"
                self._log(line, tag=tag)
                if "all training jobs finished successfully" in lower:
                    self.root.after(500, self._update_summary)
                    self.root.after(800, self._display_loop_summary)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log_queue)

    def _display_loop_summary(self) -> None:
        """Appends a concise performance summary directly to the live log."""
        cfg = self._gather_cfg()
        output_dir = ROOT / cfg["output"]
        timeframes = list(cfg["timeframes"]) or ["5m"]
        primary = cfg["primary"]

        self._log("\n" + "="*60 + "\n", tag="info")
        self._log("LOOP ZUSAMMENFASSUNG (Performance Update)\n", tag="hdr")
        self._log("="*60 + "\n", tag="info")

        # Core AI Summary
        if cfg["target"] in ("core", "all"):
            self._log("\nCORE-AI (Best Model per TF):\n", tag="hdr")
            for tf in timeframes:
                tf_dir = output_dir if tf == primary else (output_dir / "timeframes" / tf.replace(" ", "_"))
                versions = self._list_versions(tf_dir)
                if not versions: continue

                cur = self._read_core_metrics(versions[-1])
                if not cur: continue

                msg = f"  {tf:4s}: PF {cur['pf']:.3f} | WR {cur['wr']*100:.1f}% | Trades: {cur['trades']}"

                if len(versions) >= 2:
                    prev = self._read_core_metrics(versions[-2])
                    if prev and prev["pf"] > 0:
                        lift = ((cur["pf"] - prev["pf"]) / prev["pf"]) * 100.0
                        sign = "+" if lift >= 0 else ""
                        msg += f" | Verbess.: {sign}{lift:.1f}%"
                        tag = "ok" if lift >= 0 else "err"
                    else:
                        tag = None
                else:
                    msg += " | [Initial Run]"
                    tag = None

                self._log(msg + "\n", tag=tag)

        # Exit AI Summary
        if cfg["target"] in ("exit", "all"):
            self._log("\nEXIT-AI (vs Baseline):\n", tag="hdr")
            exit_dir = output_dir / "specialists" / "exit_ai"
            versions = self._list_versions(exit_dir)
            if versions:
                met = self._read_exit_metrics(versions[-1])
                if met:
                    tag = "ok" if met["pf_lift_pct"] >= 0 else "err"
                    sign = "+" if met["pf_lift_pct"] >= 0 else ""
                    self._log(f"  Lift: {sign}{met['pf_lift_pct']:.1f}% ggue. Baseline\n", tag=tag)
                    self._log(f"  Drawdown: {met['dd_better_pct']:+.1f}% Verbesserung\n", tag="info")
                    self._log(f"  Status: {met['promotion'].upper()}\n", tag=tag)
            else:
                self._log("  Keine Exit-AI Daten gefunden.\n", tag="mute")

        self._log("\n" + "="*60 + "\n\n", tag="info")

    def _on_proc_done(self, rc: int) -> None:
        self.proc = None
        self.btn_stop.state(["disabled"])
        self.btn_start.state(["!disabled"])
        self.btn_loop_exit.state(["!disabled"])
        if rc == 0:
            self.lbl_status.config(text="* done", fg="#7fc26b")
        else:
            self.lbl_status.config(text=f"* failed (rc={rc})", fg="#d96755")
        self._refresh_validation()
        self.root.after(500, self._update_summary)

    def _log(self, text: str, tag: str | None = None) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", text, tag if tag else ())
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    # Misc
    def copy_command(self) -> None:
        cmd = quote_command(build_command(self._gather_cfg()))
        self.root.clipboard_clear()
        self.root.clipboard_append(cmd)
        self.root.update_idletasks()
        self._log("[copy] Befehl in Zwischenablage kopiert.\n", tag="mute")

    def show_command_dialog(self) -> None:
        cmd = quote_command(build_command(self._gather_cfg()))
        dlg = tk.Toplevel(self.root)
        dlg.title("Befehl-Vorschau")
        dlg.geometry("960x260")
        dlg.configure(bg=self._colors["bg"])
        ttk.Label(dlg, text="Dieser Befehl wird ausgefuehrt:",
                  style="Mute.TLabel"
                  ).pack(anchor="w", padx=12, pady=(10, 4))
        txt = tk.Text(dlg, height=8, bg=self._colors["bg2"],
                      fg=self._colors["fg"], font=("Consolas", 9),
                      borderwidth=0, wrap="word")
        txt.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        txt.insert("1.0", cmd)
        txt.configure(state="disabled")
        bar = ttk.Frame(dlg)
        bar.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(bar, text="In Zwischenablage",
                   command=lambda: (
                       self.root.clipboard_clear(),
                       self.root.clipboard_append(cmd),
                       self.root.update_idletasks(),
                   )).pack(side="left")
        ttk.Button(bar, text="Schliessen", command=dlg.destroy
                   ).pack(side="right")

    def reset_defaults(self) -> None:
        if not messagebox.askyesno("Reset",
                                   "Auf Default-Werte zuruecksetzen?"):
            return
        self.cfg = dict(DEFAULTS)
        save_config(self.cfg)
        self.var_target.set(self.cfg["target"])
        for tf, v in self.tf_vars.items():
            v.set(tf in self.cfg["timeframes"])
        self.var_primary.set(self.cfg["primary"])
        self.var_count.set(str(self.cfg["count"] or ""))
        self.var_min_candles.set(str(self.cfg["min_candles"] or ""))
        self.var_output.set(self.cfg["output"])
        self.var_save_csv.set(self.cfg["save_csv_dir"])
        self.var_min_months.set(str(self.cfg["min_data_months"]))
        self.var_max_hold.set(str(self.cfg["max_holding"]))
        self.var_tp.set(str(self.cfg["tp_atr_mult"]))
        self.var_sl.set(str(self.cfg["sl_atr_mult"]))
        self.var_no_dyn_atr.set(self.cfg["no_dynamic_atr"])
        self.var_dry_run.set(self.cfg["dry_run"])
        self.var_use_csv.set(self.cfg["use_csv_if_present"])
        self.var_exit_csv.set(self.cfg["exit_csv"])
        self.var_exit_required.set(self.cfg["exit_required"])
        self.var_exit_min_samples.set(str(self.cfg["exit_min_samples"]))
        self.var_exit_purge.set(str(self.cfg["exit_purge_gap"]))
        self.var_exit_min_train.set(str(self.cfg["exit_min_train_samples"]))
        self.var_exit_min_test.set(str(self.cfg["exit_min_test_samples"]))
        self.var_loop_iter.set(str(self.cfg["loop_iterations"]))
        self.var_loop_interval.set(str(self.cfg["loop_interval_min"]))
        self.var_loop_refetch.set(self.cfg["loop_refetch"])
        self.var_loop_refetch_years.set(str(self.cfg["loop_refetch_years"]))
        self.var_rebuild_snapshots.set(self.cfg["rebuild_exit_snapshots"])
        self.var_snapshot_tf.set(self.cfg["snapshot_timeframe"])
        self.var_snapshot_stride.set(str(self.cfg["snapshot_stride"]))
        self._refresh()

    def _on_close(self) -> None:
        if self.proc is not None:
            if not messagebox.askyesno(
                    "Training laeuft",
                    "Ein Training laeuft noch. Beenden und Fenster schliessen?"):
                return
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        try:
            save_config(self._gather_cfg())
        except Exception:
            pass
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    TrainingStarterApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
