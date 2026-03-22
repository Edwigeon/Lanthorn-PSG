# gui/fx_ui_manager.py
"""
Unified FX System — Central catalog, waveform preview, and FX editor.
The FX Editor is the 'brain' behind all FX interactions:
 - Instrument Lab: embedded in the modulation rack, replaces GenericModWindow
 - Tracker:        called as a popup from FX column right-click
 - SFX Painter:    called as a popup (future)
"""

import math
import numpy as np
import pyqtgraph as pg

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QDialogButtonBox, QComboBox, QPushButton, QSpinBox,
    QListWidget, QListWidgetItem, QWidget, QGroupBox, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont


# ============================================================
#  CENTRAL FX CATALOG — single source of truth
# ============================================================

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def _semi_label(semitones):
    """Returns a human-readable interval name for a semitone offset."""
    INTERVALS = {
        0: "Unison", 1: "min 2nd", 2: "Maj 2nd", 3: "min 3rd",
        4: "Maj 3rd", 5: "P4", 6: "Tritone", 7: "P5",
        8: "min 6th", 9: "Maj 6th", 10: "min 7th", 11: "Maj 7th",
        12: "Octave", 13: "min 9th", 14: "Maj 9th", 15: "min 10th",
    }
    return INTERVALS.get(semitones, f"+{semitones} semi")


FX_CATALOG = {
    # --- Envelope ---
    "ENV": {
        "name": "ADSR Envelope",
        "category": "📐 Envelope",
        "desc": "Attack / Decay / Sustain Level / Release — shapes the volume over time",
        "param_type": "adsr",
        "adsr_labels": ("Attack  (seconds)", "Decay  (seconds)",
                        "Sustain Level  (0-100%)", "Release  (seconds)"),
        "presets": [("Pluck", "2.10.20.15"), ("Pad", "40.30.70.50"),
                    ("Organ", "1.5.80.10"), ("Swell", "70.20.60.40")],
    },
    # --- Pitch ---
    "ARP": {
        "name": "Arpeggio",
        "category": "🎵 Pitch",
        "desc": "+X,+Y semitones (hi=X, lo=Y)",
        "param_type": "dual",
        "dual_labels": ("Interval 1  (+X semitones)", "Interval 2  (+Y semitones)"),
        "presets": [("Minor 3+5", "55"), ("Major 3+5", "71"),
                    ("Octave", "12"), ("Power 5+Oct", "124")],
        "chord_presets": [
            ("↑ Up (fast)", "04"), ("↑ Up (slow)", "08"),
            ("↓ Down (fast)", "14"), ("↓ Down (slow)", "18"),
            ("↕ Ping-Pong", "24"), ("↕ Ping-Pong (slow)", "28"),
            ("🎲 Random", "34"), ("🎲 Random (slow)", "38"),
        ],
        "chord_desc": "Chord ARP: hi=pattern(0↑1↓2↕3🎲), lo=subdivisions",
        "chord_dual_labels": ("Pattern  (0=↑  1=↓  2=↕  3=🎲)", "Subdivisions  (cycle speed)"),
    },
    "SUP": {
        "name": "Slide Up",
        "category": "🎵 Pitch",
        "desc": "Pitch bend up (0-255 = 0-12 semitones)",
        "param_type": "byte",
        "byte_label": "Pitch Bend Up  (0=None → 255=Full Octave)",
        "presets": [("Subtle", "21"), ("Medium", "64"), ("Deep", "128"), ("Full Octave", "255")],
    },
    "SDN": {
        "name": "Slide Down",
        "category": "🎵 Pitch",
        "desc": "Pitch bend down (0-255 = 0-12 semitones)",
        "param_type": "byte",
        "byte_label": "Pitch Bend Down  (0=None → 255=Full Octave)",
        "presets": [("Subtle", "21"), ("Medium", "64"), ("Deep", "128"), ("Full Octave", "255")],
    },
    "PRT": {
        "name": "Portamento",
        "category": "🎵 Pitch",
        "desc": "Glide to next note",
        "param_type": "byte",
        "byte_label": "Slide Time  (0=Fast → 255=Very Slow)",
        "presets": [("Fast", "32"), ("Medium", "96"), ("Slow", "160"), ("Very Slow", "224")],
    },
    "DTN": {
        "name": "Detune",
        "category": "🎵 Pitch",
        "desc": "Detune in cents",
        "param_type": "byte",
        "byte_label": "Detune  (0=None → 255=50 cents)",
        "presets": [("Slight", "8"), ("Warm", "24"), ("Wide", "64"), ("Extreme", "128")],
    },
    # --- Modulation ---
    "VIB": {
        "name": "Vibrato",
        "category": "🌊 Modulation",
        "desc": "Pitch wobble: hi=speed (1-16 Hz), lo=depth (0-1 semitone)",
        "param_type": "dual",
        "dual_labels": ("Speed  (0=1Hz … F=16Hz)", "Depth  (0=none … F=1 semitone)"),
        "presets": [("Gentle", "36"), ("Standard", "68"), ("Fast", "100"), ("Intense", "136")],
    },
    "TRM": {
        "name": "Tremolo",
        "category": "🌊 Modulation",
        "desc": "Volume wobble: hi=speed, lo=depth",
        "param_type": "dual",
        "dual_labels": ("Speed  (0=1Hz … F=16Hz)", "Depth  (0=none … F=full)"),
        "presets": [("Gentle", "35"), ("Pulse", "70"), ("Fast", "104"), ("Chop", "138")],
    },
    "RNG": {
        "name": "Ring Mod",
        "category": "🌊 Modulation",
        "desc": "Multiplies wave by a carrier — metallic / bell tones",
        "param_type": "byte",
        "byte_label": "Ring Mod Mix  (0=Dry → 255=Full)",
        "presets": [("Touch", "32"), ("Metallic", "96"), ("Harsh", "160"), ("Full", "255")],
    },
    "SAT": {
        "name": "Saturation",
        "category": "🌊 Modulation",
        "desc": "Harmonic drive via tanh waveshaping",
        "param_type": "byte",
        "byte_label": "Saturation  (0=Clean → 255=Heavy Fuzz)",
        "presets": [("Warm", "32"), ("Drive", "96"), ("Crunch", "160"), ("Fuzz", "255")],
    },
    "VMD": {
        "name": "Voice Mod",
        "category": "🌊 Modulation",
        "desc": "Crossfade from OSC1 → OSC2 over the note's gate time",
        "param_type": "dual",
        "dual_labels": ("Target Mix  (0=OSC1 … F=100% OSC2)",
                        "Slide Time  (0=instant … F=full gate)"),
        "presets": [("Quick Morph", "100"), ("Slow Sweep", "143"),
                    ("Full Slide", "255"), ("Half Blend", "136")],
    },
    # --- Master Mix (Global Automation) ---
    "MVL": {
        "name": "Master Volume",
        "category": "🎛 Master Mix",
        "desc": "Instantly set the global song volume (0-255)",
        "param_type": "byte",
        "byte_label": "Master Volume  (0=Silent → 255=Full)",
        "presets": [("Silent", "0"), ("Quiet", "64"), ("Normal", "192"), ("Max", "255")],
    },
    "CVL": {
        "name": "Crescendo Volume",
        "category": "🎛 Master Mix",
        "desc": "Slide master volume to target (0-255) until next command",
        "param_type": "byte",
        "byte_label": "Target Volume  (0=Silent → 255=Full)",
        "presets": [("Fade to 0%", "0"), ("Fade to 25%", "64"),
                    ("Fade to 75%", "192"), ("Fade to 100%", "255")],
    },
    "MPN": {
        "name": "Master Pan",
        "category": "🎛 Master Mix",
        "desc": "Instantly set the global stereo balance (0=L, 128=C, 255=R)",
        "param_type": "byte",
        "byte_label": "Stereo Position  (0=Left, 128=Center, 255=Right)",
        "presets": [("Hard Left", "0"), ("Center", "128"), ("Hard Right", "255")],
    },
    "CPN": {
        "name": "Crescendo Pan",
        "category": "🎛 Master Mix",
        "desc": "Slide master pan to target over duration until next command",
        "param_type": "byte",
        "byte_label": "Target Pan  (0=Left, 128=Center, 255=Right)",
        "presets": [("Sweep to Left", "0"), ("Sweep to Center", "128"), ("Sweep to Right", "255")],
    },
    # --- Dynamics ---
    "VOL": {
        "name": "Volume",
        "category": "🔊 Dynamics",
        "desc": "Volume level (0-255)",
        "param_type": "byte",
        "byte_label": "Volume Level  (0=Silent → 255=Full)",
        "presets": [("Silent", "0"), ("Quiet", "48"), ("Half", "128"), ("Full", "255")],
    },
    "CUT": {
        "name": "Note Cut",
        "category": "🔊 Dynamics",
        "desc": "Delayed cut position",
        "param_type": "byte",
        "byte_label": "Cut Position  (0=Immediate → 255=Near End)",
        "presets": [("Quick", "32"), ("Half", "128"), ("Late", "192"), ("Near End", "240")],
    },
    "PAN": {
        "name": "Pan",
        "category": "🔊 Dynamics",
        "desc": "Stereo position",
        "param_type": "byte",
        "byte_label": "Stereo Position  (0=Left, 128=Center, 255=Right)",
        "presets": [("Hard Left", "0"), ("Left", "64"), ("Center", "128"),
                    ("Right", "192"), ("Hard Right", "255")],
    },
    "RTG": {
        "name": "Retrigger",
        "category": "🔊 Dynamics",
        "desc": "Stutter gate (0-255 = 1-32 Hz)",
        "param_type": "byte",
        "byte_label": "Retrigger Rate  (0=Slow 1Hz → 255=Buzz 32Hz)",
        "presets": [("Slow", "32"), ("Medium", "96"), ("Fast", "160"), ("Buzz", "255")],
    },
    # --- Time ---
    "ECH": {
        "name": "Echo",
        "category": "⏱ Time",
        "desc": "Multi-tap delay: hi=delay × 50ms, lo=feedback",
        "param_type": "dual",
        "dual_labels": ("Delay  (0=50ms … F=750ms)", "Feedback  (0=dry … F=wash)"),
        "presets": [("Short", "34"), ("Medium", "68"), ("Long", "104"), ("Wash", "138")],
    },
    "DLY": {
        "name": "Delay",
        "category": "⏱ Time",
        "desc": "Delay note start",
        "param_type": "byte",
        "byte_label": "Delay Start  (0=None → 255=Late)",
        "presets": [("Nudge", "16"), ("Swing", "64"), ("Half", "128"), ("Late", "192")],
    },
}

# Convenience: list of (display, code, desc) for backward compat with context_menu imports
FX_COMMANDS = [(info["name"], code, info["desc"]) for code, info in FX_CATALOG.items()]

# Build category groupings on import
def get_fx_categories(has_chord=False):
    """Returns FX grouped by category, respecting chord context for ARP."""
    categories = {}
    for code, info in FX_CATALOG.items():
        cat = info["category"]
        if cat not in categories:
            categories[cat] = []
        if code == "ARP" and has_chord:
            presets = info.get("chord_presets", info["presets"])
            desc = info.get("chord_desc", info["desc"])
        else:
            presets = info["presets"]
            desc = info["desc"]
        categories[cat].append((info["name"], code, desc, presets))
    return categories


# ============================================================
#  WAVEFORM PREVIEW GENERATORS — one per effect code
# ============================================================

def _generate_preview_waveform(code, p1, p2, p_full, n=200, adsr_s=None, adsr_r=None):
    """Returns (x, y) numpy arrays for the waveform preview graph."""
    x = np.linspace(0, 4 * math.pi, n)
    base = np.sin(x * 3)  # base waveform at ~3 cycles

    if code == "VIB":
        speed = 1.0 + p1
        depth = p2 / 15.0
        lfo = np.sin(x * speed) * depth * 0.3
        y = np.sin(x * 3 + lfo * 2 * math.pi)
    elif code == "TRM":
        speed = 1.0 + p1
        depth = p2 / 15.0
        lfo = 1.0 - depth * (0.5 * (1.0 + np.sin(x * speed)))
        y = base * lfo
    elif code == "ARP":
        # Show 3-note alternation visualization
        third = n // 3
        f0, f1, f2 = 3.0, 3.0 * (2 ** (p1 / 12.0)), 3.0 * (2 ** (p2 / 12.0))
        seg0 = np.sin(x[:third] * f0)
        seg1 = np.sin(x[third:2*third] * f1)
        seg2 = np.sin(x[2*third:] * f2)
        y = np.concatenate([seg0, seg1, seg2])
    elif code == "SAT":
        gain = 1.0 + (p_full / 255.0) * 10.0
        y = np.tanh(base * gain) / (np.tanh(gain) + 1e-9)
    elif code == "RNG":
        mix = p_full / 255.0
        carrier = np.sin(x * 15)
        y = base * (1.0 - mix) + base * carrier * mix
    elif code == "RTG":
        rate = 1.0 + (p_full / 255.0) * 8.0
        gate = (np.sign(np.sin(x * rate)) + 1) / 2
        y = base * gate
    elif code == "ECH":
        delay_frac = max(0.05, p1 / 15.0)
        feedback = p2 / 15.0
        offset = int(n * delay_frac * 0.3)
        y = base.copy()
        gain = feedback
        for tap in range(4):
            start = offset * (tap + 1)
            if start >= n:
                break
            y[start:] += base[:n - start] * gain
            gain *= feedback
        y = y / (np.max(np.abs(y)) + 1e-9)
    elif code in ("SUP", "SDN"):
        bend = (p_full / 255.0) * 12.0
        direction = 1.0 if code == "SUP" else -1.0
        sweep = x / x[-1] * bend * direction / 12.0
        y = np.sin(x * 3 + sweep * 2 * math.pi)
    elif code == "PRT":
        slide_frac = p_full / 255.0
        slide_pt = max(1, int(slide_frac * n * 0.6))
        freqs = np.ones(n) * 3.0
        freqs[:slide_pt] = np.linspace(2.0, 3.0, slide_pt)
        y = np.sin(x * freqs) * 0.8
    elif code == "DTN":
        cents = (p_full / 255.0) * 50.0
        ratio = 2.0 ** (cents / 1200.0)
        y = np.sin(x * 3) * 0.5 + np.sin(x * 3 * ratio) * 0.5
    elif code == "VMD":
        # Time-based crossfade from OSC1 (sine) to OSC2 (triangle)
        target_mix = p1 / 15.0
        slide_frac = max(0.05, p2 / 15.0)
        # Build a mix envelope that ramps from 0 to target_mix over slide_frac of the note
        slide_end = int(n * slide_frac)
        mix_env = np.zeros(n)
        mix_env[:slide_end] = np.linspace(0, target_mix, slide_end)
        mix_env[slide_end:] = target_mix
        tri = 2.0 * np.abs(2.0 * (x / (2 * math.pi) - np.floor(x / (2 * math.pi) + 0.5))) - 1.0
        y = base * (1.0 - mix_env) + tri * mix_env
    elif code == "VOL":
        y = base * (p_full / 255.0)
    elif code == "CUT":
        cut_pt = int((p_full / 255.0) * n)
        y = base.copy()
        if 0 < cut_pt < n:
            fade = min(10, n - cut_pt)
            y[cut_pt:cut_pt+fade] *= np.linspace(1, 0, fade)
            y[cut_pt+fade:] = 0
    elif code == "DLY":
        shift = int((p_full / 255.0) * n * 0.5)
        y = np.zeros(n)
        if shift < n:
            y[shift:] = base[:n - shift] * 0.8
    elif code == "PAN":
        # Show L/R balance as two overlapping waves
        pan = (p_full - 128) / 128.0
        y = base * max(0.1, 1.0 - abs(pan))
    elif code == "ENV":
        # ADSR envelope shape
        a = max(0.01, p1 / 100.0)
        d = max(0.01, p2 / 100.0)
        s_level = adsr_s if adsr_s is not None else 0.5
        r = adsr_r if adsr_r is not None else 0.3
        # Build classic ADSR shape
        total = a + d + 0.5 + r
        n_a = max(1, int(n * a / total))
        n_d = max(1, int(n * d / total))
        n_s = max(1, int(n * 0.5 / total))
        n_r = n - n_a - n_d - n_s
        seg_a = np.linspace(0, 1.0, n_a)
        seg_d = np.linspace(1.0, s_level, n_d)
        seg_s = np.ones(n_s) * s_level
        seg_r = np.linspace(s_level, 0, max(1, n_r))
        y = np.concatenate([seg_a, seg_d, seg_s, seg_r])[:n]
    else:
        y = base
    return x, y


# ============================================================
#  FX POPUP WINDOW — unified dialog for inserting / editing FX
# ============================================================

class FXPopupWindow(QDialog):
    """
    Unified FX editor with waveform preview and stacking support.

    Callbacks:
        on_apply(fx_string)  — called when OK is pressed; delivers the result string
        on_preview(fx_string) — called when ▶ Preview is pressed; caller plays audio
    """

    def __init__(self, parent=None, on_apply=None, on_preview=None,
                 has_chord=False, initial_value="", show_override=False,
                 inst_fx_chain=None):
        super().__init__(parent)
        self.on_apply = on_apply
        self.on_preview = on_preview
        self.has_chord = has_chord
        self._show_override = show_override
        # Extract the set of FX codes the instrument already uses
        self._inst_fx_codes = set()
        if inst_fx_chain:
            for item in inst_fx_chain:
                parts = item.strip().split()
                if parts:
                    self._inst_fx_codes.add(parts[0].upper())
        self.setWindowTitle("FX Editor")
        self.setMinimumSize(520, 640)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #cccccc; }
            QGroupBox { border: 1px solid #3f3f46; margin-top: 8px; padding-top: 14px; color: #aaa;
                        font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
            QSlider::groove:horizontal { background: #3f3f46; height: 6px; border-radius: 3px; }
            QSlider::handle:horizontal { background: #007acc; width: 14px; margin: -4px 0;
                                         border-radius: 7px; }
            QLabel { color: #cccccc; }
            QSpinBox { background-color: #333; color: #00ff88; border: 1px solid #555;
                       font-family: 'Courier New'; font-size: 12px; padding: 2px; min-width: 45px; }
            QComboBox { background-color: #333; color: #ccc; border: 1px solid #555; padding: 3px; }
            QPushButton { background-color: #3f3f46; color: #ccc; padding: 4px 12px; }
            QPushButton:hover { background-color: #007acc; color: white; }
            QListWidget { background-color: #252526; color: #00ff88; border: 1px solid #3f3f46;
                          font-family: 'Courier New'; font-size: 13px; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # --- 1. WAVEFORM PREVIEW ---
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setFixedHeight(90)
        self.plot_widget.setBackground('#151515')
        self.plot_widget.setYRange(-1.2, 1.2)
        self.plot_widget.hideAxis('bottom')
        self.plot_widget.hideAxis('left')
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_data = self.plot_widget.plot(pen=pg.mkPen('#00FFFF', width=2))
        layout.addWidget(self.plot_widget)

        # --- 2. FX SELECTOR + PARAMS ---
        selector_group = QGroupBox("Effect")
        selector_layout = QVBoxLayout(selector_group)
        selector_layout.setSpacing(4)

        # Effect combo — with category headers
        sel_row = QHBoxLayout()
        self.fx_combo = QComboBox()
        last_cat = None
        for code, info in FX_CATALOG.items():
            cat = info['category']
            if cat != last_cat:
                self.fx_combo.addItem(f"── {cat} ──", None)  # separator
                # Disable the separator item
                idx = self.fx_combo.count() - 1
                self.fx_combo.model().item(idx).setEnabled(False)
                last_cat = cat
            self.fx_combo.addItem(f"  {info['name']}", code)
        self.fx_combo.currentIndexChanged.connect(self._on_fx_selected)
        sel_row.addWidget(QLabel("Effect:"))
        sel_row.addWidget(self.fx_combo, stretch=1)
        selector_layout.addLayout(sel_row)

        # Preset combo
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        preset_row.addWidget(QLabel("Preset:"))
        preset_row.addWidget(self.preset_combo, stretch=1)
        selector_layout.addLayout(preset_row)

        # Description
        self.desc_label = QLabel("")
        self.desc_label.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        self.desc_label.setWordWrap(True)
        selector_layout.addWidget(self.desc_label)

        # Contextual info label (interval names for ARP, Hz for VIB, etc.)
        self.context_label = QLabel("")
        self.context_label.setStyleSheet(
            "color: #55aaff; font-size: 12px; font-weight: bold; font-family: 'Courier New';")
        self.context_label.setWordWrap(True)
        selector_layout.addWidget(self.context_label)

        # Parameter controls container
        self.param_container = QWidget()
        self.param_layout = QVBoxLayout(self.param_container)
        self.param_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.addWidget(self.param_container)

        # Override toggle + Add to stack + Preview buttons
        mode_row = QHBoxLayout()
        self.override_check = QCheckBox("Override")
        self.override_check.setToolTip(
            "Override: replaces the instrument's matching FX\n"
            "Additive: stacks on top of instrument FX")
        self.override_check.setStyleSheet("color: #ff8844; font-size: 11px;")
        mode_row.addWidget(self.override_check)
        mode_row.addStretch()
        if self._show_override:
            selector_layout.addLayout(mode_row)
        else:
            # Still create it but keep hidden so isChecked() always works
            self.override_check.setVisible(False)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Add to Stack")
        btn_add.setStyleSheet(
            "background-color: #007acc; color: white; font-weight: bold; padding: 6px;")
        btn_add.clicked.connect(self._add_to_stack)
        btn_row.addWidget(btn_add)

        self.btn_preview = QPushButton("▶ Preview")
        self.btn_preview.setStyleSheet(
            "background-color: #264f78; color: #55aaff; font-weight: bold; padding: 6px;")
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        btn_row.addWidget(self.btn_preview)
        selector_layout.addLayout(btn_row)

        layout.addWidget(selector_group)

        # --- 3. FX STACK ---
        stack_group = QGroupBox("FX Stack (applied top → bottom)")
        stack_layout = QVBoxLayout(stack_group)

        self.stack_list = QListWidget()
        self.stack_list.setFixedHeight(70)
        stack_layout.addWidget(self.stack_list)

        stack_btn_row = QHBoxLayout()
        btn_remove = QPushButton("Remove")
        btn_remove.clicked.connect(self._remove_from_stack)
        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self._clear_stack)
        stack_btn_row.addWidget(btn_remove)
        stack_btn_row.addWidget(btn_clear)
        stack_btn_row.addStretch()
        stack_layout.addLayout(stack_btn_row)
        layout.addWidget(stack_group)

        # --- 4. OUTPUT + BUTTONS ---
        self.preview_label = QLabel("Output:  --")
        self.preview_label.setStyleSheet(
            "font-family: 'Courier New'; font-size: 15px; color: #00ff88; "
            "font-weight: bold; padding: 6px; background: #151515; border: 1px solid #3f3f46;")
        layout.addWidget(self.preview_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.setStyleSheet(
            "QPushButton { background-color: #333; color: #ccc; padding: 4px 16px; }")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Internal state
        self._slider_widgets = []  # [(slider, spinbox), ...]
        self._current_code = None
        self._current_param_type = None

        # Initialize first FX
        self._on_fx_selected(0)

        # Pre-populate from initial value
        if initial_value and initial_value not in ["--", "---", ""]:
            self._parse_initial(initial_value)

    def _parse_initial(self, fx_string):
        """Parse an existing FX cell value into the stack and pre-select the first FX in the editor."""
        parts = fx_string.split(":")
        first_code = None
        first_val = None
        for part in parts:
            part = part.strip()
            if part and part not in ["--", "---"]:
                self.stack_list.addItem(part)
                # Remember the first valid FX for combo/slider pre-selection
                if first_code is None:
                    tokens = part.split()
                    if len(tokens) >= 1:
                        first_code = tokens[0].upper()
                        first_val = tokens[1] if len(tokens) > 1 else "0"
        self._update_preview()

        # Pre-select the matching FX in the combo and drive sliders
        if first_code and first_code in FX_CATALOG:
            # Find and select the combo item with matching code
            for i in range(self.fx_combo.count()):
                if self.fx_combo.itemData(i) == first_code:
                    self.fx_combo.setCurrentIndex(i)  # triggers _on_fx_selected
                    break

            # Now set the slider values from the parsed parameter
            info = FX_CATALOG[first_code]
            param_type = info["param_type"]
            try:
                if param_type == "dual" and first_val:
                    v = int(first_val)
                    if len(self._slider_widgets) >= 2:
                        self._slider_widgets[0][0].setValue((v >> 4) & 0xF)
                        self._slider_widgets[1][0].setValue(v & 0xF)
                elif param_type == "byte" and first_val:
                    v = int(first_val)
                    if len(self._slider_widgets) >= 1:
                        self._slider_widgets[0][0].setValue(v)
                elif param_type == "adsr" and first_val:
                    adsr_parts = first_val.split(".")
                    for i, p in enumerate(adsr_parts):
                        if i < len(self._slider_widgets):
                            self._slider_widgets[i][0].setValue(int(p))
            except (ValueError, IndexError):
                pass

    # --- FX Selection ---
    def _on_fx_selected(self, index):
        code = self.fx_combo.itemData(index)
        if not code or code not in FX_CATALOG:
            return
        info = FX_CATALOG[code]
        self._current_code = code
        self._current_param_type = info["param_type"]

        # Description
        if code == "ARP" and self.has_chord:
            self.desc_label.setText(info.get("chord_desc", info["desc"]))
        else:
            self.desc_label.setText(info["desc"])

        # Presets
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Custom...", None)
        presets = info.get("chord_presets", info["presets"]) if (
            code == "ARP" and self.has_chord) else info["presets"]
        for label, val in presets:
            self.preset_combo.addItem(f"{label}  ({code} {val})", val)
        self.preset_combo.blockSignals(False)

        # Rebuild sliders
        self._build_param_controls(code, info)
        self._update_context_and_waveform()

        # Intelligently show/hide Override checkbox
        if self._show_override:
            self.override_check.setVisible(code in self._inst_fx_codes)

    def _on_preset_selected(self, index):
        val = self.preset_combo.itemData(index)
        if val is None:
            return
        try:
            v = int(val)
        except (ValueError, TypeError):
            return
        if self._current_param_type == "dual" and len(self._slider_widgets) >= 2:
            self._slider_widgets[0][0].setValue((v >> 4) & 0xF)
            self._slider_widgets[1][0].setValue(v & 0xF)
        elif self._current_param_type == "byte" and len(self._slider_widgets) >= 1:
            self._slider_widgets[0][0].setValue(v)
        elif self._current_param_type == "adsr":
            # Presets stored as "A.D.S.R" e.g. "5.20.50.30"
            parts = val.split(".") if isinstance(val, str) else []
            for i, part in enumerate(parts):
                if i < len(self._slider_widgets):
                    try:
                        self._slider_widgets[i][0].setValue(int(part))
                    except ValueError:
                        pass

    # --- Build Parameter Controls ---
    def _build_param_controls(self, code, info):
        self._slider_widgets = []
        while self.param_layout.count():
            child = self.param_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                while child.layout().count():
                    sub = child.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        param_type = info["param_type"]

        if param_type == "dual":
            # Use chord-specific labels for ARP when applicable
            if code == "ARP" and self.has_chord:
                labels = info.get("chord_dual_labels", info.get("dual_labels", ("High", "Low")))
            else:
                labels = info.get("dual_labels", ("High", "Low"))

            for i, label_text in enumerate(labels):
                row = QHBoxLayout()
                lbl = QLabel(f"{'Hi' if i == 0 else 'Lo'}: {label_text}")
                lbl.setStyleSheet("color: #aaa; font-size: 11px;")
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(0, 15)
                slider.setValue(0)
                spin = QSpinBox()
                spin.setRange(0, 15)
                row.addWidget(lbl, 3)
                row.addWidget(slider, 4)
                row.addWidget(spin, 1)

                slider.valueChanged.connect(spin.setValue)
                spin.valueChanged.connect(slider.setValue)
                slider.valueChanged.connect(self._update_context_and_waveform)

                container = QWidget()
                container.setLayout(row)
                self.param_layout.addWidget(container)
                self._slider_widgets.append((slider, spin))

        elif param_type == "byte":
            label_text = info.get("byte_label", "Parameter (0-255)")
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            self.param_layout.addWidget(lbl)

            row = QHBoxLayout()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 255)
            slider.setValue(0)
            spin = QSpinBox()
            spin.setRange(0, 255)
            row.addWidget(slider, 5)
            row.addWidget(spin, 1)

            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            slider.valueChanged.connect(self._update_context_and_waveform)

            container = QWidget()
            container.setLayout(row)
            self.param_layout.addWidget(container)
            self._slider_widgets.append((slider, spin))

        elif param_type == "adsr":
            labels = info.get("adsr_labels",
                              ("Attack", "Decay", "Sustain Level", "Release"))
            defaults = [5, 20, 50, 30]  # sensible init values
            for i, label_text in enumerate(labels):
                row = QHBoxLayout()
                short = ["A", "D", "S", "R"][i]
                lbl = QLabel(f"{short}: {label_text}")
                lbl.setStyleSheet("color: #aaa; font-size: 11px;")
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(0, 100)
                slider.setValue(defaults[i])
                spin = QSpinBox()
                spin.setRange(0, 100)
                spin.setValue(defaults[i])
                row.addWidget(lbl, 3)
                row.addWidget(slider, 4)
                row.addWidget(spin, 1)

                slider.valueChanged.connect(spin.setValue)
                spin.valueChanged.connect(slider.setValue)
                slider.valueChanged.connect(self._update_context_and_waveform)

                container = QWidget()
                container.setLayout(row)
                self.param_layout.addWidget(container)
                self._slider_widgets.append((slider, spin))

    # --- Contextual Info + Waveform ---
    def _update_context_and_waveform(self, *_):
        """Updates both the context label and waveform when sliders change."""
        code = self._current_code
        if not code:
            return

        p1, p2, p_full = self._get_params()

        # --- Context-specific labels ---
        if code == "ARP" and not self.has_chord:
            # Show interval names: "Root → +X (P5) → +Y (Octave)"
            name1 = _semi_label(p1)
            name2 = _semi_label(p2)
            self.context_label.setText(
                f"Root  →  +{p1} ({name1})  →  +{p2} ({name2})")
        elif code == "ARP" and self.has_chord:
            patterns = {0: "↑ Up", 1: "↓ Down", 2: "↕ Ping-Pong", 3: "🎲 Random"}
            pat = patterns.get(p1, f"Pattern {p1}")
            self.context_label.setText(f"Pattern: {pat}   Subdivisions: {p2}")
        elif code == "VIB":
            hz = 1.0 + p1
            semi = p2 / 15.0
            self.context_label.setText(f"Speed: {hz:.0f} Hz    Depth: {semi:.2f} semitones")
        elif code == "TRM":
            hz = 1.0 + p1
            depth = p2 / 15.0 * 100
            self.context_label.setText(f"Speed: {hz:.0f} Hz    Depth: {depth:.0f}%")
        elif code == "ECH":
            delay_ms = max(50, p1 * 50)
            fb_pct = p2 / 15.0 * 100
            self.context_label.setText(f"Delay: {delay_ms}ms    Feedback: {fb_pct:.0f}%")
        elif code == "SAT":
            gain = 1.0 + (p_full / 255.0) * 4.0
            self.context_label.setText(f"Drive Gain: {gain:.1f}x")
        elif code == "RTG":
            hz = 1.0 + (p_full / 255.0) * 31.0
            self.context_label.setText(f"Gate Rate: {hz:.1f} Hz")
        elif code == "DTN":
            cents = (p_full / 255.0) * 50.0
            self.context_label.setText(f"Detune: {cents:.1f} cents")
        elif code == "VOL":
            pct = p_full / 255.0 * 100
            self.context_label.setText(f"Volume: {pct:.0f}%")
        elif code in ("SUP", "SDN"):
            semi = (p_full / 255.0) * 12.0
            self.context_label.setText(
                f"Bend: {semi:.1f} semitones {'up' if code == 'SUP' else 'down'}")
        elif code == "PAN":
            if p_full < 120:
                self.context_label.setText(f"Pan: Left {(128 - p_full) / 1.28:.0f}%")
            elif p_full > 136:
                self.context_label.setText(f"Pan: Right {(p_full - 128) / 1.27:.0f}%")
            else:
                self.context_label.setText("Pan: Center")
        elif code == "VMD":
            target_pct = p1 / 15.0 * 100
            slide_pct = p2 / 15.0 * 100
            self.context_label.setText(
                f"Target: {target_pct:.0f}% OSC2    Slide: {slide_pct:.0f}% of gate")
        elif code == "ENV":
            if len(self._slider_widgets) >= 4:
                a = self._slider_widgets[0][0].value() / 100.0
                d = self._slider_widgets[1][0].value() / 100.0
                s = self._slider_widgets[2][0].value()
                r = self._slider_widgets[3][0].value() / 100.0
                self.context_label.setText(
                    f"A: {a:.2f}s   D: {d:.2f}s   S: {s}%   R: {r:.2f}s")
            else:
                self.context_label.setText("")
        else:
            self.context_label.setText("")

        # --- Update waveform preview ---
        if code == "ENV" and len(self._slider_widgets) >= 4:
            a_val = self._slider_widgets[0][0].value()
            d_val = self._slider_widgets[1][0].value()
            s_val = self._slider_widgets[2][0].value()
            r_val = self._slider_widgets[3][0].value()
            x, y = _generate_preview_waveform(code, a_val, d_val, s_val,
                                               adsr_s=s_val / 100.0, adsr_r=r_val / 100.0)
        else:
            x, y = _generate_preview_waveform(code, p1, p2, p_full)
        self.plot_data.setData(x, y)

        # --- Update text preview ---
        self._update_param_preview()

    def _get_params(self):
        """Returns (p1, p2, p_full) from current slider state."""
        if self._current_param_type == "dual" and len(self._slider_widgets) >= 2:
            p1 = self._slider_widgets[0][0].value()
            p2 = self._slider_widgets[1][0].value()
            p_full = (p1 << 4) | p2
        elif self._current_param_type == "byte" and len(self._slider_widgets) >= 1:
            p_full = self._slider_widgets[0][0].value()
            p1 = (p_full >> 4) & 0xF
            p2 = p_full & 0xF
        elif self._current_param_type == "adsr" and len(self._slider_widgets) >= 4:
            p1 = self._slider_widgets[0][0].value()
            p2 = self._slider_widgets[1][0].value()
            p_full = 0  # not used for ADSR
        else:
            p1, p2, p_full = 0, 0, 0
        return p1, p2, p_full

    def _get_current_fx_string(self):
        code = self._current_code
        if not code:
            return ""
        if self._current_param_type == "adsr" and len(self._slider_widgets) >= 4:
            vals = [self._slider_widgets[i][0].value() for i in range(4)]
            return f"{code} {vals[0]}.{vals[1]}.{vals[2]}.{vals[3]}"
        _, _, p_full = self._get_params()
        return f"{code} {p_full}"

    # --- Preview ---
    def _update_param_preview(self, *_):
        current_fx = self._get_current_fx_string()
        stack_items = [self.stack_list.item(i).text() for i in range(self.stack_list.count())]
        if stack_items:
            combined = " : ".join(stack_items + [current_fx])
        else:
            combined = current_fx
        self.preview_label.setText(f"Output:  {combined}")

    def _update_preview(self):
        stack_items = [self.stack_list.item(i).text() for i in range(self.stack_list.count())]
        if stack_items:
            self.preview_label.setText(f"Output:  {' : '.join(stack_items)}")
        else:
            self.preview_label.setText("Output:  --")

    def _on_preview_clicked(self):
        """Fires the on_preview callback with the current FX string."""
        if self.on_preview:
            fx_str = self._get_current_fx_string()
            self.on_preview(fx_str)

    # --- Stack ---
    def _add_to_stack(self):
        fx_str = self._get_current_fx_string()
        if fx_str:
            if self.override_check.isChecked():
                fx_str = "!" + fx_str
            self.stack_list.addItem(fx_str)
            self._update_preview()

    def _remove_from_stack(self):
        row = self.stack_list.currentRow()
        if row >= 0:
            self.stack_list.takeItem(row)
            self._update_preview()

    def _clear_stack(self):
        self.stack_list.clear()
        self._update_preview()

    # --- Accept ---
    def _accept(self):
        items = [self.stack_list.item(i).text() for i in range(self.stack_list.count())]
        if not items:
            fx_str = self._get_current_fx_string()
            if fx_str:
                items = [fx_str]
        result = " : ".join(items) if items else "--"
        if self.on_apply:
            self.on_apply(result)
        self.accept()
