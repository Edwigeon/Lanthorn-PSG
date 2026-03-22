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
    from engine.constants import ROOT_A4_FREQ
    return ROOT_A4_FREQ * (2.0 ** ((midi_note - 69) / 12.0))

def midi_to_name(midi_note):
    """Convert MIDI note number to human-readable name like 'C4'."""
    octave = (midi_note // 12) - 1
    note = NOTE_NAMES[midi_note % 12]
    return f"{note}{octave}"


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
        
        # Canvas Range & Constraints
        self.base_midi = 36  # C2
        self.octaves = 5
        self.notes = self.octaves * 12 + 1
        self.scale_root = 0
        self.scale_notes = set(range(12)) # 0..11 Chromatic
        self.snap_to_scale = False

        self.cell_w = 12
        self.cell_h = 10
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self._update_scene_rect()
        
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

        self._line_start = None
        self._curve_start = None
        self._curve_ctrl = None
        self._preview_items = []
        self._pan_start = None
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def _update_scene_rect(self):
        self.scene.setSceneRect(-60, 0, self.steps * self.cell_w + 60, self.notes * self.cell_h)

    def rebuild_grid(self, base_oct, octs, root, scale_vals, snap):
        """Updates constraints and redraws the canvas."""
        self.base_midi = base_oct * 12 + 12
        self.octaves = octs
        self.notes = int(octs * 12 + 1)
        self.scale_root = root
        self.scale_notes = set(scale_vals)
        self.snap_to_scale = snap
        
        # Clear background grid items but keep painted cells!
        # Easiest way to only clear background is to remove non-painted items
        for item in self.scene.items():
            if item.zValue() <= 10: # background + text
                self.scene.removeItem(item)
                
        self._update_scene_rect()
        self.draw_grid()
        
        # Filter painted cells that are out of bounds
        for layer_idx in range(len(LAYERS)):
            points = self.layer_points[layer_idx]
            for key, rect in list(points.items()):
                step, note_row = key
                if note_row >= self.notes:
                    self.scene.removeItem(rect)
                    del points[key]

    def get_midi(self, row):
        return self.base_midi + (self.notes - 1 - row)

    def get_freq(self, row):
        return midi_to_freq(self.get_midi(row))
        
    def _is_in_scale(self, row):
        if len(self.scale_notes) == 12: return True
        midi = self.get_midi(row)
        rel = (midi - self.scale_root) % 12
        return rel in self.scale_notes

    def _snap_note(self, note):
        if note < 0: note = 0
        if note >= self.notes: note = self.notes - 1
        if not self.snap_to_scale or len(self.scale_notes) == 12:
            return note
        if self._is_in_scale(note):
            return note
            
        best_n = note
        dist = 999
        for n in range(self.notes):
            if self._is_in_scale(n):
                d = abs(n - note)
                if d < dist:
                    dist = d
                    best_n = n
        return best_n

    def draw_grid(self):
        pen_normal = QPen(QColor('#2a2a2e'))
        pen_octave = QPen(QColor('#444448'))
        pen_octave.setWidth(2)
        pen_c = QPen(QColor('#3a3a40'))
        font = QFont("Courier New", 7)
        font.setBold(True)

        for y in range(self.notes + 1):
            midi = self.get_midi(y) if y < self.notes else self.base_midi - 1
            if midi % 12 == 0:
                self.scene.addLine(0, y * self.cell_h, self.steps * self.cell_w, y * self.cell_h, pen_octave).setZValue(1)
            else:
                self.scene.addLine(0, y * self.cell_h, self.steps * self.cell_w, y * self.cell_h, pen_normal).setZValue(1)

            if y < self.notes:
                name = midi_to_name(midi)
                sharp = '#' in name or 'b' in name
                
                rel = (midi - self.scale_root) % 12
                is_root = (rel == 0)
                in_scale = (rel in self.scale_notes)
                
                bg_color = None
                if not in_scale:
                    bg_color = QColor('#151515') # Very dark
                elif sharp and len(self.scale_notes) == 12:
                    bg_color = QColor(20, 20, 22)
                elif is_root and len(self.scale_notes) < 12:
                    bg_color = QColor('#333344') # Highlight Root
                    
                if bg_color:
                    bg = QGraphicsRectItem(QRectF(0, y * self.cell_h, self.steps * self.cell_w, self.cell_h))
                    bg.setBrush(QBrush(bg_color))
                    bg.setPen(QPen(Qt.PenStyle.NoPen))
                    bg.setZValue(-1)
                    self.scene.addItem(bg)

                if is_root or midi % 12 == 4 or midi % 12 == 7 or len(self.scale_notes) < 12:
                    txt = QGraphicsTextItem(name)
                    txt.setFont(font)
                    txt.setDefaultTextColor(QColor('#00ff88') if is_root else QColor('#888') if in_scale else QColor('#444'))
                    txt.setPos(-56, y * self.cell_h - 3)
                    txt.setZValue(10)
                    self.scene.addItem(txt)

        for x in range(self.steps + 1):
            if x % 16 == 0:
                self.scene.addLine(x * self.cell_w, 0, x * self.cell_w, self.notes * self.cell_h, pen_octave).setZValue(1)
            elif x % 4 == 0:
                self.scene.addLine(x * self.cell_w, 0, x * self.cell_w, self.notes * self.cell_h, pen_c).setZValue(1)
            else:
                self.scene.addLine(x * self.cell_w, 0, x * self.cell_w, self.notes * self.cell_h, pen_normal).setZValue(1)

    # ---------- Cell helpers ----------
    def _pos_to_cell(self, pos):
        scene_pos = self.mapToScene(pos)
        step = int(scene_pos.x() // self.cell_w)
        note = int(scene_pos.y() // self.cell_h)
        if 0 <= step < self.steps and 0 <= note < self.notes:
            return (step, self._snap_note(note))
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
                    self._draw_cells(self._get_line_cells(self._line_start, (step, note)))
                    self._line_start = None
                    self._clear_previews()
                    self.info_signal.emit("Line drawn")
            elif self.current_tool == TOOL_CURVE:
                if self._curve_start is None:
                    self._curve_start = (step, note)
                    self.info_signal.emit("Curve: start set — click control point")
                elif self._curve_ctrl is None:
                    self._curve_ctrl = (step, note)
                    self.info_signal.emit("Curve: control set — click end point")
                else:
                    self._draw_cells(self._get_curve_cells(self._curve_start, self._curve_ctrl, (step, note)))
                    self._curve_start = None
                    self._curve_ctrl = None
                    self._clear_previews()
                    self.info_signal.emit("Curve drawn")
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_start = event.pos()
            event.accept()
            return

        cell = self._pos_to_cell(event.pos())
        if cell:
            step, note = cell
            midi = self.get_midi(note)
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
                
        # Draw live tool preview
        if cell:
            step, note = cell
            if self.current_tool == TOOL_LINE and self._line_start:
                cells = self._get_line_cells(self._line_start, (step, note))
                self._update_previews(cells)
            elif self.current_tool == TOOL_CURVE and self._curve_start:
                if self._curve_ctrl is None:
                    # Previewing from start to control point (straight line preview)
                    cells = self._get_line_cells(self._curve_start, (step, note))
                    self._update_previews(cells)
                else:
                    # Previewing final curve
                    cells = self._get_curve_cells(self._curve_start, self._curve_ctrl, (step, note))
                    self._update_previews(cells)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_drawing = False
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            parent = self.parent()
            if parent and hasattr(parent, '_on_tool_changed'):
                # Resets cursor to whatever the active tool is
                parent._on_tool_changed(self.current_tool, True)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
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

    # ---------- Tool Previews ----------
    def _clear_previews(self):
        for item in self._preview_items:
            self.scene.removeItem(item)
        self._preview_items.clear()

    def _update_previews(self, cells):
        self._clear_previews()
        color = QColor(LAYERS[self.active_layer]["color"])
        color.setAlpha(100) # Semi-transparent for preview
        brush = QBrush(color)
        pen = QPen(Qt.PenStyle.NoPen)
        
        for (step, note_row) in cells:
            x = step * self.cell_w
            y = note_row * self.cell_h
            rect = QGraphicsRectItem(QRectF(x, y, self.cell_w, self.cell_h))
            rect.setBrush(brush)
            rect.setPen(pen)
            rect.setZValue(20)
            self.scene.addItem(rect)
            self._preview_items.append(rect)

    def _draw_cells(self, cells):
        for step, note in cells:
            self.paint_note_block(step, note, self.active_layer)

    # ---------- Line tool (Bresenham) ----------
    def _get_line_cells(self, p0, p1):
        cells = []
        x0, y0 = p0
        x1, y1 = p1
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            if 0 <= x0 < self.steps and 0 <= y0 < self.notes:
                cells.append((x0, self._snap_note(y0)))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
        return cells

    # ---------- Curve tool (quadratic Bézier) ----------
    def _get_curve_cells(self, p0, ctrl, p2):
        cells = []
        dist = abs(p2[0] - p0[0]) + abs(p2[1] - p0[1])
        n_steps = max(dist * 2, 20)
        prev = None
        for i in range(n_steps + 1):
            t = i / n_steps
            x = (1 - t)**2 * p0[0] + 2*(1 - t)*t * ctrl[0] + t**2 * p2[0]
            y = (1 - t)**2 * p0[1] + 2*(1 - t)*t * ctrl[1] + t**2 * p2[1]
            cell = (int(round(x)), self._snap_note(int(round(y))))
            if cell != prev and 0 <= cell[0] < self.steps and 0 <= cell[1] < self.notes:
                cells.append(cell)
                prev = cell
        return cells

    # ---------- Context menu ----------
    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2d2d30; color: #cccccc; border: 1px solid #3f3f46; }
            QMenu::item:selected { background-color: #007acc; }
            QMenu::separator { background-color: #3f3f46; height: 1px; margin: 4px 8px; }
        """)

        # Tools quick-select
        tool_names = {TOOL_PAINT: "🖌 Paint", TOOL_ERASE: "🧹 Erase",
                      TOOL_LINE: "📏 Line", TOOL_CURVE: "〰 Curve"}
        for tid, tname in tool_names.items():
            icon = "●" if tid == self.current_tool else "○"
            action = menu.addAction(f"{icon} {tname}")
            action.setCheckable(True)
            action.setChecked(tid == self.current_tool)
            def make_tool_callback(tool_id):
                return lambda checked: self.parent().tool_btn_group.button(tool_id).setChecked(True) if hasattr(self.parent(), 'tool_btn_group') else None
            action.triggered.connect(make_tool_callback(tid))

        menu.addSeparator()

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

# ---------- FX Slot Widget (DAW Style) ----------
from gui.fx_ui_manager import FX_CATALOG

class FXSlotWidget(QGroupBox):
    """A dynamic widget that renders sliders for a single FX string (e.g., 'VIB 64')."""
    changed_signal = pyqtSignal()
    remove_requested = pyqtSignal()

    def __init__(self, fx_string, parent=None):
        super().__init__(parent)
        self._slider_widgets = []
        self._setup_ui(fx_string)

    def _setup_ui(self, fx_string):
        parts = fx_string.strip().split()
        self.code = parts[0].upper() if parts else ""
        self.param_str = parts[1] if len(parts) > 1 else "0"
        
        info = FX_CATALOG.get(self.code, {"name": self.code, "param_type": "byte", "desc": ""})
        self.param_type = info.get("param_type", "byte")

        # Header
        self.setTitle(f"🎛 {info['name']}")
        self.setStyleSheet("QGroupBox { border: 1px solid #3f3f46; margin-top: 10px; color: #aaa; font-weight: bold; } "
                           "QGroupBox::title { subcontrol-origin: margin; left: 8px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(2)

        # Header close button (placed top right via layout hack)
        header_row = QHBoxLayout()
        header_row.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(20, 20)
        btn_close.setStyleSheet("background: #552222; color: #fff; border: none; font-weight: bold;")
        btn_close.clicked.connect(self.remove_requested.emit)
        header_row.addWidget(btn_close)
        layout.addLayout(header_row)

        try:
            val = int(self.param_str)
        except ValueError:
            val = 0

        # Build controls based on param type
        if self.param_type == "dual":
            p1 = (val >> 4) & 0xF
            p2 = val & 0xF
            for i, lbl_txt in enumerate(info.get("dual_labels", ("Param 1", "Param 2"))):
                layout.addLayout(self._build_slider_row(lbl_txt, 0, 15, p1 if i==0 else p2))
        elif self.param_type == "adsr":
            parts_arr = self.param_str.split(".")
            labels = ["Attack", "Decay", "Sustain", "Release"]
            for i in range(4):
                v = int(parts_arr[i]) if i < len(parts_arr) else 0
                layout.addLayout(self._build_slider_row(labels[i], 0, 100, v))
        else: # byte
            layout.addLayout(self._build_slider_row(info.get("byte_label", "Level (0-255)"), 0, 255, val))

    def _build_slider_row(self, label_text, min_val, max_val, init_val):
        row = QHBoxLayout()
        lbl = QLabel(label_text.split("  ")[0]) # Short label
        lbl.setStyleSheet("color: #ccc; font-size: 10px;")
        lbl.setFixedWidth(50)
        
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(init_val)
        slider.setStyleSheet("""
            QSlider::groove:horizontal { background: #3f3f46; height: 4px; }
            QSlider::handle:horizontal { background: #007acc; width: 10px; margin: -3px 0; border-radius: 5px; }
        """)
        
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(init_val)
        spin.setFixedWidth(45)
        spin.setStyleSheet("QSpinBox { background: #2d2d30; color: #00ff88; border: 1px solid #3f3f46; font-size: 10px; }")
        
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        slider.valueChanged.connect(lambda _: self.changed_signal.emit())
        
        row.addWidget(lbl)
        row.addWidget(slider, stretch=1)
        row.addWidget(spin)
        
        self._slider_widgets.append(slider)
        return row

    def get_fx_string(self):
        if self.param_type == "dual":
            v1 = self._slider_widgets[0].value() if len(self._slider_widgets) > 0 else 0
            v2 = self._slider_widgets[1].value() if len(self._slider_widgets) > 1 else 0
            combined = (v1 << 4) | v2
            return f"{self.code} {combined}"
        elif self.param_type == "adsr":
            vals = [str(w.value()) for w in self._slider_widgets]
            return f"{self.code} {'.'.join(vals)}"
        else:
            v = self._slider_widgets[0].value() if len(self._slider_widgets) > 0 else 0
            return f"{self.code} {v}"



# ============================================================
#                    SFX Canvas (Main Widget)
# ============================================================
class SfxCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Per-layer FX string storage
        self.layer_fx_chain = [[], [], []]
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

        # ======== Canvas Options & Scale Constraints ========
        options_bar = QHBoxLayout()
        options_bar.setSpacing(6)
        lbl_style = "color: #aaa; font-size: 11px; font-weight: bold;"
        spin_style = "QSpinBox { background: #2d2d30; color: #fff; border: 1px solid #3f3f46; }"
        combo_style = "QComboBox { background: #2d2d30; color: #ccc; border: 1px solid #3f3f46; padding: 2px; } QComboBox::drop-down { border: none; }"
        
        # Base Octave
        lbl1 = QLabel("Base Oct:")
        lbl1.setStyleSheet(lbl_style)
        options_bar.addWidget(lbl1)
        self.base_oct_spin = QSpinBox()
        self.base_oct_spin.setRange(0, 8)
        self.base_oct_spin.setValue(2) # C2
        self.base_oct_spin.setFixedWidth(35)
        self.base_oct_spin.setStyleSheet(spin_style)
        self.base_oct_spin.valueChanged.connect(self._on_canvas_options_changed)
        options_bar.addWidget(self.base_oct_spin)

        # Octaves
        lbl2 = QLabel("Range (Octs):")
        lbl2.setStyleSheet(lbl_style)
        options_bar.addWidget(lbl2)
        self.range_oct_spin = QSpinBox()
        self.range_oct_spin.setRange(1, 8)
        self.range_oct_spin.setValue(5)
        self.range_oct_spin.setFixedWidth(35)
        self.range_oct_spin.setStyleSheet(spin_style)
        self.range_oct_spin.valueChanged.connect(self._on_canvas_options_changed)
        options_bar.addWidget(self.range_oct_spin)

        # Key
        lbl3 = QLabel("Key:")
        lbl3.setStyleSheet(lbl_style)
        options_bar.addWidget(lbl3)
        self.key_combo = QComboBox()
        self.key_combo.addItems(NOTE_NAMES)
        self.key_combo.setStyleSheet(combo_style)
        self.key_combo.currentIndexChanged.connect(self._on_canvas_options_changed)
        options_bar.addWidget(self.key_combo)

        # Scale
        lbl4 = QLabel("Scale:")
        lbl4.setStyleSheet(lbl_style)
        options_bar.addWidget(lbl4)
        self.scale_combo = QComboBox()
        self.scale_combo.addItems([
            "Chromatic", "Major", "Minor", "Pentatonic Major", "Pentatonic Minor", 
            "Harmonic Minor", "Dorian", "Mixolydian", "Diminished (W-H)", "Diminished (H-W)"
        ])
        self.scale_combo.setStyleSheet(combo_style)
        self.scale_combo.currentIndexChanged.connect(self._on_canvas_options_changed)
        options_bar.addWidget(self.scale_combo)

        # Snap
        self.snap_cb = QCheckBox("Snap to Scale")
        self.snap_cb.setChecked(False)
        self.snap_cb.setStyleSheet("QCheckBox { color: #fff; font-weight: bold; }")
        self.snap_cb.stateChanged.connect(self._on_canvas_options_changed)
        options_bar.addWidget(self.snap_cb)

        options_bar.addStretch()
        left_column.addLayout(options_bar)

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

        # ======== Foley FX (Scrollable Channel Strip) ========
        self.fx_group = QGroupBox(f"Foley FX — 🔴 {LAYERS[0]['name']}")
        self.fx_group.setStyleSheet(f"QGroupBox {{ color: {LAYERS[0]['color']}; font-weight: bold; }}")
        fx_main_layout = QVBoxLayout()
        fx_main_layout.setSpacing(4)
        fx_main_layout.setContentsMargins(4, 12, 4, 4)

        # "Add FX" Button
        self.btn_add_fx = QPushButton("➕ Add FX")
        self.btn_add_fx.setStyleSheet("background: #264f78; color: white; padding: 4px; border-radius: 3px;")
        self.btn_add_fx.clicked.connect(self._show_add_fx_menu)
        fx_main_layout.addWidget(self.btn_add_fx)

        # Scroll Area for FX Slots
        from PyQt6.QtWidgets import QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.fx_scroll_widget = QWidget()
        self.fx_scroll_widget.setStyleSheet("background: transparent;")
        self.fx_scroll_layout = QVBoxLayout(self.fx_scroll_widget)
        self.fx_scroll_layout.setSpacing(4)
        self.fx_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.fx_scroll_layout.addStretch()
        
        scroll_area.setWidget(self.fx_scroll_widget)
        fx_main_layout.addWidget(scroll_area, stretch=1)

        self.fx_group.setLayout(fx_main_layout)
        right_panel.addWidget(self.fx_group, stretch=1)

        # ======== Actions ========
        right_panel.addStretch()

        self.btn_play = QPushButton("▶ Play SFX")
        self.btn_play.setStyleSheet(
            "background: #007acc; color: white; font-weight: bold; padding: 8px; border-radius: 4px;")
        self.btn_play.clicked.connect(self.play_sfx)
        right_panel.addWidget(self.btn_play)

        self.btn_default = QPushButton("↺ Clear Layer FX")
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
    #            CANVAS OPTIONS API
    # ==========================================================
    
    def _on_canvas_options_changed(self, *args):
        base_oct = self.base_oct_spin.value()
        octs = self.range_oct_spin.value()
        root = self.key_combo.currentIndex()
        scale_name = self.scale_combo.currentText()
        snap = self.snap_cb.isChecked()
        
        SCALE_MAP = {
            "Chromatic": range(12),
            "Major": [0, 2, 4, 5, 7, 9, 11],
            "Minor": [0, 2, 3, 5, 7, 8, 10],
            "Pentatonic Major": [0, 2, 4, 7, 9],
            "Pentatonic Minor": [0, 3, 5, 7, 10],
            "Harmonic Minor": [0, 2, 3, 5, 7, 8, 11],
            "Dorian": [0, 2, 3, 5, 7, 9, 10],
            "Mixolydian": [0, 2, 4, 5, 7, 9, 10],
            "Diminished (W-H)": [0, 2, 3, 5, 6, 8, 9, 11],
            "Diminished (H-W)": [0, 1, 3, 4, 6, 7, 9, 10]
        }
        scale_vals = SCALE_MAP.get(scale_name, range(12))
        
        self.canvas.rebuild_grid(base_oct, octs, root, scale_vals, snap)
        
    # ==========================================================
    #            LAYER / FX MANAGEMENT
    # ==========================================================

    def _show_add_fx_menu(self):
        from PyQt6.QtWidgets import QMenu
        from gui.fx_ui_manager import FX_CATALOG
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2d2d30; color: #ccc; border: 1px solid #3f3f46; }
            QMenu::item:selected { background-color: #007acc; }
        """)
        cats = {}
        for code, info in FX_CATALOG.items():
            if info.get("category") == "🎛 Master Mix":
                continue
            cat = info.get("category", "Other")
            if cat not in cats: cats[cat] = []
            cats[cat].append((info["name"], code))
            
        for cat, items in cats.items():
            sub = menu.addMenu(cat)
            for name, code in items:
                action = sub.addAction(f"{name} ({code})")
                action.triggered.connect(lambda checked, c=code: self._add_fx_slot(f"{c} 64"))
        
        pos = self.btn_add_fx.mapToGlobal(self.btn_add_fx.rect().bottomLeft())
        menu.exec(pos)

    def _add_fx_slot(self, fx_string):
        slot = FXSlotWidget(fx_string, parent=self.fx_scroll_widget)
        slot.remove_requested.connect(lambda: self._remove_fx_slot(slot))
        slot.changed_signal.connect(self._save_fx_to_layer)
        
        # Insert before the stretch at the end
        idx = max(0, self.fx_scroll_layout.count() - 1)
        self.fx_scroll_layout.insertWidget(idx, slot)
        self._save_fx_to_layer()

    def _remove_fx_slot(self, slot):
        self.fx_scroll_layout.removeWidget(slot)
        slot.deleteLater()
        self._save_fx_to_layer()

    def _save_fx_to_layer(self):
        """Saves current slots to the active layer's internal chain."""
        chain = []
        for i in range(self.fx_scroll_layout.count() - 1): # exclude stretch
            item = self.fx_scroll_layout.itemAt(i)
            if item and item.widget():
                chain.append(item.widget().get_fx_string())
        self.layer_fx_chain[self._active_fx_layer] = chain

    def _load_fx_from_layer(self, layer_idx):
        """Builds UI slots for the current layer."""
        # Clear existing slots
        while self.fx_scroll_layout.count() > 1:
            item = self.fx_scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # Rebuild
        chain = self.layer_fx_chain[layer_idx]
        for fx_str in chain:
            self._add_fx_slot(fx_str)

    def _update_fx_header(self, layer_idx):
        """Updates the FX group title to show which layer is active."""
        icons = ["🔴", "🔵", "🟡"]
        layer = LAYERS[layer_idx]
        self.fx_group.setTitle(f"Foley FX — {icons[layer_idx]} {layer['name']}")
        self.fx_group.setStyleSheet(f"QGroupBox {{ color: {layer['color']}; font-weight: bold; }}")

    def _on_layer_changed(self, button_id, checked):
        """When user switches active layer: switch the UI slots, update header."""
        if not checked:
            return
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
                "fx_chain": list(self.layer_fx_chain[i]),
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

            # FX Chain
            chain = layer_state.get("fx_chain", [])
            self.layer_fx_chain[i] = list(chain)

        # Reload the active layer's FX into slots
        self._load_fx_from_layer(self._active_fx_layer)
        self._update_fx_header(self._active_fx_layer)

    def _get_duration(self):
        return self.dur_slider.value() / 100.0

    def _reset_fx_defaults(self):
        """Clears the ACTIVE layer's FX."""
        self.layer_fx_chain[self._active_fx_layer] = []
        self._load_fx_from_layer(self._active_fx_layer)

    def _copy_fx_to_layer(self, target_idx):
        """Copies the active layer's FX chain to another layer."""
        self.layer_fx_chain[target_idx] = list(self.layer_fx_chain[self._active_fx_layer])

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
                freq = self.canvas.get_freq(nr)
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
            # Smooth gate edges (vectorized)
            smoothed = gate.copy()
            edges = np.diff(gate)
            rise_idx = np.where(edges > 0)[0] + 1   # indices where gate goes 0→1
            fall_idx = np.where(edges < 0)[0] + 1   # indices where gate goes 1→0
            for idx in rise_idx:
                r_start = max(0, idx - ramp_len)
                ramp = np.linspace(0, 1, idx - r_start)
                smoothed[r_start:idx] = np.maximum(smoothed[r_start:idx], ramp)
            for idx in fall_idx:
                r_end = min(len(smoothed), idx + ramp_len)
                ramp = np.linspace(1, 0, r_end - idx)
                smoothed[idx:r_end] = np.minimum(smoothed[idx:r_end], ramp)
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
                freq = self.canvas.get_freq(note_row)
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

    def _apply_layer_fx(self, audio, total_samples, sample_rate, layer_idx):
        """Applies the FX chain using the string stack."""
        master = audio.copy()
        chain = self.layer_fx_chain[layer_idx]

        from engine.playback import Sequencer
        parsed_fx = []
        for fx_str in chain:
            parsed_fx.extend(Sequencer._parse_fx_stack(fx_str))

        for cmd, param in parsed_fx:
            if not cmd:
                continue
            try:
                p_full = int(param)
                p1 = (p_full >> 4) & 0xF
                p2 = p_full & 0xF
            except ValueError:
                continue

            if cmd == "VOL":
                master *= (p_full / 255.0)

            elif cmd == "SAT":
                sat = p_full / 255.0
                if sat > 0.01:
                    drive = 1.0 + sat * 10.0
                    master = np.tanh(master * drive) / np.tanh(drive)

            elif cmd == "BND":
                bend = (p_full - 128) / 128.0
                if abs(bend) > 0.01:
                    sweep = np.linspace(1.0, 1.0 + bend, total_samples)
                    indices = np.cumsum(sweep)
                    indices = (indices / indices[-1] * (total_samples - 1)).astype(int)
                    indices = np.clip(indices, 0, total_samples - 1)
                    master = master[indices]

            elif cmd == "TRM":
                trem_depth = p2 / 15.0
                if trem_depth > 0.01:
                    trem_hz = 1.0 + p1
                    t = np.arange(total_samples) / sample_rate
                    trem_lfo = 1.0 - trem_depth * 0.5 * (1.0 + np.sin(2 * np.pi * trem_hz * t))
                    master *= trem_lfo

            elif cmd == "VIB":
                vib_depth = p2 / 15.0
                if vib_depth > 0.01:
                    vib_hz = 1.0 + p1
                    t = np.arange(total_samples) / sample_rate
                    max_shift = vib_depth * 40.0
                    shift = max_shift * np.sin(2 * np.pi * vib_hz * t)
                    indices = np.clip(np.arange(total_samples) + shift, 0, total_samples - 1).astype(int)
                    master = master[indices]

            elif cmd == "BIT":
                bit_depth = 4 + p_full % 13
                if bit_depth < 16:
                    quant_steps = 2 ** bit_depth
                    master = np.round(master * quant_steps) / quant_steps

            elif cmd == "ECH":
                echo_fb = p2 / 15.0
                if echo_fb > 0.01:
                    delay_ms = max(10, p1 * 50)
                    delay_samples = int((delay_ms / 1000.0) * sample_rate)
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

            elif cmd == "RNG":
                ring_mix = p_full / 255.0
                if ring_mix > 0.01:
                    carrier_freq = 300.0 + (p_full / 255.0) * 1700.0
                    t = np.arange(total_samples) / sample_rate
                    carrier = np.sin(2 * np.pi * carrier_freq * t)
                    master = (1.0 - ring_mix) * master + ring_mix * (master * carrier)

            elif cmd == "DTN":
                cents = (p_full / 255.0) * 50.0
                if cents > 0.01:
                    ratio = 2.0 ** (cents / 1200.0)
                    indices = np.clip(
                        (np.arange(total_samples) * ratio).astype(int),
                        0, total_samples - 1)
                    master = master[indices]

            elif cmd == "DLY":
                dly_pct = p_full / 255.0
                if dly_pct > 0.01:
                    shift = int(dly_pct * total_samples * 0.5)
                    out = np.zeros_like(master)
                    if shift < len(out):
                        out[shift:] = master[:len(out) - shift] * 0.8
                    master = out

            elif cmd == "ENV":
                parts = param.split(".")
                att = int(parts[0]) if len(parts) > 0 else 0
                dec = int(parts[1]) if len(parts) > 1 else 0
                sus = int(parts[2]) if len(parts) > 2 else 100
                rel = int(parts[3]) if len(parts) > 3 else 0
                
                duration = total_samples / sample_rate
                amp_env = np.ones(total_samples)
                
                # Attack
                if att > 0:
                    att_n = min(int((att / 100.0) * duration * sample_rate), total_samples)
                    if att_n > 0:
                        amp_env[:att_n] = np.linspace(0, 1, att_n)
                # Release
                if rel > 0:
                    rel_n = min(int((rel / 100.0) * duration * sample_rate), total_samples)
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
        self._save_fx_to_layer()

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

        master_mix = np.zeros(total_samples)
        active_count = 0

        # Generate final mix for valid layers
        for i in range(3):
            buf = self._render_layer(i, total_samples, sample_rate, step_start, step_end)
            if buf is not None:
                # Apply the DAW-style FX slots
                buf = self._apply_layer_fx(buf, total_samples, sample_rate, i)
                # Apply individual layer volume
                vol = self.layer_vol_sliders[i].value() / 100.0
                master_mix += buf * vol * 0.6
                active_count += 1

        if active_count == 0:
            return None

        master_mix /= np.sqrt(active_count)
        return np.clip(master_mix, -0.98, 0.98).astype(np.float32)

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
