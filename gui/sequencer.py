# gui/sequencer.py — Graphical Pattern Sequencer (Phase 5)
"""
A snap-together sequential arranger with volume & pan automation.
Patterns are placed end-to-end in order — no gaps, no overlaps.
Below the pattern lane, two automation lanes allow drawing volume
and stereo pan curves across the arrangement.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QGraphicsView,
    QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsEllipseItem, QGraphicsPathItem,
    QMenu, QFrame, QGraphicsLineItem
)
from PyQt6.QtGui import (
    QBrush, QColor, QPen, QFont, QPainter, QDrag,
    QLinearGradient, QPainterPath
)
from PyQt6.QtCore import (
    Qt, QPointF, QMimeData, pyqtSignal, QTimer, QRectF
)

# ── Layout Constants ───────────────────────────────────────────────
STEP_PX          = 6       # px per step (very small — zoom handles scale)
PAT_LANE_H       = 80      # pattern blocks lane height
AUTO_LANE_H      = 60      # each automation lane height
RULER_H          = 22      # top ruler
GAP              = 4       # spacing between lanes
HANDLE_R         = 5       # automation handle radius
MIN_ZOOM         = 0.1
MAX_ZOOM         = 10.0
COLORS = [
    "#2979FF", "#00C853", "#FF6D00", "#D500F9",
    "#FFD600", "#00BFA5", "#FF1744", "#651FFF",
    "#00B0FF", "#76FF03", "#FF9100", "#E040FB",
]
BTN = ("QPushButton{padding:5px 12px;border-radius:4px;font-weight:bold;"
       "font-family:'Courier New';font-size:11px;}")


# ═══════════════════════════════════════════════════════════════════
#   PATTERN BLOCK
# ═══════════════════════════════════════════════════════════════════
class PatternBlock(QGraphicsRectItem):
    """A pattern in the sequential arrangement."""

    def __init__(self, index, pat_id, pat_name, length, color_idx, scene_ref):
        w = length * STEP_PX
        h = PAT_LANE_H - 4
        super().__init__(0, 0, w, h)
        self.idx = index
        self.pat_id = pat_id
        self.pat_name = pat_name
        self.length = length
        self._scene = scene_ref

        # Gradient
        base = QColor(COLORS[color_idx % len(COLORS)])
        self._base = base
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, base.lighter(125))
        g.setColorAt(1, base.darker(125))
        self.setBrush(QBrush(g))
        self.setPen(QPen(base.darker(150), 1.5))
        self.setOpacity(0.90)
        self.setZValue(10)
        self.setAcceptHoverEvents(True)

        # Name label (centered)
        self._label = QGraphicsTextItem(pat_name, self)
        self._label.setDefaultTextColor(Qt.GlobalColor.white)
        fs = min(14, max(8, int(w * 0.12)))
        self._label.setFont(QFont("Courier New", fs, QFont.Weight.Bold))
        lw = self._label.boundingRect().width()
        lh = self._label.boundingRect().height()
        self._label.setPos(max(3, (w - lw) / 2), max(2, (h - lh) / 2 - 6))

        # Step count (below name)
        self._sub = QGraphicsTextItem(f"{length}", self)
        self._sub.setDefaultTextColor(QColor(255, 255, 255, 130))
        self._sub.setFont(QFont("Courier New", 7))
        sw = self._sub.boundingRect().width()
        self._sub.setPos(max(3, (w - sw) / 2), h - 16)

    def hoverEnterEvent(self, e):
        self.setOpacity(1.0)
        self.setPen(QPen(QColor("#ffffff"), 2))
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self.setOpacity(0.90)
        self.setPen(QPen(self._base.darker(150), 1.5))
        super().hoverLeaveEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self._scene:
            self._scene._preview_pattern(self.pat_id)
        super().mouseDoubleClickEvent(e)

    def contextMenuEvent(self, e):
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu{background:#1e1e3a;color:#ccc;border:1px solid #3a3a5a;"
            "font-family:'Courier New';font-size:11px;}"
            "QMenu::item{padding:6px 16px;}"
            "QMenu::item:selected{background:#0066cc;color:white;}"
            "QMenu::separator{background:#3a3a5a;height:1px;}")
        prev = menu.addAction("▶  Preview")
        menu.addSeparator()
        dup = menu.addAction("📋  Duplicate After")
        ins = menu.addAction("📌  Insert Before...")
        menu.addSeparator()
        mv_l = menu.addAction("◀  Move Left")
        mv_r = menu.addAction("▶  Move Right")
        menu.addSeparator()
        rm = menu.addAction("🗑  Remove")

        a = menu.exec(e.screenPos())
        if not self._scene:
            return
        if a == prev:
            self._scene._preview_pattern(self.pat_id)
        elif a == dup:
            self._scene.insert_after(self.idx, self.pat_id)
        elif a == ins:
            self._scene.show_insert_menu(self.idx, e.screenPos())
        elif a == mv_l:
            self._scene.move_block(self.idx, -1)
        elif a == mv_r:
            self._scene.move_block(self.idx, 1)
        elif a == rm:
            self._scene.remove_block(self.idx)


# ═══════════════════════════════════════════════════════════════════
#   AUTOMATION HANDLE (draggable point on vol/pan lane)
# ═══════════════════════════════════════════════════════════════════
class AutoHandle(QGraphicsEllipseItem):
    """A draggable control point for automation lanes."""

    def __init__(self, x, y, lane_top, lane_h, color, scene_ref, lane_key, point_idx):
        r = HANDLE_R
        super().__init__(-r, -r, r * 2, r * 2)
        self.setBrush(QBrush(QColor(color)))
        self.setPen(QPen(QColor(color).lighter(140), 1.5))
        self.setPos(x, y)
        self.setZValue(30)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self._lane_top = lane_top
        self._lane_h = lane_h
        self._scene = scene_ref
        self._lane_key = lane_key
        self._point_idx = point_idx

    def itemChange(self, change, value):
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionChange:
            # Constrain to lane bounds
            x = max(0, value.x())
            y = max(self._lane_top, min(self._lane_top + self._lane_h, value.y()))
            return QPointF(x, y)
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionHasChanged:
            if self._scene:
                self._scene._on_handle_moved(self._lane_key)
        return super().itemChange(change, value)

    def hoverEnterEvent(self, e):
        self.setScale(1.4)
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self.setScale(1.0)
        super().hoverLeaveEvent(e)

    def contextMenuEvent(self, e):
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu{background:#1e1e3a;color:#ccc;border:1px solid #3a3a5a;}"
            "QMenu::item:selected{background:#0066cc;color:white;}")
        rm = menu.addAction("🗑  Remove Point")
        if menu.exec(e.screenPos()) == rm:
            self._scene._remove_auto_point(self._lane_key, self._point_idx)


# ═══════════════════════════════════════════════════════════════════
#   SEQUENCER SCENE
# ═══════════════════════════════════════════════════════════════════
class SequencerScene(QGraphicsScene):
    order_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracker = None
        self._pattern_lengths = {}
        self._pattern_names = {}
        self._color_map = {}
        self._next_color = 0

        # Arrangement: ordered list of pat_ids
        self._order = []
        self._blocks = []

        # Automation: list of (step_x, value_0_to_1) tuples
        self._auto_data = {
            "vol": [(0, 0.8)],   # start at 80% volume
            "pan": [(0, 0.5)],   # center pan
        }
        self._auto_handles = {"vol": [], "pan": []}
        self._auto_paths = {"vol": None, "pan": None}
        self._auto_fills = {"vol": None, "pan": None}
        self._auto_labels = {}

        self._build()

    def _total_steps(self):
        return sum(self._pattern_lengths.get(p, 64) for p in self._order)

    def _build(self):
        """Full rebuild of the scene."""
        self.clear()
        self._blocks.clear()
        self._auto_handles = {"vol": [], "pan": []}
        self._auto_paths = {"vol": None, "pan": None}
        self._auto_fills = {"vol": None, "pan": None}
        self._auto_labels.clear()

        total = max(self._total_steps(), 64)
        w = total * STEP_PX + 40  # padding

        # Lane Y positions
        self._pat_y = RULER_H
        self._vol_y = RULER_H + PAT_LANE_H + GAP
        self._pan_y = self._vol_y + AUTO_LANE_H + GAP
        scene_h = self._pan_y + AUTO_LANE_H + 10

        self.setBackgroundBrush(QBrush(QColor("#101028")))

        # ── Ruler ──
        ruler_bg = self.addRect(0, 0, w, RULER_H,
                                QPen(Qt.PenStyle.NoPen), QBrush(QColor("#16163a")))
        ruler_bg.setZValue(-20)

        pen_tick = QPen(QColor("#3a3a5a"), 0.5)
        pen_major = QPen(QColor("#5a5a7a"), 1.0)
        font = QFont("Courier New", 7)

        for s in range(0, total + 1, 4):
            x = s * STEP_PX
            if s % 16 == 0:
                self.addLine(x, 0, x, scene_h, pen_major).setZValue(-5)
                txt = self.addText(str(s), font)
                txt.setDefaultTextColor(QColor("#8888aa"))
                txt.setPos(x + 2, 3)
                txt.setZValue(-4)
            else:
                self.addLine(x, RULER_H, x, RULER_H + PAT_LANE_H, pen_tick).setZValue(-8)

        # ── Pattern Lane Background ──
        self.addRect(0, self._pat_y, w, PAT_LANE_H,
                     QPen(QColor("#252548"), 1), QBrush(QColor("#181838"))).setZValue(-10)

        # ── Pattern Blocks ──
        x_cursor = 0
        for i, pid in enumerate(self._order):
            length = self._pattern_lengths.get(pid, 64)
            name = self._pattern_names.get(pid, pid)
            ci = self._get_color(pid)
            block = PatternBlock(i, pid, name, length, ci, self)
            block.setPos(x_cursor * STEP_PX, self._pat_y + 2)
            self.addItem(block)
            self._blocks.append(block)
            x_cursor += length

        # ── Volume Lane ──
        self._draw_auto_lane("vol", self._vol_y, w, "#00CC66", "VOL")

        # ── Pan Lane ──
        self._draw_auto_lane("pan", self._pan_y, w, "#FF9900", "PAN")

        self.setSceneRect(0, 0, w, scene_h)

    def _draw_auto_lane(self, key, y, w, color, label):
        """Draws an automation lane with its handles and curve."""
        # Background
        bg = self.addRect(0, y, w, AUTO_LANE_H,
                          QPen(QColor("#252548"), 1), QBrush(QColor("#141430")))
        bg.setZValue(-10)

        # Center line (0dB / center pan)
        if key == "pan":
            cy = y + AUTO_LANE_H / 2
            self.addLine(0, cy, w, AUTO_LANE_H / 2 + y, QPen(QColor("#333355"), 0.5,
                         Qt.PenStyle.DashLine)).setZValue(-5)

        # Label
        lbl = self.addText(label, QFont("Courier New", 8, QFont.Weight.Bold))
        lbl.setDefaultTextColor(QColor(color))
        lbl.setPos(4, y + 2)
        lbl.setZValue(25)
        self._auto_labels[key] = lbl

        # Draw automation curve + handles
        self._rebuild_auto(key, y, color)

    def _rebuild_auto(self, key, y=None, color=None):
        """Redraws the automation curve and handles for a lane."""
        if y is None:
            y = self._vol_y if key == "vol" else self._pan_y
        if color is None:
            color = "#00CC66" if key == "vol" else "#FF9900"

        # Remove old path
        try:
            if self._auto_paths.get(key):
                self.removeItem(self._auto_paths[key])
        except Exception:
            pass
        self._auto_paths[key] = None

        # Remove old fill
        try:
            if self._auto_fills.get(key):
                self.removeItem(self._auto_fills[key])
        except Exception:
            pass
        self._auto_fills[key] = None

        # Remove old handles
        for h in list(self._auto_handles.get(key, [])):
            try:
                self.removeItem(h)
            except Exception:
                pass
        self._auto_handles[key] = []

        points = sorted(self._auto_data.get(key, []), key=lambda p: p[0])
        if not points:
            return

        total = max(self._total_steps(), 64)

        # Build path
        path = QPainterPath()
        first = True
        for step_x, val in points:
            px = step_x * STEP_PX
            py = y + AUTO_LANE_H * (1.0 - val)  # 1=top, 0=bottom
            if first:
                path.moveTo(px, py)
                first = False
            else:
                path.lineTo(px, py)

        # Extend to end
        last_val = points[-1][1]
        path.lineTo(total * STEP_PX, y + AUTO_LANE_H * (1.0 - last_val))

        path_item = QGraphicsPathItem(path)
        path_item.setPen(QPen(QColor(color), 2.0))
        path_item.setZValue(20)
        self.addItem(path_item)
        self._auto_paths[key] = path_item

        # Fill under curve (subtle)
        fill_path = QPainterPath(path)
        fill_path.lineTo(total * STEP_PX, y + AUTO_LANE_H)
        fill_path.lineTo(points[0][0] * STEP_PX, y + AUTO_LANE_H)
        fill_path.closeSubpath()
        fill_item = QGraphicsPathItem(fill_path)
        fill_color = QColor(color)
        fill_color.setAlpha(25)
        fill_item.setBrush(QBrush(fill_color))
        fill_item.setPen(QPen(Qt.PenStyle.NoPen))
        fill_item.setZValue(15)
        self.addItem(fill_item)
        self._auto_fills[key] = fill_item

        # Handles
        for i, (step_x, val) in enumerate(points):
            px = step_x * STEP_PX
            py = y + AUTO_LANE_H * (1.0 - val)
            handle = AutoHandle(px, py, y, AUTO_LANE_H, color, self, key, i)
            self.addItem(handle)
            self._auto_handles[key].append(handle)

    def _on_handle_moved(self, key):
        """Called when an automation handle is dragged."""
        try:
            y = self._vol_y if key == "vol" else self._pan_y
            handles = self._auto_handles.get(key, [])
            new_data = []
            for h in handles:
                step_x = max(0, h.pos().x() / STEP_PX)
                val = 1.0 - (h.pos().y() - y) / AUTO_LANE_H
                val = max(0.0, min(1.0, val))
                new_data.append((step_x, val))
            self._auto_data[key] = sorted(new_data, key=lambda p: p[0])
            self._rebuild_auto(key)
        except (RuntimeError, AttributeError):
            pass  # scene may be rebuilding

    def _remove_auto_point(self, key, idx):
        if 0 <= idx < len(self._auto_data[key]):
            self._auto_data[key].pop(idx)
            self._build()

    def _get_color(self, pat_id):
        if pat_id not in self._color_map:
            self._color_map[pat_id] = self._next_color
            self._next_color += 1
        return self._color_map[pat_id]

    # ── Order management ────────────────────────────────────────
    def set_order(self, order_list, pattern_lengths, pattern_names):
        self._order = list(order_list)
        self._pattern_lengths = dict(pattern_lengths)
        self._pattern_names = dict(pattern_names)
        self._build()
        self.order_changed.emit()

    def get_order(self):
        return list(self._order)

    def insert_after(self, idx, pat_id):
        self._order.insert(idx + 1, pat_id)
        self._build()
        self.order_changed.emit()

    def insert_before(self, idx, pat_id):
        self._order.insert(idx, pat_id)
        self._build()
        self.order_changed.emit()

    def remove_block(self, idx):
        if 0 <= idx < len(self._order):
            self._order.pop(idx)
            self._build()
            self.order_changed.emit()

    def move_block(self, idx, direction):
        new_idx = idx + direction
        if 0 <= new_idx < len(self._order):
            self._order[idx], self._order[new_idx] = self._order[new_idx], self._order[idx]
            self._build()
            self.order_changed.emit()

    def append_pattern(self, pat_id):
        self._order.append(pat_id)
        self._build()
        self.order_changed.emit()

    def show_insert_menu(self, before_idx, pos):
        """Shows a menu of available patterns to insert."""
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu{background:#1e1e3a;color:#ccc;border:1px solid #3a3a5a;"
            "font-family:'Courier New';}"
            "QMenu::item:selected{background:#0066cc;color:white;}")
        for pid in sorted(self._pattern_lengths.keys()):
            name = self._pattern_names.get(pid, pid)
            a = menu.addAction(f"{name}  ({self._pattern_lengths[pid]} steps)")
            a.triggered.connect(lambda checked, p=pid: self.insert_before(before_idx, p))
        menu.exec(pos)

    def _preview_pattern(self, pat_id):
        if self._tracker:
            self._tracker.switch_pattern(pat_id)
            self._tracker.play_current_pattern()

    def clear_order(self):
        self._order.clear()
        self._build()
        self.order_changed.emit()

    def get_auto_data(self):
        return dict(self._auto_data)

    # ── Double-click on automation lane to add point ─────────────
    def mouseDoubleClickEvent(self, event):
        pos = event.scenePos()
        # Check if click is in vol or pan lane
        for key, y in [("vol", self._vol_y), ("pan", self._pan_y)]:
            if y <= pos.y() <= y + AUTO_LANE_H:
                step_x = max(0, pos.x() / STEP_PX)
                val = 1.0 - (pos.y() - y) / AUTO_LANE_H
                val = max(0.0, min(1.0, val))
                self._auto_data[key].append((step_x, val))
                self._auto_data[key].sort(key=lambda p: p[0])
                self._build()
                return
        super().mouseDoubleClickEvent(event)

    # ── Drop from Pattern Bank ──────────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        if not e.mimeData().hasText():
            return
        parts = e.mimeData().text().split("|")
        if len(parts) < 3:
            return
        pat_id = parts[0]
        self.append_pattern(pat_id)
        e.acceptProposedAction()


# ═══════════════════════════════════════════════════════════════════
#   SEQUENCER VIEW
# ═══════════════════════════════════════════════════════════════════
class SequencerView(QGraphicsView):

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)
        self.setStyleSheet("border:none;background:#101028;")
        self._zoom = 1.0

    def fit_all(self):
        """Zoom to fit entire scene in the viewport."""
        sr = self.scene().sceneRect()
        if sr.width() < 1:
            return
        self.fitInView(sr, Qt.AspectRatioMode.KeepAspectRatio)
        # Compute the effective zoom
        t = self.transform()
        self._zoom = t.m11()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.2 if e.angleDelta().y() > 0 else 1 / 1.2
            nz = self._zoom * factor
            if MIN_ZOOM <= nz <= MAX_ZOOM:
                self._zoom = nz
                self.scale(factor, factor)
        else:
            delta = e.angleDelta().y()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta)
        e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            fake = type(e)(e.type(), e.position(), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton, e.modifiers())
            super().mousePressEvent(fake)
            return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        super().mouseReleaseEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.fit_all)


# ═══════════════════════════════════════════════════════════════════
#   PATTERN BANK
# ═══════════════════════════════════════════════════════════════════
class PatternBankWidget(QWidget):
    preview_requested = pyqtSignal(str)
    append_requested = pyqtSignal(str)  # for single-click append

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        title = QLabel("📦  Patterns")
        title.setStyleSheet(
            "color:#00ddff;font-weight:bold;font-size:13px;padding:4px;"
            "font-family:'Courier New';")
        layout.addWidget(title)

        hint = QLabel("Click → append\nDbl-click → preview\nDrag → drop on timeline")
        hint.setStyleSheet("color:#4a4a6a;font-size:8px;padding:0 4px 4px;"
                           "font-family:'Courier New';")
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background:#161638;color:#d4d4d4;border:1px solid #2a2a4a;
                font-family:'Courier New';font-size:11px;border-radius:6px;
            }
            QListWidget::item {
                padding:8px 10px;border-bottom:1px solid #1e1e40;
                margin:1px 2px;border-radius:3px;
            }
            QListWidget::item:selected{background:#0055aa;color:white;}
            QListWidget::item:hover{background:#22224a;}
        """)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.list_widget.clicked.connect(self._on_click)
        self.list_widget.doubleClicked.connect(self._on_dbl_click)
        layout.addWidget(self.list_widget)

        self.setFixedWidth(200)
        self.setStyleSheet("background:#141438;")

    def _on_click(self, index):
        item = self.list_widget.item(index.row())
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                self.append_requested.emit(data.split("|")[0])

    def _on_dbl_click(self, index):
        item = self.list_widget.item(index.row())
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                self.preview_requested.emit(data.split("|")[0])

    def refresh(self, pattern_lengths, pattern_names):
        self.list_widget.clear()
        for i, pid in enumerate(sorted(pattern_lengths.keys())):
            name = pattern_names.get(pid, pid)
            length = pattern_lengths[pid]
            item = QListWidgetItem(f" {name}  ·  {length} steps")
            item.setData(Qt.ItemDataRole.UserRole, f"{pid}|{length}|{name}")
            item.setForeground(QBrush(QColor(COLORS[i % len(COLORS)])))
            item.setToolTip(f"Pattern {pid} '{name}' — {length} steps")
            self.list_widget.addItem(item)

    def startDrag(self, sa):
        item = self.list_widget.currentItem()
        if not item:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(item.data(Qt.ItemDataRole.UserRole))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


# ═══════════════════════════════════════════════════════════════════
#   MAIN SEQUENCER WIDGET
# ═══════════════════════════════════════════════════════════════════
class SequencerWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──
        tb = QFrame()
        tb.setStyleSheet("QFrame{background:#181840;border-bottom:2px solid #2a2a50;}")
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(10, 5, 10, 5)
        tl.setSpacing(6)

        # Play / Stop
        self.btn_play = self._btn("▶  Play", "#1a6b1a", "#bbffbb", "#2a8a2a")
        self.btn_play.clicked.connect(self.play_arrangement)
        tl.addWidget(self.btn_play)

        self.btn_stop = self._btn("⏹  Stop", "#5a1a1a", "#ffaaaa", "#7a2a2a")
        self.btn_stop.clicked.connect(self.stop_playback)
        tl.addWidget(self.btn_stop)

        self._sep(tl)

        # Sync / Apply
        b = self._btn("🔄  Sync", "#2a4a2a", "#aaffaa", "#3a6a3a")
        b.setToolTip("Rebuild from tracker")
        b.clicked.connect(self.sync_from_tracker)
        tl.addWidget(b)

        b = self._btn("✅  Apply", "#2a3a5a", "#aaddff", "#3a5a8a")
        b.setToolTip("Push to tracker order list")
        b.clicked.connect(self.apply_to_tracker)
        tl.addWidget(b)

        self._sep(tl)

        b = self._btn("🗑  Clear", "#3a1a1a", "#ff8888", "#522")
        b.clicked.connect(self.clear_timeline)
        tl.addWidget(b)

        tl.addStretch()

        # Fit / Zoom
        b = self._btn("⊞  Fit", "#2a2a4a", "#aaa", "#3a3a5a")
        b.clicked.connect(lambda: self.view.fit_all())
        tl.addWidget(b)

        lbl = QLabel("🔍")
        lbl.setStyleSheet("color:#666;font-size:13px;")
        tl.addWidget(lbl)

        for sym, f in [("−", 1/1.3), ("+", 1.3)]:
            b = QPushButton(sym)
            b.setFixedSize(26, 26)
            b.setStyleSheet(
                "QPushButton{background:#2a2a4a;color:white;font-weight:bold;"
                "border-radius:4px;border:1px solid #3a3a5a;}"
                "QPushButton:hover{background:#3a3a5a;}")
            b.clicked.connect(lambda _, fac=f: self._do_zoom(fac))
            tl.addWidget(b)

        layout.addWidget(tb)

        # ── Content ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            "QSplitter::handle{background:#2a2a4a;width:3px;}"
            "QSplitter{background:#101028;}")

        self.bank = PatternBankWidget()
        self.bank.preview_requested.connect(self._preview)
        self.bank.append_requested.connect(self._append)
        self.bank.list_widget.startDrag = self.bank.startDrag
        splitter.addWidget(self.bank)

        self.scene = SequencerScene()
        self.view = SequencerView(self.scene)
        splitter.addWidget(self.view)

        splitter.setSizes([200, 800])
        layout.addWidget(splitter, stretch=1)

        # ── Status ──
        sf = QFrame()
        sf.setStyleSheet("QFrame{background:#181840;border-top:2px solid #2a2a50;}")
        sl = QHBoxLayout(sf)
        sl.setContentsMargins(12, 3, 12, 3)

        self.status = QLabel("  Click a pattern to append  ·  Ctrl+Scroll to zoom  ·  "
                             "Double-click automation lanes to add points")
        self.status.setStyleSheet(
            "color:#4a4a6a;font-style:italic;font-size:10px;font-family:'Courier New';")
        sl.addWidget(self.status)

        self.play_lbl = QLabel("")
        self.play_lbl.setStyleSheet(
            "color:#aaffaa;font-size:10px;font-weight:bold;font-family:'Courier New';")
        sl.addWidget(self.play_lbl)
        sl.addStretch()

        layout.addWidget(sf)

        self.scene.order_changed.connect(self._refresh_status)
        QTimer.singleShot(100, self.view.fit_all)

    # ── Helpers ─────────────────────────────────────────────────
    @staticmethod
    def _btn(text, bg, fg, border):
        b = QPushButton(text)
        b.setStyleSheet(
            f"{BTN}QPushButton{{background:{bg};color:{fg};border:1px solid {border};}}"
            f"QPushButton:hover{{background:{QColor(bg).lighter(130).name()}}}")
        return b

    @staticmethod
    def _sep(layout):
        s = QFrame()
        s.setFrameShape(QFrame.Shape.VLine)
        s.setStyleSheet("color:#2a2a4a;")
        layout.addWidget(s)

    def set_tracker(self, tracker_widget):
        self._tracker = tracker_widget
        self.scene._tracker = tracker_widget

    # ── Playback ────────────────────────────────────────────────
    def play_arrangement(self):
        if not self._tracker:
            return
        order = self.scene.get_order()
        if not order:
            self._set_status("⚠ Timeline is empty", "#ffaa44")
            return
        self._tracker.order_list = order
        self._tracker.refresh_order_display()
        self._tracker.play_sequence()

        self.btn_play.setText("⏸  Pause")
        try:
            self.btn_play.clicked.disconnect()
        except Exception:
            pass
        self.btn_play.clicked.connect(self._toggle_pause)
        self.play_lbl.setText(f"▶ Playing {len(order)} patterns")

    def _toggle_pause(self):
        if not self._tracker:
            return
        self._tracker.toggle_play_pause()
        playing = getattr(self._tracker, '_is_playing', False)
        self.btn_play.setText("⏸  Pause" if playing else "▶  Resume")
        self.play_lbl.setText("▶ Playing..." if playing else "⏸ Paused")

    def stop_playback(self):
        if self._tracker:
            self._tracker.stop_sequence()
        self.btn_play.setText("▶  Play")
        try:
            self.btn_play.clicked.disconnect()
        except Exception:
            pass
        self.btn_play.clicked.connect(self.play_arrangement)
        self.play_lbl.setText("")

    def _preview(self, pat_id):
        if self._tracker:
            self._tracker.switch_pattern(pat_id)
            self._tracker.play_current_pattern()
            name = self._tracker.pattern_names.get(pat_id, pat_id)
            self.play_lbl.setText(f"▶ Preview: {name}")

    def _append(self, pat_id):
        self.scene.append_pattern(pat_id)
        QTimer.singleShot(50, self.view.fit_all)

    # ── Sync / Apply ────────────────────────────────────────────
    def sync_from_tracker(self):
        if not self._tracker:
            return
        self.bank.refresh(self._tracker.pattern_lengths, self._tracker.pattern_names)
        self.scene.set_order(
            self._tracker.order_list,
            self._tracker.pattern_lengths,
            self._tracker.pattern_names)
        self._set_status("🔄 Synced", "#aaffaa")
        QTimer.singleShot(50, self.view.fit_all)

    def apply_to_tracker(self):
        if not self._tracker:
            return
        order = self.scene.get_order()
        if not order:
            self._set_status("⚠ Nothing to apply", "#ffaa44")
            return
        self._tracker.order_list = order
        self._tracker.refresh_order_display()
        self._set_status(f"✅ Applied {len(order)} patterns", "#aaffaa")

    def clear_timeline(self):
        self.scene.clear_order()
        self._refresh_status()

    def _do_zoom(self, factor):
        nz = self.view._zoom * factor
        if MIN_ZOOM <= nz <= MAX_ZOOM:
            self.view._zoom = nz
            self.view.scale(factor, factor)

    def _set_status(self, text, color="#4a4a6a"):
        self.status.setText(f"  {text}")
        self.status.setStyleSheet(
            f"color:{color};font-style:italic;font-size:10px;font-family:'Courier New';")

    def _refresh_status(self):
        n = len(self.scene._order)
        total = self.scene._total_steps()
        self._set_status(f"{n} patterns  ·  {total} steps total")
