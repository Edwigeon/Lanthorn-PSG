# gui/retro_visualizer.py
# Retro Visualizer — Standalone Project Player
# Renders a DOS/C64/ZX-style scrolling tracker with live audio playback.

import csv
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
import sounddevice as sd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDialog, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPainter, QColor, QKeyEvent, QPen, QFontMetrics, QImage

from engine.theory import Theory
from engine.playback import Sequencer
from engine.preset_manager import PresetManager

# ─────────────────────────────────────────────────────────────────
# THEMES
# ─────────────────────────────────────────────────────────────────

class RetroTheme:
    """Data class holding color palette and font info for a retro theme."""

    THEMES = {
        "MS-DOS": {
            "name":       "MS-DOS",
            "bg":         "#000000",
            "text":       "#AAAAAA",
            "highlight":  "#FFFF55",
            "note":       "#55FF55",
            "inst":       "#FFFF55",
            "fx":         "#55FFFF",
            "vel_gate":   "#AAAAAA",
            "header_bg":  "#0000AA",
            "header_text":"#FFFFFF",
            "border":     "#555555",
            "row_num":    "#555555",
            "active_row": "#1A1A3A",
            "empty":      "#333333",
            "font":       "Consolas",
            "font_size":  13,
            "border_h":   "═",
            "border_v":   "║",
            "corner_tl":  "╔", "corner_tr": "╗",
            "corner_bl":  "╚", "corner_br": "╝",
        },
        "Commodore 64": {
            "name":       "Commodore 64",
            "bg":         "#40318D",
            "text":       "#7869C4",
            "highlight":  "#A5A5FF",
            "note":       "#A5A5FF",
            "inst":       "#CBE29A",
            "fx":         "#8CE0AA",
            "vel_gate":   "#7B7B7B",
            "header_bg":  "#352879",
            "header_text":"#A5A5FF",
            "border":     "#6C5EB5",
            "row_num":    "#6C5EB5",
            "active_row": "#5040A0",
            "empty":      "#504090",
            "font":       "Courier New",
            "font_size":  13,
            "border_h":   "▀",
            "border_v":   "▌",
            "corner_tl":  "▛", "corner_tr": "▜",
            "corner_bl":  "▙", "corner_br": "▟",
        },
        "ZX Spectrum": {
            "name":       "ZX Spectrum",
            "bg":         "#000000",
            "text":       "#CACACA",
            "highlight":  "#FFFF00",
            "note":       "#00FF00",
            "inst":       "#FF0000",
            "fx":         "#00FFFF",
            "vel_gate":   "#FF00FF",
            "header_bg":  "#0000D7",
            "header_text":"#FFFFFF",
            "border":     "#D7D7D7",
            "row_num":    "#D7D700",
            "active_row": "#00007B",
            "empty":      "#3B3B3B",
            "font":       "Courier New",
            "font_size":  13,
            "border_h":   "─",
            "border_v":   "│",
            "corner_tl":  "┌", "corner_tr": "┐",
            "corner_bl":  "└", "corner_br": "┘",
        },
        "Amiga": {
            "name":       "Amiga",
            "bg":         "#4455AA",
            "text":       "#AAAACC",
            "highlight":  "#FFFFFF",
            "note":       "#FFCC00",
            "inst":       "#FF8800",
            "fx":         "#88CCFF",
            "vel_gate":   "#BBBBCC",
            "header_bg":  "#2233AA",
            "header_text":"#FFFFFF",
            "border":     "#7788CC",
            "row_num":    "#7788CC",
            "active_row": "#3344BB",
            "empty":      "#5566AA",
            "font":       "Consolas",
            "font_size":  13,
            "border_h":   "─",
            "border_v":   "│",
            "corner_tl":  "┌", "corner_tr": "┐",
            "corner_bl":  "└", "corner_br": "┘",
        },
        "Apple II": {
            "name":       "Apple II",
            "bg":         "#000000",
            "text":       "#33FF33",
            "highlight":  "#FFFFFF",
            "note":       "#33FF33",
            "inst":       "#33FF33",
            "fx":         "#33FF33",
            "vel_gate":   "#22CC22",
            "header_bg":  "#003300",
            "header_text":"#33FF33",
            "border":     "#116611",
            "row_num":    "#116611",
            "active_row": "#003300",
            "empty":      "#0A3A0A",
            "font":       "Courier New",
            "font_size":  13,
            "border_h":   "─",
            "border_v":   "│",
            "corner_tl":  "┌", "corner_tr": "┐",
            "corner_bl":  "└", "corner_br": "┘",
        },
        "Atari ST": {
            "name":       "Atari ST",
            "bg":         "#FFFFFF",
            "text":       "#000000",
            "highlight":  "#FF0000",
            "note":       "#000000",
            "inst":       "#008800",
            "fx":         "#0000CC",
            "vel_gate":   "#444444",
            "header_bg":  "#00AA00",
            "header_text":"#FFFFFF",
            "border":     "#888888",
            "row_num":    "#888888",
            "active_row": "#CCDDCC",
            "empty":      "#CCCCCC",
            "font":       "Consolas",
            "font_size":  13,
            "border_h":   "─",
            "border_v":   "│",
            "corner_tl":  "┌", "corner_tr": "┐",
            "corner_bl":  "└", "corner_br": "┘",
        },
        "VT100": {
            "name":       "VT100",
            "bg":         "#000000",
            "text":       "#FF8800",
            "highlight":  "#FFCC00",
            "note":       "#FF8800",
            "inst":       "#FFAA33",
            "fx":         "#FFCC00",
            "vel_gate":   "#CC6600",
            "header_bg":  "#221100",
            "header_text":"#FF8800",
            "border":     "#663300",
            "row_num":    "#663300",
            "active_row": "#331A00",
            "empty":      "#2A1500",
            "font":       "Consolas",
            "font_size":  13,
            "border_h":   "═",
            "border_v":   "║",
            "corner_tl":  "╔", "corner_tr": "╗",
            "corner_bl":  "╚", "corner_br": "╝",
        },
    }

    def __init__(self, name="MS-DOS"):
        data = self.THEMES.get(name, self.THEMES["MS-DOS"])
        for k, v in data.items():
            setattr(self, k, v)

# ─────────────────────────────────────────────────────────────────
# V1.1 CSV PARSER
# ─────────────────────────────────────────────────────────────────

class VisualizerDataParser:
    """Parses a LANTHORN_V1.1 CSV file into playback-ready data structures."""

    def __init__(self):
        self.tracks = 8
        self.sub_cols = 7
        self.bpm = 120
        self.lpb = 4
        self.lpm = 16
        self.key = "C"
        self.mode = "Chromatic"
        self.patches = {}          # {inst_name: {json_data}}
        self.order_list = []       # [pat_id, ...]
        self.pattern_lengths = {}  # {pat_id: int}
        self.pattern_meta = {}     # {pat_id: {bpm, lpb, lpm, key, mode}}
        self.pattern_names = {}    # {pat_id: display_name}
        self.timeline = {}         # {pat_id: {row: [event_dicts]}}
        self._current_pattern = None  # Tracks which pattern events belong to

    def parse(self, filepath):
        """Parse the CSV file and populate all data structures."""
        with open(filepath, 'r', newline='') as f:
            reader = csv.reader(f)
            rows = list(reader)

        for row in rows:
            if not row:
                continue
            tag = row[0].strip()

            # ── HEADER ──
            if tag == "LANTHORN_V1.1":
                self._parse_header(row)
                continue

            # ── SECTION MARKERS ──
            if tag.startswith("--- ORDER") or tag.startswith("--- PATTERN"):
                continue

            # ── PATCH ──
            if tag == "PATCH" and len(row) >= 3:
                name = row[1].strip()
                try:
                    self.patches[name] = json.loads(row[2])
                except (json.JSONDecodeError, IndexError):
                    pass
                continue

            # ── ORDER LIST ──
            if tag == "SEQ" and len(row) >= 3:
                self.order_list.append(row[2].strip())
                continue

            # ── PATTERN HEADER ──
            if tag == "PATTERN" and len(row) >= 3:
                pat_id = row[1].strip()
                pat_len = int(row[2])
                self.pattern_lengths[pat_id] = pat_len
                self.timeline[pat_id] = {}
                self._current_pattern = pat_id
                # Per-pattern overrides
                meta = {}
                if len(row) > 3 and row[3].strip():
                    try: meta["bpm"] = int(row[3])
                    except ValueError: pass
                if len(row) > 4 and row[4].strip():
                    try: meta["lpb"] = int(row[4])
                    except ValueError: pass
                if len(row) > 5 and row[5].strip():
                    try: meta["lpm"] = int(row[5])
                    except ValueError: pass
                if len(row) > 6 and row[6].strip():
                    meta["key"] = row[6].strip()
                if len(row) > 7 and row[7].strip():
                    meta["mode"] = row[7].strip()
                if meta:
                    self.pattern_meta[pat_id] = meta
                # Custom name (position 8)
                if len(row) > 8 and row[8].strip():
                    self.pattern_names[pat_id] = row[8].strip()
                else:
                    self.pattern_names[pat_id] = pat_id
                continue

            # ── EVENT ──
            if tag == "EVENT" and len(row) >= 5:
                self._parse_event(row)
                continue

    def _parse_header(self, row):
        try:
            self.tracks = int(row[1]) if len(row) > 1 else 8
            self.sub_cols = int(row[2]) if len(row) > 2 else 7
            self.bpm = int(row[3]) if len(row) > 3 else 120
            self.lpb = int(row[4]) if len(row) > 4 else 4
            self.key = row[5].strip() if len(row) > 5 else "C"
            self.mode = row[6].strip() if len(row) > 6 else "Chromatic"
            self.lpm = int(row[7]) if len(row) > 7 else 16
        except (ValueError, IndexError):
            pass

    def _parse_event(self, row):
        """Parse EVENT, row, track, note, inst, vel, gate, fx1, fx2"""
        try:
            r = int(row[1])
            t = int(row[2])
        except (ValueError, IndexError):
            return

        note = row[3].strip() if len(row) > 3 else ""
        inst = row[4].strip() if len(row) > 4 else ""
        vel = row[5].strip() if len(row) > 5 else ""
        gate = row[6].strip() if len(row) > 6 else ""
        fx1 = row[7].strip() if len(row) > 7 else ""
        fx2 = row[8].strip() if len(row) > 8 else ""

        pat_id = self._current_pattern
        if pat_id is None:
            return

        if r not in self.timeline[pat_id]:
            self.timeline[pat_id][r] = []

        self.timeline[pat_id][r].append({
            "track": t,
            "note": note,
            "inst": inst,
            "vel": vel,
            "gate": gate,
            "fx1": fx1,
            "fx2": fx2,
        })

    def get_bpm_for_pattern(self, pat_id):
        return self.pattern_meta.get(pat_id, {}).get("bpm", self.bpm)

    def get_lpb_for_pattern(self, pat_id):
        return self.pattern_meta.get(pat_id, {}).get("lpb", self.lpb)

    def get_key_for_pattern(self, pat_id):
        return self.pattern_meta.get(pat_id, {}).get("key", self.key)

    def get_mode_for_pattern(self, pat_id):
        return self.pattern_meta.get(pat_id, {}).get("mode", self.mode)

    def get_lpm_for_pattern(self, pat_id):
        return self.pattern_meta.get(pat_id, {}).get("lpm", self.lpm)

    # ── AUDIO: Build Sequencer-compatible track dicts ──

    def build_tracks_for_pattern(self, pat_id):
        """Converts parsed CSV events into Sequencer track dicts for rendering."""
        pm = PresetManager()
        default_patch = pm.get_default_patch()
        pat_len = self.pattern_lengths.get(pat_id, 64)
        events_by_row = self.timeline.get(pat_id, {})

        # Reorganize events by track
        track_events = {}  # track_idx -> [(row, event_dict)]
        for r in range(pat_len):
            for ev in events_by_row.get(r, []):
                ti = ev["track"]
                if ti not in track_events:
                    track_events[ti] = []
                track_events[ti].append((r, ev))

        tracks = []
        for t in range(self.tracks):
            sequence = []
            track_patch = default_patch
            standalone_pan = []
            standalone_vol = []

            for r, ev in track_events.get(t, []):
                note_str = ev.get("note", "")
                inst_str = ev.get("inst", "")
                vel_str = ev.get("vel", "")
                gate_str = ev.get("gate", "")
                fx1_str = ev.get("fx1", "")
                fx2_str = ev.get("fx2", "")

                # NOTE OFF
                if note_str == "OFF":
                    sequence.append({"step": r, "note": "OFF"})
                    continue

                # Empty note — check for standalone PAN/VOL
                if not note_str or note_str in ("---", "--", ""):
                    for fxc in (fx1_str, fx2_str):
                        if isinstance(fxc, str) and fxc.startswith("PAN "):
                            try:
                                pv = int(fxc[4:])
                                standalone_pan.append({"step": r, "value": (pv / 127.5) - 1.0})
                            except ValueError:
                                pass
                        elif isinstance(fxc, str) and fxc.startswith("VOL "):
                            try:
                                pv = int(fxc[4:])
                                standalone_vol.append({"step": r, "level": pv / 255.0})
                            except ValueError:
                                pass
                    continue

                # Resolve instrument patch
                if inst_str and inst_str not in ("---", "--", ""):
                    if inst_str in self.patches:
                        track_patch = self.patches[inst_str]

                # Velocity
                try:
                    vel = int(vel_str) / 127.0 if vel_str and vel_str not in ("--", "---") else 0.8
                except ValueError:
                    vel = 0.8

                # Gate
                try:
                    gate = int(gate_str) if gate_str and gate_str not in ("--", "---") else 2
                except ValueError:
                    gate = 2

                # Notes (chord support)
                if "," in note_str:
                    midi_notes = []
                    for ns in note_str.split(","):
                        mn = Theory.string_to_midi(ns.strip())
                        if mn >= 0:
                            midi_notes.append(mn)
                    if not midi_notes:
                        continue
                    note_val = midi_notes if len(midi_notes) > 1 else midi_notes[0]
                else:
                    midi_note = Theory.string_to_midi(note_str)
                    if midi_note < 0:
                        continue
                    note_val = midi_note

                event = {
                    "step": r,
                    "note": note_val,
                    "velocity": vel,
                    "gate": gate,
                    "patch": track_patch,
                }
                if fx1_str and fx1_str not in ("--", "---"):
                    event["fx1"] = fx1_str
                if fx2_str and fx2_str not in ("--", "---"):
                    event["fx2"] = fx2_str
                sequence.append(event)

            # Extract PAN/VOL automation from events
            pan_kf = []
            vol_kf = []
            for evt in sequence:
                for fx_key in ("fx1", "fx2"):
                    fx_str = evt.get(fx_key, "")
                    if isinstance(fx_str, str) and fx_str.startswith("PAN "):
                        try:
                            dec_val = int(fx_str[4:])
                            pan_kf.append({"step": evt["step"], "value": (dec_val / 127.5) - 1.0})
                            del evt[fx_key]
                        except (ValueError, KeyError):
                            pass
                    elif isinstance(fx_str, str) and fx_str.startswith("VOL "):
                        try:
                            dec_val = int(fx_str[4:])
                            vol_kf.append({"step": evt["step"], "level": dec_val / 255.0})
                            del evt[fx_key]
                        except (ValueError, KeyError):
                            pass

            all_pan = pan_kf + standalone_pan
            all_vol = vol_kf + standalone_vol
            track_dict = {"patch": track_patch, "sequence": sequence}
            if all_pan:
                all_pan.sort(key=lambda kf: kf["step"])
                track_dict["pan_automation"] = all_pan
            if all_vol:
                all_vol.sort(key=lambda kf: kf["step"])
                track_dict["track_volume"] = all_vol
            tracks.append(track_dict)
        return tracks


# ─────────────────────────────────────────────────────────────────
# COLUMN LAYOUT & TRUNCATION
# ─────────────────────────────────────────────────────────────────
# All data truncated to 3 characters — clean hard cut, no ** suffix.
# Spacing: 1-char gap between each column for legibility.
# Each track: Nte  Ins  Vel  Gt  FX1  FX2
#              3    3    3    2   3    3  = 17 data + 5 gaps = 22
# + 1 char divider per track boundary

COL_NOTE = 3   # "C-4" or "OFF"
COL_INST = 3   # "Led" or "Bas"
COL_VEL  = 3   # "255"
COL_GATE = 2   # "16"
COL_FX   = 3   # "VIB" or "──"

# 3+1+3+1+3+1+2+1+3+1+3 = 22 chars per track
TRACK_INNER = COL_NOTE + COL_INST + COL_VEL + COL_GATE + COL_FX * 2 + 5  # 22
TRACK_DIVIDER = "║"  # Solid track separator


def _trunc(text, width):
    """Fit text to width — pad or truncate as needed."""
    if not text or text in ("---", "--", ""):
        return "·" * min(width, 3)
    text = text.strip()
    return text[:width]


# ─────────────────────────────────────────────────────────────────
# TRACK LEVEL METERS
# ─────────────────────────────────────────────────────────────────

class TrackLevelMeters:
    """8-channel VU meter bars driven by audio RMS with decay."""

    def __init__(self, num_tracks=8):
        self.num_tracks = num_tracks
        self.levels = [0.0] * num_tracks

    def set_level(self, track_idx, level):
        """Set a track's level directly from an RMS value (0.0-1.0)."""
        if 0 <= track_idx < self.num_tracks:
            self.levels[track_idx] = max(self.levels[track_idx], min(1.0, level))

    def tick(self):
        for i in range(self.num_tracks):
            self.levels[i] = max(0.0, self.levels[i] - 0.06)

    def render(self, width=5):
        result = []
        for level in self.levels:
            filled = round(level * width)
            bar = "█" * filled + "·" * (width - filled)
            result.append(bar)
        return result


# ─────────────────────────────────────────────────────────────────
# REAL-AUDIO ASCII OSCILLOSCOPE
# ─────────────────────────────────────────────────────────────────

def render_ascii_oscilloscope(audio, sample_pos, width=160, height=5):
    """
    Renders a per-track oscilloscope using half-block characters (▀▄█).
    Each character cell represents two vertical sub-pixels.
    Dynamically scales amplitude to fill the vertical space.
    """
    sub_h = height * 2
    canvas = [[' '] * width for _ in range(height)]
    mid_sub = sub_h // 2

    if audio is None or len(audio) == 0 or sample_pos < 0:
        char_row = mid_sub // 2
        ch = '▀' if (mid_sub % 2) == 0 else '▄'
        for x in range(width):
            canvas[char_row][x] = ch
        return [''.join(row) for row in canvas]

    mono = audio[:, 0] if audio.ndim == 2 else audio
    total_samples = len(mono)

    window_half = 1200
    start = max(0, sample_pos - window_half)
    end = min(total_samples, sample_pos + window_half)
    chunk = mono[start:end]

    if len(chunk) == 0:
        char_row = mid_sub // 2
        ch = '▀' if (mid_sub % 2) == 0 else '▄'
        for x in range(width):
            canvas[char_row][x] = ch
        return [''.join(row) for row in canvas]

    step = max(1, len(chunk) // width)

    # Dynamic amplitude scaling: normalize to the peak of this chunk
    peak = float(np.max(np.abs(chunk)))
    if peak < 0.01:
        peak = 1.0  # silence: don't amplify noise
    scale = 0.95 / peak  # fill ~95% of vertical range

    # Build sub-pixel bitmap
    sub_bitmap = [[False] * width for _ in range(sub_h)]

    for x in range(width):
        col_start = x * step
        col_end = min(col_start + step, len(chunk))
        segment = chunk[col_start:col_end]
        if len(segment) == 0:
            continue
        val = float(np.clip(np.mean(segment) * scale, -1.0, 1.0))
        sub_row = int(round((1.0 - val) * 0.5 * (sub_h - 1)))
        sub_row = max(0, min(sub_h - 1, sub_row))
        sub_bitmap[sub_row][x] = True

    # Convert sub-pixel bitmap to half-block characters
    for cr in range(height):
        upper_sub = cr * 2
        lower_sub = cr * 2 + 1
        for x in range(width):
            has_upper = upper_sub < sub_h and sub_bitmap[upper_sub][x]
            has_lower = lower_sub < sub_h and sub_bitmap[lower_sub][x]
            if has_upper and has_lower:
                canvas[cr][x] = '█'
            elif has_upper:
                canvas[cr][x] = '▀'
            elif has_lower:
                canvas[cr][x] = '▄'

    return [''.join(row) for row in canvas]


# ─────────────────────────────────────────────────────────────────
# LAUNCH DIALOG
# ─────────────────────────────────────────────────────────────────

class RetroVisualizerLaunchDialog(QDialog):
    """Pre-launch dialog for choosing theme and confirming project file."""

    def __init__(self, parent=None, csv_path=None):
        super().__init__(parent)
        self.setWindowTitle("🖥️ Retro Visualizer")
        self.setMinimumSize(420, 260)
        self.setStyleSheet("""
            QDialog { background: #1e1e1e; color: #cccccc; }
            QLabel { color: #cccccc; font-size: 13px; }
            QComboBox { background: #2d2d30; color: #cccccc; border: 1px solid #3f3f46;
                        padding: 6px; font-size: 13px; min-width: 200px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #2d2d30; color: #cccccc;
                                          selection-background-color: #007acc; }
            QPushButton { background: #264f78; color: white; border: none;
                          padding: 10px 24px; font-size: 14px; font-weight: bold;
                          border-radius: 4px; }
            QPushButton:hover { background: #1177bb; }
            QPushButton#cancel { background: #3f3f46; }
            QPushButton#cancel:hover { background: #555555; }
            QPushButton#browse { background: #3f3f46; padding: 8px 14px; font-size: 12px; }
        """)

        self.csv_path = csv_path or ""
        self.selected_theme = "MS-DOS"

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel("🖥️  Retro Visualizer")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #55aaff;")
        layout.addWidget(title)

        # Display mode selector (at top for immediate selection)
        display_row = QHBoxLayout()
        display_row.addWidget(QLabel("Display:"))
        self.display_combo = QComboBox()
        self.display_combo.addItems([label for _, label in DISPLAY_MODES])
        self.selected_display_mode = 0  # default: maximized
        self.display_combo.currentIndexChanged.connect(self._on_display_changed)
        display_row.addWidget(self.display_combo, 1)
        layout.addLayout(display_row)

        # Project file row
        file_row = QHBoxLayout()
        self.file_label = QLabel(self._short_path(self.csv_path) or "No project loaded")
        self.file_label.setStyleSheet("color: #888888; font-size: 12px;")
        file_row.addWidget(QLabel("Project:"))
        file_row.addWidget(self.file_label, 1)
        browse_btn = QPushButton("📂 Browse")
        browse_btn.setObjectName("browse")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # Theme selector
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(RetroTheme.THEMES.keys()))
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo, 1)
        layout.addLayout(theme_row)

        # Export settings
        export_group_label = QLabel("── MP4 Export ──")
        export_group_label.setStyleSheet("color: #888; font-size: 11px; margin-top: 8px;")
        layout.addWidget(export_group_label)

        export_row = QHBoxLayout()
        export_row.addWidget(QLabel("1080p"))
        export_row.addWidget(QLabel("FPS:"))
        self.fps_combo = QComboBox()
        self.fps_combo.addItem("30", 30)
        self.fps_combo.addItem("15 (fast)", 15)
        export_row.addWidget(self.fps_combo)

        export_btn = QPushButton("[>>]  Export MP4")
        export_btn.setStyleSheet(
            "background-color: #264f78; color: #55aaff; font-weight: bold; padding: 5px 12px;")
        export_btn.clicked.connect(self._export_mp4)
        export_row.addWidget(export_btn)
        layout.addLayout(export_row)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        launch_btn = QPushButton("[>>]  Launch Visualizer")
        launch_btn.clicked.connect(self.accept)
        btn_row.addWidget(launch_btn)
        layout.addLayout(btn_row)

    def _short_path(self, path):
        return os.path.basename(path) if path else ""

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Lanthorn CSV (*.csv)")
        if path:
            self.csv_path = path
            self.file_label.setText(self._short_path(path))

    def _on_theme_changed(self, name):
        self.selected_theme = name

    def _on_display_changed(self, idx):
        self.selected_display_mode = idx

    def get_result(self):
        return self.csv_path, self.selected_theme, self.selected_display_mode

    def _export_mp4(self):
        """Handles the Export MP4 button click."""
        from PyQt6.QtWidgets import QMessageBox, QProgressDialog

        if not self.csv_path or not os.path.exists(self.csv_path):
            QMessageBox.warning(self, "No Project",
                "Please select a project CSV file first.")
            return

        # Get export settings
        fps = self.fps_combo.currentData()
        width, height = 1920, 1080

        # Choose output path
        from engine.paths import get_export_tracks_dir
        default_name = os.path.splitext(os.path.basename(self.csv_path))[0] + ".mp4"
        default_path = os.path.join(get_export_tracks_dir(), default_name)
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Export MP4 Video", default_path, "MP4 Video (*.mp4)")
        if not output_path:
            return

        # Check ffmpeg
        ffmpeg = _find_ffmpeg_exe()
        if not ffmpeg:
            QMessageBox.critical(self, "FFmpeg Not Found",
                "ffmpeg is required for MP4 export.\n"
                "Run build.bat to download it, or install it manually.")
            return

        # Progress dialog
        progress = QProgressDialog("Rendering video...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Exporting MP4")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setAutoClose(False)

        self._export_error = None
        self._export_progress = 0.0

        def _on_progress(pct):
            self._export_progress = pct

        def _do_export():
            try:
                export_mp4(
                    self.csv_path, self.selected_theme, output_path,
                    width=width, height=height, fps=fps,
                    progress_callback=_on_progress)
            except Exception as e:
                import traceback
                self._export_error = traceback.format_exc()

        import threading
        t = threading.Thread(target=_do_export, daemon=True)
        t.start()

        # Poll progress from main thread
        while t.is_alive():
            QApplication.processEvents()
            progress.setValue(int(self._export_progress * 100))
            if progress.wasCanceled():
                break
            t.join(timeout=0.1)

        progress.close()

        if self._export_error:
            QMessageBox.critical(self, "Export Failed",
                f"MP4 export failed:\n{self._export_error}")
        elif not progress.wasCanceled():
            QMessageBox.information(self, "Export Complete",
                f"Video saved to:\n{output_path}")


# Display mode constants
DISPLAY_MODES = [
    ("maximized",       "Maximized (16:9)"),
    ("windowed_large",  "1280×800 (16:10)"),
    ("windowed_small",  "960×600 (16:10)"),
    ("4_3_large",       "1024×768 (4:3)"),
    ("fullscreen",      "Fullscreen"),
]


# ─────────────────────────────────────────────────────────────────
# RETRO VISUALIZER WINDOW
# ─────────────────────────────────────────────────────────────────

class RetroVisualizerWindow(QWidget):
    """
    Fullscreen frameless window rendering a scrolling DOS-style tracker
    with synchronized audio playback.
    """

    def __init__(self, csv_path, theme_name="MS-DOS", display_mode_idx=0, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Display mode cycling
        self._display_mode_idx = display_mode_idx
        self._is_fullscreen = False
        self._apply_display_mode()

        # Parse project
        self.data = VisualizerDataParser()
        self.data.parse(csv_path)
        self._project_name = os.path.splitext(os.path.basename(csv_path))[0]

        # Theme management (cycle with ←/→)
        self.theme_names = list(RetroTheme.THEMES.keys())
        self.theme_idx = self.theme_names.index(theme_name) if theme_name in self.theme_names else 0
        self.theme = RetroTheme(self.theme_names[self.theme_idx])

        # Audio state
        self._audio = None             # Full rendered stereo numpy array
        self._step_times = []          # [{time, pat_id, row}, ...]
        self._step_time_values = []    # [float, ...] for binary search
        self._track_rms = {}           # {step_idx: [rms_per_track]}
        self._play_start_time = 0.0
        self._total_duration = 0.0
        self._rendering = False

        # Playback state
        self._playing = False
        self._current_step_idx = 0

        # Display state
        self._visible_rows = 32
        self._max_visible_tracks = 8   # Calculated dynamically in paintEvent

        # Sub-systems
        self.meters = TrackLevelMeters(self.data.tracks)

        # Viz timer (55fps, synced to audio clock)
        self._viz_timer = QTimer(self)
        self._viz_timer.timeout.connect(self._update_viz)

        # Last processed step so we only fire events once
        self._last_step_idx = -1

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Start rendering audio immediately
        self._render_audio()

    # ── AUDIO RENDERING ──

    def _render_audio(self):
        """Render the full song audio in a background thread."""
        self._rendering = True
        self.update()

        # Snapshot data for thread
        order_list = list(self.data.order_list)
        pattern_lengths = dict(self.data.pattern_lengths)

        def _do_render():
            seq = Sequencer(44100)
            num_tracks = self.data.tracks

            audio_blocks = []
            track_audio_blocks = [[] for _ in range(num_tracks)]  # per-track mono
            play_pattern_steps = []  # [(pat_id, pat_len, bpm, lpb)]

            for pat_id in order_list:
                pat_len = pattern_lengths.get(pat_id, 64)
                pat_bpm = self.data.get_bpm_for_pattern(pat_id)
                pat_lpb = self.data.get_lpb_for_pattern(pat_id)

                tracks = self.data.build_tracks_for_pattern(pat_id)
                try:
                    block = seq.render_pattern(pat_len, pat_bpm, tracks, apply_limiter=False)
                    audio_blocks.append(block)
                except Exception as e:
                    import traceback
                    print(f"Visualizer Render Error ({pat_id}):\n{traceback.format_exc()}")
                    step_dur = seq.calculate_step_time(pat_bpm, pat_lpb)
                    silence = np.zeros((int(pat_len * step_dur * 44100), 2))
                    audio_blocks.append(silence)

                # Render each track solo for per-track RMS
                for ti in range(num_tracks):
                    try:
                        solo_tracks = [{"patch": t.get("patch"), "sequence": []} for t in tracks]
                        if ti < len(tracks):
                            solo_tracks[ti] = tracks[ti]
                        solo_seq = Sequencer(44100)
                        solo_block = solo_seq.render_pattern(pat_len, pat_bpm, solo_tracks, apply_limiter=False)
                        # Convert stereo to mono for RMS
                        mono = np.mean(solo_block, axis=1) if solo_block.ndim == 2 else solo_block
                        track_audio_blocks[ti].append(mono)
                    except Exception:
                        step_dur = seq.calculate_step_time(pat_bpm, pat_lpb)
                        track_audio_blocks[ti].append(np.zeros(int(pat_len * step_dur * 44100)))

                play_pattern_steps.append((pat_id, pat_len, pat_bpm, pat_lpb))

            if not audio_blocks:
                return

            audio = np.concatenate(audio_blocks, axis=0)
            max_val = np.max(np.abs(audio))
            if max_val > 0.98:
                audio *= (0.98 / max_val)

            # Concatenate per-track mono audio
            full_track_audio = []
            for ti in range(num_tracks):
                if track_audio_blocks[ti]:
                    full_track_audio.append(np.concatenate(track_audio_blocks[ti]))
                else:
                    full_track_audio.append(np.zeros(len(audio)))

            # Build timestamp array
            step_times = []
            step_time_values = []
            current_time = 0.0
            for pat_id, p_len, p_bpm, p_lpb in play_pattern_steps:
                step_dur = seq.calculate_step_time(p_bpm, p_lpb)
                for r in range(p_len):
                    step_times.append({"time": current_time, "pat_id": pat_id, "row": r})
                    step_time_values.append(current_time)
                    current_time += step_dur

            # Pre-compute per-track per-step RMS levels
            track_rms = {}
            sr = 44100
            for si, st in enumerate(step_times):
                start_sample = int(st["time"] * sr)
                # Use a window of ~1024 samples centered on the step
                window = 1024
                s0 = max(0, start_sample)
                s1 = min(s0 + window, len(audio))
                rms_list = []
                for ti in range(num_tracks):
                    chunk = full_track_audio[ti][s0:s1]
                    if len(chunk) > 0:
                        rms = float(np.sqrt(np.mean(chunk ** 2)))
                        # Scale RMS to 0-1 range (typical audio RMS is 0-0.3)
                        rms_list.append(min(1.0, rms * 3.5))
                    else:
                        rms_list.append(0.0)
                track_rms[si] = rms_list

            # Store results (main thread will read these)
            self._audio = audio
            self._step_times = step_times
            self._step_time_values = step_time_values
            self._track_rms = track_rms
            self._total_duration = current_time
            self._rendering = False
            self.update()

        threading.Thread(target=_do_render, daemon=True).start()

    def _play(self):
        """Start or resume playback."""
        if self._audio is None or self._rendering:
            return
        sd.stop()
        # Play from current position
        sample_rate = 44100
        if self._current_step_idx < len(self._step_time_values):
            start_time = self._step_time_values[self._current_step_idx]
        else:
            start_time = 0.0
            self._current_step_idx = 0
        start_sample = int(start_time * sample_rate)
        if start_sample >= len(self._audio):
            start_sample = 0
            self._current_step_idx = 0
            start_time = 0.0

        sd.play(self._audio[start_sample:], samplerate=sample_rate)
        self._play_start_time = time.perf_counter() - start_time
        self._playing = True
        self._last_step_idx = -1
        self._viz_timer.start(33)  # ~30fps — smooth scrolling

    def _pause(self):
        """Pause playback."""
        if self._playing:
            sd.stop()
            self._playing = False
            self._viz_timer.stop()

    def _reset(self):
        """Reset to beginning."""
        sd.stop()
        self._playing = False
        self._viz_timer.stop()
        self._current_step_idx = 0
        self._last_step_idx = -1
        self.meters = TrackLevelMeters(self.data.tracks)
        self.update()

    def _build_display_rows(self, center_step_idx, num_rows):
        """
        Builds a window of display rows centered on center_step_idx.
        Shows past rows above and upcoming rows below the playhead.
        Inserts pattern transition separator rows.
        Returns: list of dicts, each is either:
          {"type": "event", "row": int, "pat_id": str, "events_by_track": dict, "is_active": bool}
          {"type": "separator", "pat_id": str, "pat_name": str}
        """
        if not self._step_times:
            return []

        total = len(self._step_times)
        half = num_rows // 2

        # Bias toward showing upcoming rows when near the start
        start = max(0, center_step_idx - half)
        end = min(total, start + num_rows)
        # If we hit the end, shift the window back
        if end == total:
            start = max(0, end - num_rows)

        result = []
        prev_pat_id = None

        for idx in range(start, end):
            info = self._step_times[idx]
            pat_id = info["pat_id"]
            row = info["row"]

            # Insert pattern separator when pattern changes
            if pat_id != prev_pat_id and prev_pat_id is not None:
                pat_name = self.data.pattern_names.get(pat_id, pat_id)
                result.append({"type": "separator", "pat_id": pat_id, "pat_name": pat_name})
            prev_pat_id = pat_id

            # Collect events for this row
            events_this_row = self.data.timeline.get(pat_id, {}).get(row, [])
            events_by_track = {}
            for ev in events_this_row:
                events_by_track[ev["track"]] = ev

            result.append({
                "type": "event",
                "row": row,
                "pat_id": pat_id,
                "events_by_track": events_by_track,
                "is_active": (idx == center_step_idx),
            })

        return result

    def _update_viz(self):
        """Called at ~55fps. Syncs visual state to audio clock position."""
        if not self._playing or not self._step_time_values:
            return

        elapsed = time.perf_counter() - self._play_start_time

        # Song ended?
        if elapsed >= self._total_duration:
            self._reset()
            return

        # Binary search for current step
        step_idx = np.searchsorted(self._step_time_values, elapsed, side='right') - 1
        step_idx = max(0, min(step_idx, len(self._step_times) - 1))
        self._current_step_idx = step_idx

        # Feed meters from pre-computed per-track RMS
        if step_idx != self._last_step_idx:
            self._last_step_idx = step_idx
            rms_levels = self._track_rms.get(step_idx, [])
            for ti, rms in enumerate(rms_levels):
                self.meters.set_level(ti, rms)

        self.meters.tick()
        self.update()

    # ── KEYBOARD ──

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mod = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self._pause()
            self.close()
        elif key == Qt.Key.Key_Space:
            if self._playing:
                self._pause()
            else:
                self._play()
        elif key == Qt.Key.Key_Return:
            if mod & Qt.KeyboardModifier.AltModifier:
                self._toggle_fullscreen()
            else:
                self._reset()
        elif key == Qt.Key.Key_F11:
            self._toggle_fullscreen()
        elif key == Qt.Key.Key_Left:
            self.theme_idx = (self.theme_idx - 1) % len(self.theme_names)
            self.theme = RetroTheme(self.theme_names[self.theme_idx])
            self.update()
        elif key == Qt.Key.Key_Right:
            self.theme_idx = (self.theme_idx + 1) % len(self.theme_names)
            self.theme = RetroTheme(self.theme_names[self.theme_idx])
            self.update()
        elif key == Qt.Key.Key_W:
            self._cycle_display_mode()
        else:
            super().keyPressEvent(event)

    def _cycle_display_mode(self):
        """Cycle through display modes: Maximized → 1280×800 → 960×600 → Fullscreen."""
        self._display_mode_idx = (self._display_mode_idx + 1) % len(DISPLAY_MODES)
        self._apply_display_mode()

    def _apply_display_mode(self):
        """Apply the current display mode."""
        mode_key = DISPLAY_MODES[self._display_mode_idx][0]
        if mode_key == "maximized":
            self.showNormal()
            self.showMaximized()
            self._is_fullscreen = False
        elif mode_key == "windowed_large":
            self.showNormal()
            self.resize(1280, 800)
            self._center_on_screen()
            self._is_fullscreen = False
        elif mode_key == "windowed_small":
            self.showNormal()
            self.resize(960, 600)
            self._center_on_screen()
            self._is_fullscreen = False
        elif mode_key == "4_3_large":
            self.showNormal()
            self.resize(1024, 768)
            self._center_on_screen()
            self._is_fullscreen = False
        elif mode_key == "fullscreen":
            self.showFullScreen()
            self._is_fullscreen = True

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2 + geo.x()
            y = (geo.height() - self.height()) // 2 + geo.y()
            self.move(x, y)

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self._display_mode_idx = 0
            self._apply_display_mode()
        else:
            self._display_mode_idx = len(DISPLAY_MODES) - 1  # fullscreen is last
            self._apply_display_mode()

    def _is_4_3_mode(self):
        """Check if current display mode is a 4:3 hamburger-split layout."""
        mode_key = DISPLAY_MODES[self._display_mode_idx][0]
        return mode_key.startswith("4_3")

    # ── PAINTING ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = self.width()
        h = self.height()

        # Calculate elapsed time for live playback
        if self._playing and self._audio is not None:
            elapsed = time.perf_counter() - self._play_start_time
        else:
            elapsed = -1.0

        self._render_frame(p, w, h, elapsed, is_export=False)
        p.end()

    def _render_frame(self, p, w, h, elapsed, is_export=False):
        """Shared rendering logic used by both paintEvent and MP4 export.
        elapsed < 0 means paused/stopped."""
        t = self.theme
        font = QFont(t.font, t.font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        p.setFont(font)
        fm = QFontMetrics(font)
        char_w = fm.horizontalAdvance("M")
        line_h = fm.height() + 2

        # Calculate how many tracks fit on screen
        is_4_3 = self._is_4_3_mode()
        if is_4_3:
            # 4:3 hamburger split: always 4 tracks per half
            self._max_visible_tracks = min(4, self.data.tracks)
        else:
            usable_chars = (w - 16) // char_w - 4
            track_w = TRACK_INNER + 3
            self._max_visible_tracks = max(1, min(self.data.tracks, usable_chars // track_w))

        # Background
        p.fillRect(0, 0, w, h, QColor(t.bg))
        y = 4

        # ── RENDERING MESSAGE ──
        if self._rendering:
            p.setPen(QColor(t.highlight))
            p.drawText(w // 2 - 100, h // 2, "[...]  Rendering audio... Please wait.")
            return

        # ── HEADER BAR ──
        header_h = line_h * 2 + 4
        p.fillRect(0, y, w, header_h, QColor(t.header_bg))

        if self._step_times and self._current_step_idx < len(self._step_times):
            info = self._step_times[self._current_step_idx]
            pat_id = info["pat_id"]
            cur_row = info["row"]
        else:
            pat_id = self.data.order_list[0] if self.data.order_list else "—"
            cur_row = 0

        pat_name = self.data.pattern_names.get(pat_id, pat_id)
        key = self.data.get_key_for_pattern(pat_id)
        mode = self.data.get_mode_for_pattern(pat_id)
        bpm = self.data.get_bpm_for_pattern(pat_id)
        lpb = self.data.get_lpb_for_pattern(pat_id)
        lpm = self.data.get_lpm_for_pattern(pat_id)

        # Top line: meters
        meter_strs = self.meters.render(width=5)
        meter_line = "  ".join(
            f"T{i+1}:{meter_strs[i]}" for i in range(min(self.data.tracks, 8))
        )
        p.setPen(QColor(t.header_text))
        p.drawText(8, y + line_h, meter_line)

        # Status line
        display_label = DISPLAY_MODES[self._display_mode_idx][1]
        proj = getattr(self, '_project_name', '')
        pat_display = pat_name[:12]
        status = (f"  {proj}    KEY: {key} {mode}    BPM: {bpm}    LPB: {lpb}    LPM: {lpm}    "
                  f"PAT: {pat_display}  ROW: {cur_row:03d}    {t.name}  [{display_label}]")
        status += "  [>>] PLAYING" if self._playing else "  [||] PAUSED"
        p.drawText(8, y + line_h * 2, status)
        y += header_h + 2

        # ── SINGLE MASTER OSCILLOSCOPE ──
        osc_height = 3
        if elapsed >= 0 and self._audio is not None:
            sample_pos = int(elapsed * 44100)
        else:
            sample_pos = -1

        # Full-width oscilloscope using master audio mix
        osc_width_chars = max(20, (w - 16) // char_w)
        osc_total_h = line_h * (osc_height + 1) + 4
        p.fillRect(0, y, w, osc_total_h, QColor(t.bg))
        osc_lines = render_ascii_oscilloscope(
            self._audio, sample_pos, width=osc_width_chars, height=osc_height)
        p.setPen(QColor(t.note))
        for ri, line in enumerate(osc_lines):
            p.drawText(8, y + line_h * (ri + 1), line)

        y += osc_total_h + 2

        # ── Dynamic track column width ──
        num_tracks_here = 4 if is_4_3 else self._max_visible_tracks
        # available chars = (window_width - margins - row_number_area) / char_width
        avail_chars = max(40, (w - 16) // char_w - 4)  # subtract row num cols
        # each track gets: data_cols + 1 divider char
        chars_per_track = max(TRACK_INNER, avail_chars // num_tracks_here - 1)
        # Distribute extra space across 6 expandable columns (note, inst, vel, fx1, fx2, + 1 spare)
        extra = chars_per_track - TRACK_INNER
        base_extra, remainder = divmod(extra, 6)
        # Distribute remainder to the most impactful columns: note, inst, fx1, fx2
        dyn_note = COL_NOTE + base_extra + (1 if remainder > 0 else 0)
        dyn_inst = COL_INST + base_extra + (1 if remainder > 1 else 0)
        dyn_fx = COL_FX + base_extra + (1 if remainder > 2 else 0)
        dyn_vel = COL_VEL + base_extra + (1 if remainder > 4 else 0)
        dyn_gate = COL_GATE
        dyn_inner = dyn_note + dyn_inst + dyn_vel + dyn_gate + dyn_fx * 2 + 5

        # ── HELPER: Draw a tracker half (headers + rows for a track range) ──
        def _draw_tracker_half(p, y_start, available_h, track_offset, track_count):
            """Draws column headers, separator, and tracker rows for tracks
            [track_offset .. track_offset+track_count-1].
            Returns the y position after the last row."""
            yy = y_start

            # Column headers
            p.fillRect(0, yy, w, line_h + 2, QColor(t.header_bg))
            p.setPen(QColor(t.header_text))
            x_pos = 8 + char_w * 4
            for ti in range(track_count):
                if ti > 0:
                    p.setPen(QColor(t.border))
                    p.drawText(x_pos - char_w, yy + line_h, TRACK_DIVIDER)
                    p.setPen(QColor(t.header_text))
                hdr = (f"{'Nte':<{dyn_note}} {'Ins':<{dyn_inst}} "
                       f"{'Vel':>{dyn_vel}} {'Gt':>{dyn_gate}} {'FX1':<{dyn_fx}} {'FX2':<{dyn_fx}}")
                p.drawText(x_pos, yy + line_h, hdr)
                x_pos += (dyn_inner + 1) * char_w
            yy += line_h + 2

            # Separator
            p.setPen(QColor(t.border))
            sep = t.border_h * (w // char_w - 2)
            p.drawText(char_w, yy + line_h, sep)
            yy += line_h + 1

            # Tracker rows
            vis_rows = max(4, available_h // line_h)
            display_entries = self._build_display_rows(self._current_step_idx, vis_rows)

            for entry in display_entries:
                row_y = yy + line_h

                if entry["type"] == "separator":
                    p.fillRect(0, row_y - line_h + 4, w, line_h, QColor(t.header_bg))
                    p.setPen(QColor(t.highlight))
                    marker = f" ═══ PAT: {entry['pat_name']} ═══"
                    fill_char = t.border_h
                    fill_w = max(0, (w // char_w) - len(marker) - 4)
                    full_marker = f"  {fill_char * (fill_w // 2)}{marker}{fill_char * (fill_w // 2)}"
                    p.drawText(8, row_y, full_marker)
                    yy += line_h
                    continue

                is_active = entry.get("is_active", False)
                row_num = entry["row"]
                entry_pat = entry["pat_id"]
                entry_lpb = self.data.get_lpb_for_pattern(entry_pat)
                entry_lpm = self.data.get_lpm_for_pattern(entry_pat)

                is_measure = (row_num % entry_lpm == 0) if entry_lpm > 0 else False
                is_beat = (row_num % entry_lpb == 0) if entry_lpb > 0 else False

                if is_active:
                    p.fillRect(0, row_y - line_h + 4, w, line_h, QColor(t.active_row))
                elif is_measure:
                    measure_color = QColor(t.header_bg)
                    measure_color.setAlpha(80)
                    p.fillRect(0, row_y - line_h + 4, w, line_h, measure_color)

                if is_active:
                    p.setPen(QColor(t.highlight))
                elif is_measure:
                    p.setPen(QColor(t.header_text))
                elif is_beat:
                    p.setPen(QColor(t.text))
                else:
                    p.setPen(QColor(t.row_num))
                p.drawText(8, row_y, f"{row_num:03d}")

                # Track columns
                x_pos = 8 + char_w * 4
                for ti_local in range(track_count):
                    ti = ti_local + track_offset
                    if ti_local > 0:
                        p.setPen(QColor(t.border))
                        p.drawText(x_pos - char_w, row_y, TRACK_DIVIDER)

                    ev = entry["events_by_track"].get(ti, None)

                    if ev is None:
                        p.setPen(QColor(t.empty))
                        empty = (f"{'···':<{dyn_note}} {'···':<{dyn_inst}} "
                                 f"{'···':>{dyn_vel}} {'··':>{dyn_gate}} {'──':<{dyn_fx}} {'──':<{dyn_fx}}")
                        p.drawText(x_pos, row_y, empty)
                    else:
                        cx = x_pos
                        p.setPen(QColor(t.note))
                        p.drawText(cx, row_y, f"{_trunc(ev.get('note', ''), dyn_note):<{dyn_note}}")
                        cx += (dyn_note + 1) * char_w
                        p.setPen(QColor(t.inst))
                        p.drawText(cx, row_y, f"{_trunc(ev.get('inst', ''), dyn_inst):<{dyn_inst}}")
                        cx += (dyn_inst + 1) * char_w
                        p.setPen(QColor(t.vel_gate))
                        p.drawText(cx, row_y, f"{_trunc(ev.get('vel', ''), dyn_vel):>{dyn_vel}}")
                        cx += (dyn_vel + 1) * char_w
                        p.drawText(cx, row_y, f"{_trunc(ev.get('gate', ''), dyn_gate):>{dyn_gate}}")
                        cx += (dyn_gate + 1) * char_w
                        p.setPen(QColor(t.fx))
                        p.drawText(cx, row_y, f"{_trunc(ev.get('fx1', ''), dyn_fx):<{dyn_fx}}")
                        cx += (dyn_fx + 1) * char_w
                        p.drawText(cx, row_y, f"{_trunc(ev.get('fx2', ''), dyn_fx):<{dyn_fx}}")
                    x_pos += (dyn_inner + 1) * char_w

                yy += line_h

            return yy

        # ── RENDER TRACKER ──
        if is_4_3 and self.data.tracks > 4:
            # Hamburger split: top half = tracks 1-4, bottom half = tracks 5-8
            half_h = (h - y - line_h * 2 - 8) // 2
            tracks_top = min(4, self.data.tracks)
            tracks_bot = min(4, self.data.tracks - 4)

            y = _draw_tracker_half(p, y, half_h, 0, tracks_top)

            # Divider between halves
            p.setPen(QColor(t.highlight))
            div_sep = t.border_h * (w // char_w - 2)
            p.drawText(char_w, y + line_h, div_sep)
            y += line_h + 2

            remaining_h = h - y - line_h - 8
            y = _draw_tracker_half(p, y, remaining_h, 4, tracks_bot)
        else:
            # Normal widescreen: all tracks side by side
            available_h = h - y - line_h - 8
            y = _draw_tracker_half(p, y, available_h, 0, self._max_visible_tracks)

        # ── BOTTOM BAR ──
        p.fillRect(0, h - line_h - 4, w, line_h + 4, QColor(t.header_bg))
        p.setPen(QColor(t.header_text))
        if is_export:
            proj = getattr(self, '_project_name', '')
            p.drawText(8, h - 6, f"  Lanthorn PSG  \u2022  {proj}")
        else:
            p.drawText(8, h - 6, "  SPC:Play  RET:Reset  \u2190\u2192:Theme  W:Window  F11:Full  ESC:Exit")


# ─────────────────────────────────────────────────────────────────
# FFMPEG HELPER
# ─────────────────────────────────────────────────────────────────

def _find_ffmpeg_exe():
    """Locates the ffmpeg executable (bundled or system PATH)."""
    import shutil
    # Bundled with PyInstaller
    base = getattr(sys, '_MEIPASS', None)
    if base:
        candidate = os.path.join(base, 'ffmpeg', 'ffmpeg.exe')
        if os.path.isfile(candidate):
            return candidate
    # Next to executable (dist build)
    exe_dir = os.path.dirname(sys.executable)
    candidate = os.path.join(exe_dir, 'ffmpeg', 'ffmpeg.exe')
    if os.path.isfile(candidate):
        return candidate
    # Dev mode: tools/ffmpeg/
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(script_dir, 'tools', 'ffmpeg', 'ffmpeg.exe')
    if os.path.isfile(candidate):
        return candidate
    # System PATH
    found = shutil.which('ffmpeg')
    if found:
        return found
    return None


# ─────────────────────────────────────────────────────────────────
# MP4 EXPORT
# ─────────────────────────────────────────────────────────────────

def export_mp4(csv_path, theme_name, output_path, width=1280, height=720,
               fps=30, progress_callback=None):
    """Renders the entire Retro Visualizer playback to an MP4 file.

    Args:
        csv_path: Path to the Lanthorn CSV project.
        theme_name: Name of the RetroTheme to use.
        output_path: Destination .mp4 file path.
        width, height: Video resolution.
        fps: Frame rate (30 or 60).
        progress_callback: Optional callable(float) for 0.0-1.0 progress.
    """
    import wave as wave_mod
    import struct

    ffmpeg_exe = _find_ffmpeg_exe()
    if not ffmpeg_exe:
        raise FileNotFoundError(
            "ffmpeg not found. Install ffmpeg or run build.bat to bundle it.")

    # Parse project and render audio
    data = VisualizerDataParser()
    data.parse(csv_path)

    seq = Sequencer(44100)
    audio_blocks = []
    play_pattern_steps = []

    for pat_id in data.order_list:
        pat_len = data.pattern_lengths.get(pat_id, 64)
        pat_bpm = data.get_bpm_for_pattern(pat_id)
        pat_lpb = data.get_lpb_for_pattern(pat_id)
        tracks = data.build_tracks_for_pattern(pat_id)
        try:
            block = seq.render_pattern(pat_len, pat_bpm, tracks, apply_limiter=False)
            audio_blocks.append(block)
        except Exception:
            step_dur = seq.calculate_step_time(pat_bpm, pat_lpb)
            audio_blocks.append(np.zeros((int(pat_len * step_dur * 44100), 2)))
        play_pattern_steps.append((pat_id, pat_len, pat_bpm, pat_lpb))

    if not audio_blocks:
        raise ValueError("No audio rendered — is the project empty?")

    audio = np.concatenate(audio_blocks, axis=0)
    max_val = np.max(np.abs(audio))
    if max_val > 0.98:
        audio *= (0.98 / max_val)

    # Build step timestamps
    step_times = []
    step_time_values = []
    current_time = 0.0
    for pat_id, p_len, p_bpm, p_lpb in play_pattern_steps:
        step_dur = seq.calculate_step_time(p_bpm, p_lpb)
        for r in range(p_len):
            step_times.append({"time": current_time, "pat_id": pat_id, "row": r})
            step_time_values.append(current_time)
            current_time += step_dur

    total_duration = current_time
    step_time_arr = np.array(step_time_values)

    # Write audio to temp WAV
    tmp_dir = tempfile.mkdtemp(prefix="lanthorn_export_")
    wav_path = os.path.join(tmp_dir, "audio.wav")
    try:
        # Write stereo 16-bit WAV
        with wave_mod.open(wav_path, 'w') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
            wf.writeframes(pcm.tobytes())

        # Set up a lightweight visualizer instance for rendering
        viz = RetroVisualizerWindow.__new__(RetroVisualizerWindow)
        viz.data = data
        viz.theme = RetroTheme(theme_name)
        viz.theme_names = list(RetroTheme.THEMES.keys())
        viz.theme_idx = viz.theme_names.index(theme_name) if theme_name in viz.theme_names else 0
        viz._audio = audio
        viz._step_times = step_times
        viz._step_time_values = step_time_values
        viz._current_step_idx = 0
        viz._playing = True
        viz._rendering = False
        viz._display_mode_idx = 0
        viz._is_fullscreen = False
        viz._max_visible_tracks = min(8, data.tracks)
        viz._last_step_idx = -1
        viz._play_start_time = 0.0
        viz._total_duration = total_duration
        viz._project_name = os.path.splitext(os.path.basename(csv_path))[0]
        viz.meters = TrackLevelMeters(data.tracks)

        # Start ffmpeg process
        cmd = [
            ffmpeg_exe, '-y',
            '-f', 'rawvideo', '-pix_fmt', 'bgra',
            '-s', f'{width}x{height}', '-r', str(fps),
            '-i', 'pipe:0',
            '-i', wav_path,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            output_path
        ]

        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )

        total_frames = int(total_duration * fps) + 1
        frame_dur = 1.0 / fps

        # Reuse a single QImage for all frames
        img = QImage(width, height, QImage.Format.Format_ARGB32)
        last_rendered_step = -1
        frame_bytes = None

        for frame_idx in range(total_frames):
            elapsed = frame_idx * frame_dur
            if elapsed > total_duration:
                elapsed = total_duration

            # Update step index for this frame
            step_idx = int(np.searchsorted(step_time_arr, elapsed, side='right')) - 1
            step_idx = max(0, min(step_idx, len(step_times) - 1))
            viz._current_step_idx = step_idx

            # Feed meters from pre-computed RMS
            if step_idx != viz._last_step_idx:
                viz._last_step_idx = step_idx
                rms_levels = viz._track_rms.get(step_idx, [])
                for ti, rms in enumerate(rms_levels):
                    viz.meters.set_level(ti, rms)
            viz.meters.tick()

            # Only re-render when step changes (big speedup)
            if step_idx != last_rendered_step:
                last_rendered_step = step_idx
                img.fill(QColor(0, 0, 0))
                painter = QPainter(img)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                viz._render_frame(painter, width, height, elapsed, is_export=True)
                painter.end()
                ptr = img.bits()
                ptr.setsize(width * height * 4)
                frame_bytes = bytes(ptr)

            # Write frame (reuse bytes if step unchanged)
            proc.stdin.write(frame_bytes)

            if progress_callback:
                progress_callback(frame_idx / total_frames)

        proc.stdin.close()
        proc.wait(timeout=60)

        if progress_callback:
            progress_callback(1.0)

    finally:
        # Clean up temp files
        try:
            os.remove(wav_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────

def launch_visualizer(csv_path=None, parent=None):
    """Opens the launch dialog, then starts the visualizer on confirmation."""
    dlg = RetroVisualizerLaunchDialog(parent, csv_path)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        path, theme, display_idx = dlg.get_result()
        if not path or not os.path.exists(path):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(parent, "No Project",
                "Please save or open a project before launching the visualizer.")
            return None
        win = RetroVisualizerWindow(path, theme, display_idx, parent)
        win.show()
        return win
    return None
