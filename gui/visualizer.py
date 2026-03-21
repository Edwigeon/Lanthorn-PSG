# gui/visualizer.py
"""
SFX Painter — Multi-layer sound design canvas with chromatic note grid,
variable duration, per-layer wave types, and Foley FX processing.

Y-axis: Musical notes (C2–C7, 5 octaves = 60 semitones)
X-axis: Time steps (user-configurable duration via Duration slider)
Layers: Red (sine), Blue (square), Yellow (sawtooth) — independently painted
FX: Bit crush, attack/release envelope, pitch sweep, echo, ring mod, saturation, detune, delay
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGraphicsView,
    QGraphicsScene, QGraphicsRectItem, QSlider, QLabel,
    QGroupBox, QPushButton, QComboBox, QButtonGroup,
    QRadioButton, QCheckBox, QGraphicsTextItem,
    QSpinBox, QToolButton
)
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFont
import sounddevice as sd
import numpy as np


# ---------- Musical note helpers ----------
# C2 (MIDI 36) to C7 (MIDI 96) = 60 semitones + 1
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MIDI_LOW = 36   # C2
MIDI_HIGH = 96  # C7
TOTAL_NOTES = MIDI_HIGH - MIDI_LOW + 1   # 61 rows

def midi_to_freq(midi_note):
    """Convert MIDI note number to frequency in Hz."""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

def midi_to_name(midi_note):
    """Convert MIDI note number to human-readable name like 'C4'."""
    octave = (midi_note // 12) - 1
    note = NOTE_NAMES[midi_note % 12]
    return f"{note}{octave}"

def row_to_midi(row):
    """Canvas row 0 = top = highest note (C7), row 60 = bottom = C2."""
    return MIDI_HIGH - row

def row_to_freq(row):
    return midi_to_freq(row_to_midi(row))


# ---------- Layer definitions ----------
LAYERS = [
    {"name": "Red",    "color": "#FF004D", "dim": "#661122", "wave_default": "sine"},
    {"name": "Blue",   "color": "#29ADFF", "dim": "#103855", "wave_default": "square"},
    {"name": "Yellow", "color": "#FFEC27", "dim": "#665510", "wave_default": "sawtooth"},
]


# ---------- Tool modes ----------
TOOL_PAINT = 0
TOOL_ERASE = 1
TOOL_LINE  = 2
TOOL_CURVE = 3


# ============================================================
#                     SFX Graphics View
# ============================================================
class SfxGraphicsView(QGraphicsView):
    info_signal = pyqtSignal(str)

    def __init__(self, total_steps=128, parent=None):
        super().__init__(parent)
        self.steps = total_steps
        self.notes = TOTAL_NOTES
        self.cell_w = 12
        self.cell_h = 10
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.scene.setSceneRect(
            -52, 0,
            self.steps * self.cell_w + 52,
            self.notes * self.cell_h
        )
        self.setBackgroundBrush(QColor('#1a1a1a'))
        self.setRenderHint(self.renderHints().Antialiasing, False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self.setMouseTracking(True)
        self.draw_grid()

        self.is_drawing = False
        self.active_layer = 0
        self.layer_points = [{}, {}, {}]

        # Tool state
        self.current_tool = TOOL_PAINT
        self.erase_size = 1
        self._zoom_factor = 1.0

        # Line / Curve multi-click state
        self._line_start = None
        self._curve_start = None
        self._curve_ctrl = None

    def draw_grid(self):
        pen_normal = QPen(QColor('#2a2a2e'))
        pen_octave = QPen(QColor('#444448'))
        pen_octave.setWidth(2)
        pen_c = QPen(QColor('#3a3a40'))
        font = QFont("Courier New", 7)

        for y in range(self.notes + 1):
            midi = row_to_midi(y) if y < self.notes else MIDI_LOW - 1
            if midi % 12 == 0:
                self.scene.addLine(0, y * self.cell_h, self.steps * self.cell_w, y * self.cell_h, pen_octave)
            else:
                self.scene.addLine(0, y * self.cell_h, self.steps * self.cell_w, y * self.cell_h, pen_normal)

            if y < self.notes:
                name = midi_to_name(midi)
                sharp = '#' in name or 'b' in name
                if sharp:
                    bg = QGraphicsRectItem(QRectF(0, y * self.cell_h, self.steps * self.cell_w, self.cell_h))
                    bg.setBrush(QBrush(QColor(20, 20, 22)))
                    bg.setPen(QPen(Qt.PenStyle.NoPen))
                    bg.setZValue(-1)
                    self.scene.addItem(bg)

                if midi % 12 == 0 or midi % 12 == 4 or midi % 12 == 7:
                    txt = QGraphicsTextItem(name)
                    txt.setFont(font)
                    txt.setDefaultTextColor(QColor('#888') if not sharp else QColor('#555'))
                    txt.setPos(-48, y * self.cell_h - 3)
                    txt.setZValue(10)
                    self.scene.addItem(txt)

        for x in range(self.steps + 1):
            if x % 16 == 0:
                self.scene.addLine(x * self.cell_w, 0, x * self.cell_w, self.notes * self.cell_h, pen_octave)
            elif x % 4 == 0:
                self.scene.addLine(x * self.cell_w, 0, x * self.cell_w, self.notes * self.cell_h, pen_c)
            else:
                self.scene.addLine(x * self.cell_w, 0, x * self.cell_w, self.notes * self.cell_h, pen_normal)

    # ---------- Cell helpers ----------
    def _pos_to_cell(self, pos):
        scene_pos = self.mapToScene(pos)
        step = int(scene_pos.x() // self.cell_w)
        note = int(scene_pos.y() // self.cell_h)
        if 0 <= step < self.steps and 0 <= note < self.notes:
            return (step, note)
        return None

    # ---------- Mouse ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            cell = self._pos_to_cell(event.pos())
            if cell is None:
                return super().mousePressEvent(event)
            step, note = cell

            if self.current_tool == TOOL_PAINT:
                self.is_drawing = True
                self.paint_note_block(step, note, self.active_layer)
            elif self.current_tool == TOOL_ERASE:
                self.is_drawing = True
                self._erase_area(step, note)
            elif self.current_tool == TOOL_LINE:
                if self._line_start is None:
                    self._line_start = (step, note)
                    self.info_signal.emit("Line: start set — click end point")
                else:
                    self._fill_line(self._line_start, (step, note))
                    self._line_start = None
                    self.info_signal.emit("Line drawn")
            elif self.current_tool == TOOL_CURVE:
                if self._curve_start is None:
                    self._curve_start = (step, note)
                    self.info_signal.emit("Curve: start set — click control point")
                elif self._curve_ctrl is None:
                    self._curve_ctrl = (step, note)
                    self.info_signal.emit("Curve: control set — click end point")
                else:
                    self._fill_curve(self._curve_start, self._curve_ctrl, (step, note))
                    self._curve_start = None
                    self._curve_ctrl = None
                    self.info_signal.emit("Curve drawn")
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        cell = self._pos_to_cell(event.pos())
        if cell:
            step, note = cell
            midi = row_to_midi(note)
            name = midi_to_name(midi)
            freq = midi_to_freq(midi)
            icons = ["🔴", "🔵", "🟡"]
            layer = LAYERS[self.active_layer]
            tool_names = {TOOL_PAINT: "Paint", TOOL_ERASE: "Erase",
                          TOOL_LINE: "Line", TOOL_CURVE: "Curve"}
            self.info_signal.emit(
                f"Step {step}  |  {name} ({freq:.1f} Hz)  |  "
                f"{icons[self.active_layer]} {layer['name']}  |  "
                f"Tool: {tool_names[self.current_tool]}")

        if self.is_drawing and cell:
            step, note = cell
            if self.current_tool == TOOL_PAINT:
                self.paint_note_block(step, note, self.active_layer)
            elif self.current_tool == TOOL_ERASE:
                self._erase_area(step, note)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_drawing = False
        super().mouseReleaseEvent(event)

    # ---------- Zoom ----------
    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1.0 / 1.15
            new_zoom = self._zoom_factor * factor
            if 0.3 <= new_zoom <= 5.0:
                self._zoom_factor = new_zoom
                self.setTransform(self.transform().scale(factor, factor))
            event.accept()
        else:
            super().wheelEvent(event)

    # ---------- Erase with adjustable size ----------
    def _erase_area(self, center_step, center_note):
        r = self.erase_size
        for ds in range(-r + 1, r):
            for dn in range(-r + 1, r):
                key = (center_step + ds, center_note + dn)
                for layer_idx in range(len(LAYERS)):
                    if key in self.layer_points[layer_idx]:
                        self.scene.removeItem(self.layer_points[layer_idx][key])
                        del self.layer_points[layer_idx][key]

    # ---------- Line tool (Bresenham) ----------
    def _fill_line(self, p0, p1):
        x0, y0 = p0
        x1, y1 = p1
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            if 0 <= x0 < self.steps and 0 <= y0 < self.notes:
                self.paint_note_block(x0, y0, self.active_layer)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    # ---------- Curve tool (quadratic Bézier) ----------
    def _fill_curve(self, p0, ctrl, p2):
        dist = abs(p2[0] - p0[0]) + abs(p2[1] - p0[1])
        n_steps = max(dist * 2, 20)
        prev = None
        for i in range(n_steps + 1):
            t = i / n_steps
            x = (1 - t)**2 * p0[0] + 2*(1 - t)*t * ctrl[0] + t**2 * p2[0]
            y = (1 - t)**2 * p0[1] + 2*(1 - t)*t * ctrl[1] + t**2 * p2[1]
            cell = (int(round(x)), int(round(y)))
            if cell != prev and 0 <= cell[0] < self.steps and 0 <= cell[1] < self.notes:
                self.paint_note_block(cell[0], cell[1], self.active_layer)
                prev = cell

    # ---------- Context menu ----------
    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2d2d30; color: #cccccc; border: 1px solid #3f3f46; }
            QMenu::item:selected { background-color: #007acc; }
            QMenu::separator { background-color: #3f3f46; height: 1px; margin: 4px 8px; }
        """)

        for i, layer_def in enumerate(LAYERS):
            icon = "●" if i == self.active_layer else "○"
            action = menu.addAction(f"{icon} Paint: {layer_def['name']}")
            action.setCheckable(True)
            action.setChecked(i == self.active_layer)
            idx = i
            action.triggered.connect(lambda checked, li=idx: self._switch_layer(li))

        menu.addSeparator()
        for i, layer_def in enumerate(LAYERS):
            action = menu.addAction(f"✕ Clear {layer_def['name']} layer")
            idx = i
            action.triggered.connect(lambda checked, li=idx: self.clear_layer(li))

        menu.addSeparator()
        clear_all = menu.addAction("🗑 Clear All Layers")
        clear_all.triggered.connect(self.clear_canvas)

        sfx_parent = self.parent()
        if sfx_parent and hasattr(sfx_parent, '_copy_fx_to_layer'):
            menu.addSeparator()
            active = self.active_layer
            icons = ["🔴", "🔵", "🟡"]
            for i, layer_def in enumerate(LAYERS):
                if i != active:
                    action = menu.addAction(
                        f"📋 Copy {icons[active]} FX → {icons[i]} {layer_def['name']}")
                    idx = i
                    action.triggered.connect(
                        lambda checked, t=idx: sfx_parent._copy_fx_to_layer(t))
            reset = menu.addAction(f"↺ Reset {icons[active]} {LAYERS[active]['name']} FX")
            reset.triggered.connect(sfx_parent._reset_fx_defaults)

        menu.exec(event.globalPos())
        event.accept()

    def _switch_layer(self, layer_idx):
        self.active_layer = layer_idx
        parent = self.parent()
        if parent and hasattr(parent, 'layer_btn_group'):
            btn = parent.layer_btn_group.button(layer_idx)
            if btn:
                btn.setChecked(True)

    def paint_note_block(self, step, note_row, layer_idx):
        key = (step, note_row)
        if key in self.layer_points[layer_idx]:
            return
        x = step * self.cell_w
        y = note_row * self.cell_h
        color = LAYERS[layer_idx]["color"]
        rect = QGraphicsRectItem(QRectF(x, y, self.cell_w, self.cell_h))
        rect.setBrush(QBrush(QColor(color)))
        rect.setPen(QPen(Qt.PenStyle.NoPen))
        rect.setZValue(layer_idx + 1)
        rect.setOpacity(0.80)
        self.scene.addItem(rect)
        self.layer_points[layer_idx][key] = rect

    def get_painted_range(self):
        all_steps = set()
        for pts in self.layer_points:
            for (step, _) in pts.keys():
                all_steps.add(step)
        if not all_steps:
            return None
        return min(all_steps), max(all_steps)

    def clear_layer(self, layer_idx):
        for key, rect in list(self.layer_points[layer_idx].items()):
            self.scene.removeItem(rect)
        self.layer_points[layer_idx].clear()

    def clear_canvas(self):
        self.scene.clear()
        self.layer_points = [{}, {}, {}]
        self.draw_grid()

# ---------- Per-layer FX defaults ----------
FX_DEFAULTS = {
    "att": 0, "rel": 15, "bit": 16, "bend": 0,
    "trem": 0, "trem_spd": 8, "vib": 0, "vib_spd": 6,
    "echo": 0, "echo_ms": 120, "ring": 0, "ring_hz": 300,
    "sat": 0, "dtn": 0, "dly": 0,
}

# FX key → (slider attr name, label, lo, hi, color)
FX_SLIDER_DEFS = [
    ("att",      "att_slider",  "Attack",           0, 100,  "#aaa"),
    ("rel",      "rel_slider",  "Release",          0, 100,  "#aaa"),
    ("bit",      "bit_slider",  "Bit Crush (4–16)", 4,  16,  "#aaa"),
    ("bend",     "bend_slider", "Pitch Sweep",   -100, 100,  "#aaa"),
    ("trem",     "trem_slider", "Tremolo",          0, 100,  "#FF77AA"),
    ("trem_spd", "trem_speed",  "Tremolo Speed",    1,  30,  "#CC5588"),
    ("vib",      "vib_slider",  "Vibrato",          0, 100,  "#77FFAA"),
    ("vib_spd",  "vib_speed",   "Vibrato Speed",    1,  30,  "#55CC88"),
    ("echo",     "echo_slider", "Echo",             0,  80,  "#29ADFF"),
    ("echo_ms",  "echo_time",   "Echo Delay (ms)", 20, 500,  "#228899"),
    ("ring",     "ring_slider", "Ring Mod",         0, 100,  "#FFEC27"),
    ("ring_hz",  "ring_freq",   "Ring Freq (Hz)",  50, 2000, "#AA9910"),
    ("sat",      "sat_slider",  "Saturation",       0, 100,  "#FF6644"),
    ("dtn",      "dtn_slider",  "Detune (cents)",   0, 100,  "#CC88FF"),
    ("dly",      "dly_slider",  "Delay Start",      0, 100,  "#88CCAA"),
]


# ============================================================
#                    SFX Canvas (Main Widget)
# ============================================================
class SfxCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Per-layer FX storage (3 independent dicts)
        self.layer_fx = [dict(FX_DEFAULTS) for _ in range(3)]
        self._active_fx_layer = 0

        # === Left column: toolbar + canvas + info bar ===
        left_column = QVBoxLayout()
        left_column.setSpacing(2)

        # ======== Drawing Toolbar ========
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        toolbar_style = """
            QToolButton { background: #2d2d30; color: #ccc; border: 1px solid #3f3f46;
                          padding: 4px 8px; border-radius: 3px; font-weight: bold; }
            QToolButton:checked { background: #007acc; color: white; border: 1px solid #007acc; }
        """
        self.tool_btn_group = QButtonGroup(self)
        self.tool_btn_group.setExclusive(True)
        tool_defs = [
            (TOOL_PAINT, "🖌 Paint"),
            (TOOL_ERASE, "🧹 Erase"),
            (TOOL_LINE,  "📏 Line"),
            (TOOL_CURVE, "〰 Curve"),
        ]
        for tool_id, label in tool_defs:
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setStyleSheet(toolbar_style)
            if tool_id == TOOL_PAINT:
                btn.setChecked(True)
            self.tool_btn_group.addButton(btn, tool_id)
            toolbar.addWidget(btn)

        self.tool_btn_group.idToggled.connect(self._on_tool_changed)

        # Eraser size spinbox
        toolbar.addWidget(QLabel("  Size:"))
        self.erase_size_spin = QSpinBox()
        self.erase_size_spin.setRange(1, 5)
        self.erase_size_spin.setValue(1)
        self.erase_size_spin.setFixedWidth(45)
        self.erase_size_spin.setStyleSheet(
            "QSpinBox { background: #2d2d30; color: #ccc; border: 1px solid #3f3f46; }")
        self.erase_size_spin.valueChanged.connect(self._on_erase_size_changed)
        toolbar.addWidget(self.erase_size_spin)

        toolbar.addStretch()
        left_column.addLayout(toolbar)

        # ======== Canvas ========
        self.canvas = SfxGraphicsView(total_steps=128)
        self.canvas.info_signal.connect(self._on_info_update)
        left_column.addWidget(self.canvas, stretch=1)

        # ======== Info Bar ========
        self.info_bar = QLabel("Hover over canvas for info")
        self.info_bar.setStyleSheet(
            "QLabel { background: #1e1e1e; color: #888; font-family: 'Courier New';"
            " font-size: 11px; padding: 3px 8px; border-top: 1px solid #3f3f46; }")
        self.info_bar.setFixedHeight(22)
        left_column.addWidget(self.info_bar)

        layout.addLayout(left_column, stretch=3)

        # --- Right Panel ---
        right_panel = QVBoxLayout()
        right_panel.setSpacing(6)

        # ======== Duration ========
        dur_group = QGroupBox("Duration")
        dur_group.setStyleSheet("QGroupBox { color: #cccccc; font-weight: bold; }")
        dur_layout = QVBoxLayout()

        dur_row = QHBoxLayout()
        self.dur_label = QLabel("0.50s")
        self.dur_label.setStyleSheet("color: #00ff88; font-family: 'Courier New'; font-size: 13px;")
        self.dur_slider = QSlider(Qt.Orientation.Horizontal)
        self.dur_slider.setRange(5, 400)
        self.dur_slider.setValue(50)
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(5, 400)
        self.dur_spin.setValue(50)
        self.dur_spin.setSuffix(" cs")
        self.dur_spin.setFixedWidth(62)
        self.dur_spin.setStyleSheet(
            "QSpinBox { background: #2d2d30; color: #00ff88; border: 1px solid #3f3f46; font-size: 11px; }")
        # Bidirectional link
        self.dur_slider.valueChanged.connect(
            lambda v: (self.dur_label.setText(f"{v / 100:.2f}s"), self.dur_spin.setValue(v))
        )
        self.dur_spin.valueChanged.connect(self.dur_slider.setValue)
        dur_row.addWidget(self.dur_slider, stretch=1)
        dur_row.addWidget(self.dur_spin)
        dur_row.addWidget(self.dur_label)
        dur_layout.addLayout(dur_row)

        self.auto_trim_cb = QCheckBox("Auto-trim to painted region")
        self.auto_trim_cb.setChecked(True)
        self.auto_trim_cb.setStyleSheet("QCheckBox { color: #aaa; }")
        dur_layout.addWidget(self.auto_trim_cb)

        dur_group.setLayout(dur_layout)
        right_panel.addWidget(dur_group)

        # ======== Paint Layers ========
        layer_group = QGroupBox("Paint Layers")
        layer_group.setStyleSheet("QGroupBox { color: #cccccc; font-weight: bold; }")
        layer_layout = QVBoxLayout()
        layer_layout.setSpacing(4)

        self.layer_btn_group = QButtonGroup(self)
        self.layer_wave_combos = []
        self.layer_vol_sliders = []
        self.layer_norm_cbs = []   # per-layer Normalize checkboxes
        self.layer_smooth_cbs = [] # per-layer Smooth checkboxes

        for i, layer_def in enumerate(LAYERS):
            row = QHBoxLayout()

            radio = QRadioButton(f"● {layer_def['name']}")
            radio.setStyleSheet(f"""
                QRadioButton {{ color: {layer_def['color']}; font-weight: bold; font-size: 12px; }}
                QRadioButton::indicator {{ width: 14px; height: 14px; }}
            """)
            if i == 0:
                radio.setChecked(True)
            self.layer_btn_group.addButton(radio, i)
            row.addWidget(radio)

            wave_combo = QComboBox()
            wave_combo.addItems(["sine", "square", "triangle", "sawtooth", "noise"])
            wave_combo.setCurrentText(layer_def["wave_default"])
            wave_combo.setStyleSheet("""
                QComboBox { background-color: #2d2d30; color: #ccc;
                            border: 1px solid #3f3f46; padding: 2px; min-width: 75px; }
            """)
            row.addWidget(wave_combo)
            self.layer_wave_combos.append(wave_combo)

            vol = QSlider(Qt.Orientation.Horizontal)
            vol.setRange(0, 100)
            vol.setValue(80)
            vol.setFixedWidth(55)
            vol.setStyleSheet(f"""
                QSlider::groove:horizontal {{ background: #3f3f46; height: 4px; }}
                QSlider::handle:horizontal {{
                    background: {layer_def['color']}; width: 12px;
                    margin: -4px 0; border-radius: 6px;
                }}
            """)
            row.addWidget(vol)
            self.layer_vol_sliders.append(vol)

            clr = QPushButton("✕")
            clr.setFixedSize(22, 22)
            clr.setStyleSheet(f"background: {layer_def['dim']}; color: {layer_def['color']}; font-weight: bold;")
            li = i
            clr.clicked.connect(lambda checked, idx=li: self.canvas.clear_layer(idx))
            row.addWidget(clr)

            layer_layout.addLayout(row)

            # --- Per-layer options row ---
            opts_row = QHBoxLayout()
            opts_row.setContentsMargins(20, 0, 0, 0)

            norm_cb = QCheckBox("Norm")
            norm_cb.setStyleSheet(f"QCheckBox {{ color: {layer_def['color']}; font-size: 10px; }}")
            norm_cb.setToolTip("Normalize this layer's audio to peak volume")
            opts_row.addWidget(norm_cb)
            self.layer_norm_cbs.append(norm_cb)

            smooth_cb = QCheckBox("Smooth")
            smooth_cb.setStyleSheet(f"QCheckBox {{ color: {layer_def['color']}; font-size: 10px; }}")
            smooth_cb.setToolTip("Interpolate between painted notes (glide/portamento)")
            opts_row.addWidget(smooth_cb)
            self.layer_smooth_cbs.append(smooth_cb)

            opts_row.addStretch()
            layer_layout.addLayout(opts_row)

        self.layer_btn_group.idToggled.connect(self._on_layer_changed)
        layer_group.setLayout(layer_layout)
        right_panel.addWidget(layer_group)

        # ======== Foley FX (context-sensitive per layer) ========
        self.fx_group = QGroupBox(f"Foley FX — 🔴 {LAYERS[0]['name']}")
        self.fx_group.setStyleSheet(f"QGroupBox {{ color: {LAYERS[0]['color']}; font-weight: bold; }}")
        fx_layout = QVBoxLayout()
        fx_layout.setSpacing(3)

        # Build all FX sliders with numeric spinboxes from definition table
        for fx_key, attr_name, label, lo, hi, color in FX_SLIDER_DEFS:
            row = QHBoxLayout()
            row.setSpacing(3)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {color}; font-size: 10px;")
            lbl.setFixedWidth(90)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(lo, hi)
            slider.setValue(FX_DEFAULTS[fx_key])
            spin = QSpinBox()
            spin.setRange(lo, hi)
            spin.setValue(FX_DEFAULTS[fx_key])
            spin.setFixedWidth(52)
            spin.setStyleSheet(
                f"QSpinBox {{ background: #2d2d30; color: {color};"
                f" border: 1px solid #3f3f46; font-size: 10px; }}")
            # Bidirectional link
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            row.addWidget(lbl)
            row.addWidget(slider, stretch=1)
            row.addWidget(spin)
            fx_layout.addLayout(row)
            setattr(self, attr_name, slider)

        self.fx_group.setLayout(fx_layout)
        right_panel.addWidget(self.fx_group)

        # ======== Actions ========
        right_panel.addStretch()

        self.btn_play = QPushButton("▶ Play SFX")
        self.btn_play.setStyleSheet(
            "background: #007acc; color: white; font-weight: bold; padding: 8px; border-radius: 4px;")
        self.btn_play.clicked.connect(self.play_sfx)
        right_panel.addWidget(self.btn_play)

        self.btn_default = QPushButton("↺ Default FX")
        self.btn_default.setStyleSheet(
            "background: #333; color: #ccc; padding: 6px; border-radius: 4px;")
        self.btn_default.clicked.connect(self._reset_fx_defaults)
        right_panel.addWidget(self.btn_default)

        self.btn_clear = QPushButton("🗑 Clear All")
        self.btn_clear.setStyleSheet(
            "background: #552222; color: white; padding: 6px; border-radius: 4px;")
        self.btn_clear.clicked.connect(self.canvas.clear_canvas)
        right_panel.addWidget(self.btn_clear)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        right_widget.setFixedWidth(300)
        layout.addWidget(right_widget)

    # ==========================================================
    #            LAYER / FX MANAGEMENT
    # ==========================================================

    def _save_fx_to_layer(self, layer_idx):
        """Saves current slider values into the layer's FX dict."""
        fx = self.layer_fx[layer_idx]
        for fx_key, attr_name, *_ in FX_SLIDER_DEFS:
            fx[fx_key] = getattr(self, attr_name).value()

    def _load_fx_from_layer(self, layer_idx):
        """Loads a layer's FX dict into the sliders (blocking signals to avoid loops)."""
        fx = self.layer_fx[layer_idx]
        for fx_key, attr_name, *_ in FX_SLIDER_DEFS:
            slider = getattr(self, attr_name)
            slider.blockSignals(True)
            slider.setValue(fx[fx_key])
            slider.blockSignals(False)

    def _update_fx_header(self, layer_idx):
        """Updates the FX group title to show which layer is active."""
        icons = ["🔴", "🔵", "🟡"]
        layer = LAYERS[layer_idx]
        self.fx_group.setTitle(f"Foley FX — {icons[layer_idx]} {layer['name']}")
        self.fx_group.setStyleSheet(f"QGroupBox {{ color: {layer['color']}; font-weight: bold; }}")

    def _on_layer_changed(self, button_id, checked):
        """When user switches active layer: save old FX, load new FX, update header."""
        if not checked:
            return
        # Save outgoing layer's FX
        self._save_fx_to_layer(self._active_fx_layer)
        # Switch
        self._active_fx_layer = button_id
        self.canvas.active_layer = button_id
        # Load incoming layer's FX
        self._load_fx_from_layer(button_id)
        self._update_fx_header(button_id)

    def _on_tool_changed(self, tool_id, checked):
        """Toolbar tool selection changed."""
        if not checked:
            return
        self.canvas.current_tool = tool_id
        # Update cursor
        cursors = {
            TOOL_PAINT: Qt.CursorShape.ArrowCursor,
            TOOL_ERASE: Qt.CursorShape.CrossCursor,
            TOOL_LINE:  Qt.CursorShape.UpArrowCursor,
            TOOL_CURVE: Qt.CursorShape.PointingHandCursor,
        }
        self.canvas.setCursor(cursors.get(tool_id, Qt.CursorShape.ArrowCursor))
        # Reset multi-click state when switching tools
        self.canvas._line_start = None
        self.canvas._curve_start = None
        self.canvas._curve_ctrl = None
        tool_names = {TOOL_PAINT: "Paint", TOOL_ERASE: "Erase",
                      TOOL_LINE: "Line", TOOL_CURVE: "Curve"}
        self.info_bar.setText(f"Tool: {tool_names.get(tool_id, '?')}")

    def _on_erase_size_changed(self, value):
        """Eraser size spinbox changed."""
        self.canvas.erase_size = value

    def _on_info_update(self, text):
        """Handle info signal from canvas."""
        self.info_bar.setText(text)

    # ==========================================================
    #            SERIALIZATION  (SFX save/load)
    # ==========================================================

    def get_state(self):
        """Returns the full SFX canvas state as a serializable dict."""
        # Save current active layer's FX before serializing
        self._save_fx_to_layer(self._active_fx_layer)

        layers = []
        for i in range(3):
            # Painted cells: list of [step, note] pairs
            cells = [[step, note] for (step, note) in self.canvas.layer_points[i].keys()]
            layers.append({
                "cells": cells,
                "wave": self.layer_wave_combos[i].currentText(),
                "volume": self.layer_vol_sliders[i].value(),
                "normalize": self.layer_norm_cbs[i].isChecked(),
                "smooth": self.layer_smooth_cbs[i].isChecked(),
                "fx": dict(self.layer_fx[i]),
            })

        return {
            "duration_cs": self.dur_slider.value(),
            "auto_trim": self.auto_trim_cb.isChecked(),
            "layers": layers,
        }

    def set_state(self, state):
        """Restores the SFX canvas from a state dict (produced by get_state)."""
        # Clear everything first
        self.canvas.clear_canvas()

        # Duration
        self.dur_slider.setValue(state.get("duration_cs", 50))
        self.auto_trim_cb.setChecked(state.get("auto_trim", True))

        # Layers
        for i, layer_state in enumerate(state.get("layers", [])):
            if i >= 3:
                break

            # Paint cells back onto the canvas
            for step, note in layer_state.get("cells", []):
                self.canvas.paint_note_block(step, note, i)

            # Wave / volume / checkboxes
            self.layer_wave_combos[i].setCurrentText(layer_state.get("wave", LAYERS[i]["wave_default"]))
            self.layer_vol_sliders[i].setValue(layer_state.get("volume", 80))
            self.layer_norm_cbs[i].setChecked(layer_state.get("normalize", False))
            self.layer_smooth_cbs[i].setChecked(layer_state.get("smooth", False))

            # FX
            fx = layer_state.get("fx", dict(FX_DEFAULTS))
            self.layer_fx[i] = {k: fx.get(k, v) for k, v in FX_DEFAULTS.items()}

        # Reload the active layer's FX into sliders
        self._load_fx_from_layer(self._active_fx_layer)
        self._update_fx_header(self._active_fx_layer)

    def _get_duration(self):
        return self.dur_slider.value() / 100.0

    def _reset_fx_defaults(self):
        """Resets the ACTIVE layer's FX to defaults."""
        self.layer_fx[self._active_fx_layer] = dict(FX_DEFAULTS)
        self._load_fx_from_layer(self._active_fx_layer)

    def _copy_fx_to_layer(self, target_idx):
        """Copies the active layer's FX to another layer."""
        self._save_fx_to_layer(self._active_fx_layer)
        self.layer_fx[target_idx] = dict(self.layer_fx[self._active_fx_layer])

    # ==========================================================
    #            RENDER ENGINE (Chord + Per-Layer FX)
    # ==========================================================

    def _generate_wave(self, wave_type, freq, total_samples, sample_rate):
        """Generate a single-frequency waveform buffer."""
        phase = np.cumsum(np.full(total_samples, freq) / sample_rate) * 2 * np.pi
        return self._wave_from_phase(wave_type, phase, total_samples, sample_rate, freq)

    def _generate_wave_from_envelope(self, wave_type, freq_env, total_samples, sample_rate):
        """Generate waveform from a frequency envelope (smooth mode)."""
        phase = np.cumsum(freq_env / sample_rate) * 2 * np.pi
        avg_freq = np.mean(freq_env)
        return self._wave_from_phase(wave_type, phase, total_samples, sample_rate, avg_freq)

    def _wave_from_phase(self, wave_type, phase, total_samples, sample_rate, ref_freq):
        """Core waveform generator from a phase array."""
        if wave_type == "sine":
            return np.sin(phase)
        elif wave_type == "square":
            return np.sign(np.sin(phase))
        elif wave_type == "triangle":
            t = phase / (2 * np.pi)
            return 2.0 * np.abs(2.0 * (t - np.floor(t + 0.5))) - 1.0
        elif wave_type == "sawtooth":
            t = phase / (2 * np.pi)
            return 2.0 * (t - np.floor(t + 0.5))
        elif wave_type == "noise":
            noise = np.random.uniform(-1, 1, total_samples)
            try:
                from scipy.ndimage import uniform_filter1d
                win = max(1, min(int(sample_rate / (ref_freq + 1)), 200))
                return uniform_filter1d(noise, win)
            except ImportError:
                return noise
        return np.sin(phase)

    def _render_layer(self, layer_idx, total_samples, sample_rate,
                      step_start, step_end):
        """
        Renders a single layer. Supports two modes:
        - Normal: per-note oscillators with gating (chords, staccato)
        - Smooth: frequency envelope interpolation (glide between notes)
        After rendering, optionally normalizes to peak amplitude.
        """
        points = self.canvas.layer_points[layer_idx]
        if not points:
            return None

        total_steps = step_end - step_start + 1
        samples_per_step = total_samples / total_steps
        ramp_len = max(1, int(0.001 * sample_rate))
        use_smooth = self.layer_smooth_cbs[layer_idx].isChecked()
        wave_type = self.layer_wave_combos[layer_idx].currentText()

        cells = []
        for (step, note_row) in points.keys():
            if step_start <= step <= step_end:
                cells.append((step - step_start, note_row))

        if not cells:
            return None

        if use_smooth:
            # --- SMOOTH MODE: frequency envelope interpolation ---
            # Build sorted (step, freq) pairs; average freqs if multiple notes at same step
            step_freqs = {}
            for (ls, nr) in cells:
                freq = row_to_freq(nr)
                if ls not in step_freqs:
                    step_freqs[ls] = []
                step_freqs[ls].append(freq)

            sorted_steps = sorted(step_freqs.keys())
            xp = []  # sample positions
            fp = []  # frequencies
            for s in sorted_steps:
                freqs = step_freqs[s]
                avg_freq = sum(freqs) / len(freqs)
                sample_pos = (s + 0.5) * samples_per_step  # center of step
                xp.append(sample_pos)
                fp.append(avg_freq)

            # Extend to edges
            if xp[0] > 0:
                xp.insert(0, 0)
                fp.insert(0, fp[0])
            if xp[-1] < total_samples - 1:
                xp.append(total_samples - 1)
                fp.append(fp[-1])

            freq_env = np.interp(np.arange(total_samples), xp, fp)
            layer_buf = self._generate_wave_from_envelope(
                wave_type, freq_env, total_samples, sample_rate)

            # Gate: only sound during painted steps
            gate = np.zeros(total_samples)
            for s in sorted_steps:
                s0 = max(0, min(int(s * samples_per_step), total_samples))
                s1 = max(0, min(int((s + 1) * samples_per_step), total_samples))
                gate[s0:s1] = 1.0
            # Smooth gate edges
            smoothed = gate.copy()
            for i in range(1, len(smoothed)):
                if smoothed[i] > smoothed[i - 1]:
                    r_start = max(0, i - ramp_len)
                    smoothed[r_start:i] = np.maximum(
                        smoothed[r_start:i], np.linspace(0, 1, i - r_start))
                elif smoothed[i] < smoothed[i - 1]:
                    r_end = min(len(smoothed), i + ramp_len)
                    smoothed[i:r_end] = np.minimum(
                        smoothed[i:r_end], np.linspace(1, 0, r_end - i))
            layer_buf *= smoothed
        else:
            # --- NORMAL MODE: per-note oscillators ---
            note_steps = {}
            for (ls, nr) in cells:
                if nr not in note_steps:
                    note_steps[nr] = []
                note_steps[nr].append(ls)
            for nr in note_steps:
                note_steps[nr].sort()

            layer_buf = np.zeros(total_samples)

            for note_row, steps_list in note_steps.items():
                freq = row_to_freq(note_row)
                osc = self._generate_wave(wave_type, freq, total_samples, sample_rate)

                gate = np.zeros(total_samples)
                for s in steps_list:
                    s0 = max(0, min(int(s * samples_per_step), total_samples))
                    s1 = max(0, min(int((s + 1) * samples_per_step), total_samples))
                    gate[s0:s1] = 1.0

                smoothed = gate.copy()
                for i in range(1, len(smoothed)):
                    if smoothed[i] > smoothed[i - 1]:
                        r_start = max(0, i - ramp_len)
                        smoothed[r_start:i] = np.maximum(
                            smoothed[r_start:i], np.linspace(0, 1, i - r_start))
                    elif smoothed[i] < smoothed[i - 1]:
                        r_end = min(len(smoothed), i + ramp_len)
                        smoothed[i:r_end] = np.minimum(
                            smoothed[i:r_end], np.linspace(1, 0, r_end - i))

                layer_buf += osc * smoothed

            n_voices = len(note_steps)
            if n_voices > 1:
                layer_buf /= np.sqrt(n_voices)

        # --- Normalize if checked ---
        if self.layer_norm_cbs[layer_idx].isChecked():
            peak = np.max(np.abs(layer_buf))
            if peak > 0.001:
                layer_buf /= peak

        return layer_buf

    def _apply_layer_fx(self, audio, total_samples, sample_rate, fx):
        """Applies the FX chain using a per-layer FX dict (not sliders)."""
        master = audio.copy()

        # --- Saturation ---
        sat = fx["sat"] / 100.0
        if sat > 0.01:
            drive = 1.0 + sat * 10.0
            master = np.tanh(master * drive) / np.tanh(drive)

        # --- Pitch sweep ---
        bend = fx["bend"] / 100.0
        if abs(bend) > 0.01:
            sweep = np.linspace(1.0, 1.0 + bend, total_samples)
            indices = np.cumsum(sweep)
            indices = (indices / indices[-1] * (total_samples - 1)).astype(int)
            indices = np.clip(indices, 0, total_samples - 1)
            master = master[indices]

        # --- Tremolo ---
        trem_depth = fx["trem"] / 100.0
        if trem_depth > 0.01:
            trem_hz = fx["trem_spd"]
            t = np.arange(total_samples) / sample_rate
            trem_lfo = 1.0 - trem_depth * 0.5 * (1.0 + np.sin(2 * np.pi * trem_hz * t))
            master *= trem_lfo

        # --- Vibrato ---
        vib_depth = fx["vib"] / 100.0
        if vib_depth > 0.01:
            vib_hz = fx["vib_spd"]
            t = np.arange(total_samples) / sample_rate
            max_shift = vib_depth * 40.0
            shift = max_shift * np.sin(2 * np.pi * vib_hz * t)
            indices = np.clip(np.arange(total_samples) + shift, 0, total_samples - 1).astype(int)
            master = master[indices]

        # --- Bit crush ---
        bit_depth = fx["bit"]
        if bit_depth < 16:
            quant_steps = 2 ** bit_depth
            master = np.round(master * quant_steps) / quant_steps

        # --- Echo (vectorized multi-tap) ---
        echo_fb = fx["echo"] / 100.0
        if echo_fb > 0.01:
            delay_samples = int((fx["echo_ms"] / 1000.0) * sample_rate)
            if 0 < delay_samples < total_samples:
                echo_out = master.copy()
                gain = echo_fb
                for tap in range(6):
                    offset = delay_samples * (tap + 1)
                    if offset >= total_samples:
                        break
                    echo_out[offset:] += master[:total_samples - offset] * gain
                    gain *= echo_fb
                master = echo_out

        # --- Ring modulation ---
        ring_mix = fx["ring"] / 100.0
        if ring_mix > 0.01:
            carrier_freq = fx["ring_hz"]
            t = np.arange(total_samples) / sample_rate
            carrier = np.sin(2 * np.pi * carrier_freq * t)
            master = (1.0 - ring_mix) * master + ring_mix * (master * carrier)

        # --- Detune (pitch shift via resampling) ---
        dtn_pct = fx.get("dtn", 0) / 100.0
        if dtn_pct > 0.01:
            cents = dtn_pct * 50.0  # 0-50 cents range
            ratio = 2.0 ** (cents / 1200.0)
            indices = np.clip(
                (np.arange(total_samples) * ratio).astype(int),
                0, total_samples - 1)
            master = master[indices]

        # --- Delay start (shift audio later in the buffer) ---
        dly_pct = fx.get("dly", 0) / 100.0
        if dly_pct > 0.01:
            delay_samples = int(dly_pct * total_samples * 0.5)
            if delay_samples > 0 and delay_samples < total_samples:
                shifted = np.zeros(total_samples)
                shifted[delay_samples:] = master[:total_samples - delay_samples]
                master = shifted

        # --- Attack / Release envelope ---
        att_pct = fx["att"]
        rel_pct = fx["rel"]
        if att_pct > 0 or rel_pct > 0:
            duration = total_samples / sample_rate
            amp_env = np.ones(total_samples)
            if att_pct > 0:
                att_n = min(int((att_pct / 100.0) * duration * sample_rate), total_samples)
                if att_n > 0:
                    amp_env[:att_n] = np.linspace(0, 1, att_n)
            if rel_pct > 0:
                rel_n = min(int((rel_pct / 100.0) * duration * sample_rate), total_samples)
                if rel_n > 0:
                    amp_env[-rel_n:] = np.linspace(1, 0, rel_n)
            master *= amp_env

        return np.clip(master, -0.98, 0.98)

    def render_sfx_to_array(self):
        """
        Renders all SFX layers with per-layer FX applied before mixing.
        Returns mono float32 array, or None if empty.
        """
        # Save current slider state to active layer before rendering
        self._save_fx_to_layer(self._active_fx_layer)

        sample_rate = 44100

        painted_range = self.canvas.get_painted_range()
        if painted_range is None:
            return None

        if self.auto_trim_cb.isChecked():
            step_start, step_end = painted_range
        else:
            step_start = 0
            step_end = self.canvas.steps - 1

        duration = self._get_duration()
        step_span = step_end - step_start + 1
        rendered_duration = max(0.01, duration * (step_span / self.canvas.steps))
        total_samples = int(rendered_duration * sample_rate)

        master = np.zeros(total_samples)
        active_count = 0

        for i in range(len(LAYERS)):
            layer_audio = self._render_layer(
                i, total_samples, sample_rate, step_start, step_end)
            if layer_audio is None:
                continue

            # Apply this layer's own FX chain
            layer_audio = self._apply_layer_fx(
                layer_audio, total_samples, sample_rate, self.layer_fx[i])

            volume = self.layer_vol_sliders[i].value() / 100.0
            master += layer_audio * volume
            active_count += 1

        if active_count == 0:
            return None

        master /= np.sqrt(active_count)
        return np.clip(master, -0.98, 0.98).astype(np.float32)

    def play_sfx(self):
        """Plays the rendered SFX."""
        audio = self.render_sfx_to_array()
        if audio is None:
            return
        try:
            sd.stop()
            sd.play(audio, samplerate=44100)
        except Exception as e:
            print("Audio Playback Error:", e)
