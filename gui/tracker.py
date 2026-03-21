from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QDialog, QLineEdit, QInputDialog, QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QBrush, QPen, QKeySequence, QShortcut, QUndoStack, QUndoCommand
import pyqtgraph as pg
import time
import threading
from .context_menu import TrackerContextMenu

class TrackerTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def keyPressEvent(self, event):
        parent = self.parentWidget()

        # Spacebar: play/pause toggle (Shift+Space = play from cursor)
        if event.key() == Qt.Key.Key_Space:
            if parent and hasattr(parent, 'play_current_pattern'):
                from PyQt6.QtCore import Qt as QtCore_Qt
                if event.modifiers() & QtCore_Qt.KeyboardModifier.ShiftModifier:
                    # Play from selected row
                    sel = self.selectedIndexes()
                    start_row = sel[0].row() if sel else 0
                    parent.play_from_row(start_row)
                else:
                    # Toggle play/pause
                    parent.toggle_play_pause()
            return

        # Delete / Backspace clears selected cells to defaults
        if event.key() in [Qt.Key.Key_Backspace, Qt.Key.Key_Delete]:
            if parent and hasattr(parent, 'sub_cols'):
                for item in self.selectedItems():
                    rem = item.column() % parent.sub_cols
                    item.setText("---" if rem in [0, 1] else "--")
                    item.setForeground(QBrush(QColor("#d4d4d4")))
            return

        # Enter on FX columns opens the interpolation sweep dialog
        if event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            col = self.currentColumn()
            if parent and hasattr(parent, 'sub_cols') and col % parent.sub_cols in [4, 5]:
                selected = self.selectedItems()
                # Filter to only FX column items
                fx_items = [it for it in selected if it.column() % parent.sub_cols in [4, 5]]
                fx_items.sort(key=lambda it: it.row())
                if len(fx_items) < 2:
                    return

                # Try to detect FX command prefix from first cell
                first_text = fx_items[0].text().strip()
                default_cmd = ""
                default_start = "00"
                default_end = "FF"
                if first_text and first_text != "--":
                    parts = first_text.split()
                    if len(parts) >= 1:
                        default_cmd = parts[0]
                    if len(parts) >= 2:
                        default_start = parts[1]

                dlg = QDialog(self)
                dlg.setWindowTitle("FX Interpolation Sweep")
                dlg.setStyleSheet("background-color: #252526; color: #cccccc;")
                vbox = QVBoxLayout(dlg)
                vbox.addWidget(QLabel(f"Sweep {len(fx_items)} selected FX cells:"))
                hbox1 = QHBoxLayout()
                hbox1.addWidget(QLabel("FX Command:"))
                cmd_edit = QLineEdit(default_cmd)
                cmd_edit.setPlaceholderText("e.g. PAN, VOL, VIB")
                hbox1.addWidget(cmd_edit)
                vbox.addLayout(hbox1)
                hbox2 = QHBoxLayout()
                hbox2.addWidget(QLabel("Start:"))
                start_edit = QLineEdit(default_start)
                hbox2.addWidget(start_edit)
                hbox2.addWidget(QLabel("End:"))
                end_edit = QLineEdit(default_end)
                hbox2.addWidget(end_edit)
                vbox.addLayout(hbox2)
                btn = QPushButton("Apply Sweep")
                btn.clicked.connect(dlg.accept)
                vbox.addWidget(btn)

                if dlg.exec():
                    try:
                        cmd_prefix = cmd_edit.text().strip().upper()
                        start_val = int(start_edit.text().strip())
                        end_val = int(end_edit.text().strip())
                    except ValueError:
                        return
                    count = len(fx_items)
                    for i, item in enumerate(fx_items):
                        ratio = i / max(1, count - 1)
                        val = int(start_val + (end_val - start_val) * ratio)
                        val = max(0, min(255, val))
                        val_str = str(val)
                        if cmd_prefix:
                            item.setText(f"{cmd_prefix} {val_str}")
                        else:
                            item.setText(val_str)
                        item.setForeground(QBrush(QColor("#55aaff")))
            return

        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        """Show column-aware right-click context menu."""
        parent = self.parentWidget()
        if parent and hasattr(parent, 'sub_cols'):
            TrackerContextMenu.show(self, event.globalPos(), parent)
        else:
            super().contextMenuEvent(event)

class TheoryEngineWidget(QWidget):
    NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    INTERVALS = {
        "Chromatic": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "Major": [0, 2, 4, 5, 7, 9, 11],
        "Minor": [0, 2, 3, 5, 7, 8, 10],
        "Dorian": [0, 2, 3, 5, 7, 9, 10],
        "Phrygian": [0, 1, 3, 5, 7, 8, 10],
        "Lydian": [0, 2, 4, 6, 7, 9, 11],
        "Mixolydian": [0, 2, 4, 5, 7, 9, 10],
        "Locrian": [0, 1, 3, 5, 6, 8, 10],
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from PyQt6.QtWidgets import QComboBox

        lbl = QLabel("🎵 Scale:")
        lbl.setStyleSheet("color: #00FFFF; font-family: 'Courier New', monospace; font-weight: bold;")
        layout.addWidget(lbl)

        self.combo_root = QComboBox()
        self.combo_root.addItems(self.NOTE_NAMES)
        self.combo_root.setStyleSheet("background-color: #333333; color: white;")
        self.combo_root.currentIndexChanged.connect(self.update_keyboard)
        layout.addWidget(self.combo_root)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(list(self.INTERVALS.keys()))
        self.combo_mode.setStyleSheet("background-color: #333333; color: white;")
        self.combo_mode.currentIndexChanged.connect(self.update_keyboard)
        layout.addWidget(self.combo_mode)

        # Note name buttons — 12 chromatic buttons showing actual note names
        self.note_layout = QHBoxLayout()
        self.note_btns = []
        for i in range(12):
            btn = QPushButton(self.NOTE_NAMES[i])
            btn.setFixedWidth(30)
            btn.setFixedHeight(24)
            self.note_btns.append(btn)
            self.note_layout.addWidget(btn)

        layout.addLayout(self.note_layout)

        # Valid notes label — shows the current scale degree names
        self.valid_label = QLabel("")
        self.valid_label.setStyleSheet("color: #aaffaa; font-family: 'Courier New', monospace; font-size: 10px;")
        layout.addWidget(self.valid_label)
        layout.addStretch()

        self.update_keyboard()

    def update_keyboard(self):
        """Updates the note buttons to reflect the current root+mode."""
        root_idx = self.combo_root.currentIndex()
        mode_str = self.combo_mode.currentText()

        active_steps = self.INTERVALS.get(mode_str, self.INTERVALS["Chromatic"])
        valid_indices = set((root_idx + step) % 12 for step in active_steps)

        valid_names = []
        for i in range(12):
            btn = self.note_btns[i]
            name = self.NOTE_NAMES[i]
            btn.setText(name)
            if i in valid_indices:
                btn.setStyleSheet(
                    "background-color: #bbbbbb; color: black; font-weight: bold; font-size: 10px;"
                )
                valid_names.append(name)
            else:
                btn.setStyleSheet(
                    "background-color: #111111; color: #444444; font-size: 10px;"
                )

        self.valid_label.setText("  " + " ".join(valid_names))

class TrackerEditCommand(QUndoCommand):
    """Undoable edit for a single tracker cell."""
    def __init__(self, table, row, col, old_text, new_text, old_color=None, new_color=None):
        super().__init__(f"Edit ({row},{col})")
        self.table = table
        self.row = row
        self.col = col
        self.old_text = old_text
        self.new_text = new_text
        self.old_color = old_color or QColor("#d4d4d4")
        self.new_color = new_color or QColor("#d4d4d4")

    def undo(self):
        item = self.table.item(self.row, self.col)
        if item:
            self.table.blockSignals(True)
            item.setText(self.old_text)
            item.setForeground(QBrush(self.old_color))
            self.table.blockSignals(False)

    def redo(self):
        item = self.table.item(self.row, self.col)
        if item:
            self.table.blockSignals(True)
            item.setText(self.new_text)
            item.setForeground(QBrush(self.new_color))
            self.table.blockSignals(False)

class TrackerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Tracker Configuration Constraints
        self.min_tracks = 1
        self.max_tracks = 8
        self.current_tracks = 8
        self.total_steps = 64  # Current pattern's length
        
        # Default velocity / gate for manual entry
        self.last_step_vel = "FF"
        self.last_step_gate = "04"
        
        # --- V1.1 Pattern Architecture ---
        self.patterns = {}       # {"A": [[cell_texts], ...], "B": [...], ...}
        self.pattern_lengths = {"A": 64}  # Per-pattern step count
        self.pattern_meta = {}   # {"A": {"bpm": 140, "lpb": 4, "lpm": 12}, ...}
        self.order_list = ["A"]  # Song arrangement
        self.active_pattern = "A"  # Currently displayed pattern
        
        # Undo/Redo Stack
        self.undo_stack = QUndoStack(self)
        self._undo_block = False  # Guard against recursive itemChanged
        
        self.init_ui()

    def init_ui(self):
        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # --- 1. VISUAL THEORY ENGINE ---
        self.theory_engine = TheoryEngineWidget()
        layout.addWidget(self.theory_engine)

        # --- 2. PATTERN TOOLBAR ---
        from PyQt6.QtWidgets import QComboBox, QSpinBox
        pattern_bar = QHBoxLayout()

        pattern_bar.addWidget(QLabel("Pattern:"))
        self.pattern_combo = QComboBox()
        self.pattern_combo.addItem("A")
        self.pattern_combo.setFixedWidth(60)
        self.pattern_combo.currentTextChanged.connect(self.switch_pattern)
        pattern_bar.addWidget(self.pattern_combo)

        btn_new_pat = QPushButton("+ New")
        btn_new_pat.setFixedWidth(55)
        btn_new_pat.setToolTip("Create a new empty pattern")
        btn_new_pat.clicked.connect(self.new_pattern)
        pattern_bar.addWidget(btn_new_pat)

        btn_clone = QPushButton("⧉ Clone")
        btn_clone.setFixedWidth(60)
        btn_clone.setToolTip("Clone the current pattern")
        btn_clone.clicked.connect(self.clone_pattern)
        pattern_bar.addWidget(btn_clone)

        btn_del_pat = QPushButton("✕ Del")
        btn_del_pat.setFixedWidth(50)
        btn_del_pat.setToolTip("Delete the current pattern")
        btn_del_pat.clicked.connect(self.delete_pattern)
        pattern_bar.addWidget(btn_del_pat)

        pattern_bar.addWidget(QLabel("  Steps:"))
        self.spin_pat_len = QSpinBox()
        self.spin_pat_len.setRange(1, 256)
        self.spin_pat_len.setValue(64)
        self.spin_pat_len.setFixedWidth(55)
        self.spin_pat_len.setToolTip("Set step count for this pattern (type a number or use arrows)")
        self.spin_pat_len.valueChanged.connect(self.resize_pattern)
        pattern_bar.addWidget(self.spin_pat_len)

        pattern_bar.addStretch()

        # Order list display (compact horizontal list widget)
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        pattern_bar.addWidget(QLabel("Order:"))
        self.order_list_widget = QListWidget()
        self.order_list_widget.setFlow(QListWidget.Flow.LeftToRight)
        self.order_list_widget.setFixedHeight(28)
        self.order_list_widget.setMaximumWidth(320)
        self.order_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.order_list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.order_list_widget.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
            "QListWidget::item { color: #00FFFF; font-family: 'Courier New', monospace;"
            " font-weight: bold; padding: 1px 3px; margin: 0 1px; }"
            "QListWidget::item:selected { background: #007acc; color: white; }")
        self.order_list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        pattern_bar.addWidget(self.order_list_widget)

        btn_order_add = QPushButton("+ Seq")
        btn_order_add.setFixedWidth(50)
        btn_order_add.setToolTip("Append current pattern to order list")
        btn_order_add.clicked.connect(self.order_append)
        pattern_bar.addWidget(btn_order_add)

        btn_order_rm = QPushButton("- Seq")
        btn_order_rm.setFixedWidth(50)
        btn_order_rm.setToolTip("Remove last entry from order list")
        btn_order_rm.clicked.connect(self.order_remove_last)
        pattern_bar.addWidget(btn_order_rm)

        btn_seq_view = QPushButton("SeqEdit")
        btn_seq_view.setFixedWidth(60)
        btn_seq_view.setToolTip("Open the Sequence Editor to reorder, add, or remove patterns")
        btn_seq_view.clicked.connect(self.show_sequence_view)
        pattern_bar.addWidget(btn_seq_view)

        layout.addLayout(pattern_bar)

        # --- 3. TRACKER TOOLBAR ---
        toolbar_layout = QHBoxLayout()

        track_control_label = QLabel("Tracks:")

        self.btn_minus = QPushButton("-")
        self.btn_minus.setFixedWidth(30)
        self.btn_minus.clicked.connect(self.remove_track)

        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedWidth(30)
        self.btn_plus.clicked.connect(self.add_track)

        # Play Pattern / Solo Track buttons
        btn_play_pat = QPushButton("▶ Pat")
        btn_play_pat.setFixedWidth(55)
        btn_play_pat.setToolTip("Play current pattern only (not full song)")
        btn_play_pat.clicked.connect(self.play_current_pattern)
        toolbar_layout.addWidget(btn_play_pat)

        btn_solo = QPushButton("▶ Solo")
        btn_solo.setFixedWidth(55)
        btn_solo.setToolTip("Solo play the selected track only")
        btn_solo.clicked.connect(self.play_solo_track)
        toolbar_layout.addWidget(btn_solo)

        toolbar_layout.addStretch()
        
        # Tracker Playback Visualizer (free-floating oscilloscope)
        self.playback_viz = pg.PlotWidget(title="")
        self.playback_viz.setFixedHeight(44)
        self.playback_viz.setFixedWidth(400)
        self.playback_viz.hideAxis('left')
        self.playback_viz.hideAxis('bottom')
        self.playback_viz.setBackground(None)  # Fully transparent
        self.playback_viz.setStyleSheet("background: transparent; border: none;")
        self.playback_viz.getPlotItem().getViewBox().setDefaultPadding(0)
        self.playback_viz.setAntialiasing(True)
        # Glow layer (wide, dim)
        self.viz_glow = self.playback_viz.plot(
            [0]*200, pen=pg.mkPen(pg.mkColor(0, 255, 200, 35), width=6))
        # Main waveform (bright cyan, thin)
        self.viz_curve = self.playback_viz.plot(
            [0]*200, pen=pg.mkPen(pg.mkColor(0, 255, 200, 220), width=1.5))
        toolbar_layout.addWidget(self.playback_viz)

        toolbar_layout.addStretch()

        toolbar_layout.addWidget(track_control_label)
        toolbar_layout.addWidget(self.btn_minus)
        toolbar_layout.addWidget(self.btn_plus)
        
        layout.addLayout(toolbar_layout)

        # --- 3. THE GRID (QTableWidget) ---
        self.sub_cols = 7 # Note, Inst, Vel, Gate, FX1, FX2, Spacer
        self.table = TrackerTableWidget(self.total_steps, self.current_tracks * self.sub_cols)
        
        # Style the table to look like a DAW tracker
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New', monospace;
                gridline-color: #333333;
                border: 1px solid #333333;
            }
            QHeaderView::section {
                background-color: #2d2d30;
                color: #cccccc;
                padding: 4px;
                border: 1px solid #3f3f46;
            }
        """)
        
        # Double Click fast-switching
        self.table.cellDoubleClicked.connect(self.handle_cell_double_click)
        
        # Stateful Tracking Bindings
        self.table.itemChanged.connect(self.on_item_changed)
        
        # Cell old-text cache for undo tracking
        self._old_cell_text = {}
        
        # Loop shortcut
        self.loop_shortcut = QShortcut(QKeySequence("Ctrl+L"), self.table)
        self.loop_shortcut.activated.connect(self.loop_selection)
        
        # Undo/Redo shortcuts
        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self.table)
        self.undo_shortcut.activated.connect(self.undo_stack.undo)
        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self.table)
        self.redo_shortcut.activated.connect(self.undo_stack.redo)
        
        self.setup_table_headers()
        self.populate_grid()
        
        # Keep rows compact
        self.table.verticalHeader().setDefaultSectionSize(22) 
        
        layout.addWidget(self.table)
        self.update_button_states()

    def on_item_changed(self, item):
        """Track cell changes for undo/redo and update state memory."""
        if self._undo_block:
            return
            
        col = item.column()
        row = item.row()
        rem = col % self.sub_cols
        txt = item.text()
        
        # Push undo command
        key = (row, col)
        old_text = self._old_cell_text.get(key, "---" if rem in [0, 1] else "--")
        if txt != old_text:
            old_color = QColor("#d4d4d4")
            new_color = item.foreground().color()
            cmd = TrackerEditCommand(self.table, row, col, old_text, txt, old_color, new_color)
            self._undo_block = True
            self.undo_stack.push(cmd)
            self._undo_block = False
        self._old_cell_text[key] = txt
        
        if not txt or txt in ["---", "--"]: 
            return
            
        if rem == 2:
            self.last_step_vel = txt
        elif rem == 3:
            self.last_step_gate = txt



    def setup_table_headers(self):
        """Generates the Row (Step) and Column (Track) labels."""
        headers = []
        for i in range(self.current_tracks):
            headers.extend(["Note", "Inst", "Vel", "Gat", "FX1", "FX2", "|  |"])
        self.table.setHorizontalHeaderLabels(headers)
        
        # Set Step Headers
        step_headers = [f"{i:02d}" for i in range(self.total_steps)]
        self.table.setVerticalHeaderLabels(step_headers)
        
        for col in range(self.current_tracks * self.sub_cols):
            rem = col % self.sub_cols
            if rem == 1:
                self.table.setColumnWidth(col, 100)  # Inst needs space for string names
            elif rem in [4, 5]:
                self.table.setColumnWidth(col, 65)   # FX columns need space for "PRT 08"
            elif rem == 6:
                self.table.setColumnWidth(col, 20)   # Spacer
            elif rem in [2, 3]:
                self.table.setColumnWidth(col, 38)   # Vel/Gat need room for values
            else:
                self.table.setColumnWidth(col, 40)    # Note column

    def populate_grid(self):
        """Fills the grid with blank data and applies rhythmic shading."""
        cols = self.current_tracks * self.sub_cols
        for row in range(self.total_steps):
            for col in range(cols):
                rem = col % self.sub_cols
                if rem == 6:
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)  # Unselectable spacer
                    item.setBackground(QBrush(QColor("#0f0f0f")))
                else:
                    text = "---" if rem in [0, 1] else "--"
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    # Colorize specific columns
                    if rem == 0:
                        item.setForeground(QBrush(QColor("#00ff00")))
                    elif rem == 1:
                        item.setForeground(QBrush(QColor("#ffaa00")))
                    elif rem in [4, 5]:
                        item.setForeground(QBrush(QColor("#55aaff")))
                        
                self.table.setItem(row, col, item)
        
        # Apply initial highlighting
        self.refresh_beat_highlighting()

    def refresh_beat_highlighting(self, lines_per_beat=None, lines_per_measure=None):
        """Re-shades row backgrounds based on time signature without clearing cell content."""
        if lines_per_beat is None:
            main_win = self.window()
            if hasattr(main_win, 'spin_lpb'):
                lines_per_beat = main_win.spin_lpb.value()
            else:
                lines_per_beat = 4
        
        if lines_per_measure is None:
            main_win = self.window()
            if hasattr(main_win, 'spin_lpm'):
                lines_per_measure = main_win.spin_lpm.value()
            else:
                lines_per_measure = 16
        
        cols = self.current_tracks * self.sub_cols
        for row in range(self.total_steps):
            is_measure = (row % lines_per_measure == 0)
            is_beat = (row % lines_per_beat == 0)
            
            if is_measure:
                bgcolor = QColor("#2a2a30")  # Brightest — measure boundary
            elif is_beat:
                bgcolor = QColor("#222222")  # Medium — beat boundary
            else:
                bgcolor = QColor("#1a1a1a")  # Default dark
            
            for col in range(cols):
                rem = col % self.sub_cols
                if rem == 6:
                    continue  # Skip spacer columns
                item = self.table.item(row, col)
                if item:
                    item.setBackground(QBrush(bgcolor))

    def recolor_all_cells(self):
        """Re-applies correct foreground colors, alignment, and spacer flags after a CSV load."""
        color_map = {
            0: QColor("#00ff00"),   # Note
            1: QColor("#ffaa00"),   # Inst
            2: QColor("#d4d4d4"),   # Vel
            3: QColor("#d4d4d4"),   # Gate
            4: QColor("#55aaff"),   # FX1
            5: QColor("#55aaff"),   # FX2
        }
        cols = self.current_tracks * self.sub_cols
        for row in range(self.total_steps):
            for col in range(cols):
                rem = col % self.sub_cols
                item = self.table.item(row, col)
                if rem == 6:
                    # Spacer column
                    if item is None:
                        item = QTableWidgetItem("")
                        self.table.setItem(row, col, item)
                    item.setText("")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    item.setBackground(QBrush(QColor("#0f0f0f")))
                else:
                    if item is None:
                        text = "---" if rem in [0, 1] else "--"
                        item = QTableWidgetItem(text)
                        self.table.setItem(row, col, item)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setForeground(QBrush(color_map.get(rem, QColor("#d4d4d4"))))
        self.refresh_beat_highlighting()

    def add_track(self):
        """Appends a new column to the grid."""
        if self.current_tracks < self.max_tracks:
            self.current_tracks += 1
            self.table.setColumnCount(self.current_tracks * self.sub_cols)
            self.setup_table_headers()
            self.populate_grid()
            self.update_button_states()

    def remove_track(self):
        """Removes the right-most column from the grid."""
        if self.current_tracks > self.min_tracks:
            self.current_tracks -= 1
            self.table.setColumnCount(self.current_tracks * self.sub_cols)
            self.setup_table_headers()
            self.update_button_states()

    def update_button_states(self):
        """Disables buttons if limits are reached to prevent errors."""
        self.btn_plus.setEnabled(self.current_tracks < self.max_tracks)
        self.btn_minus.setEnabled(self.current_tracks > self.min_tracks)

    def loop_selection(self):
        """Clones the selected block multiple times down the tracker."""
        ranges = self.table.selectedRanges()
        if not ranges:
            return
            
        sel = ranges[0]
        start_row = sel.topRow()
        end_row = sel.bottomRow()
        start_col = sel.leftColumn()
        end_col = sel.rightColumn()
        
        length = end_row - start_row + 1
        
        multiplier, ok = QInputDialog.getInt(self, "Loop Selection", "Multiply this block how many times?", 2, 2, 32)
        if ok:
            # Copy data block
            block_data = []
            for r in range(start_row, end_row + 1):
                row_data = []
                for c in range(start_col, end_col + 1):
                    item = self.table.item(r, c)
                    row_data.append(item.text() if item else "")
                block_data.append(row_data)
                
            # Paste it sequentially
            curr_row = end_row + 1
            for m in range(multiplier - 1):
                for br, r_data in enumerate(block_data):
                    target_row = curr_row + br
                    if target_row >= self.total_steps:
                        return # Reached end of pattern
                        
                    for c_idx, val in enumerate(r_data):
                        target_col = start_col + c_idx
                        item = self.table.item(target_row, target_col)
                        if item and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                            item.setText(val)
                curr_row += length
    # ================================================================
    #              PATTERN MANAGEMENT (V1.1)
    # ================================================================

    def save_grid_to_pattern(self):
        """Captures the current QTableWidget state into self.patterns[active_pattern]."""
        cols = self.current_tracks * self.sub_cols
        grid = []
        for row in range(self.total_steps):
            row_data = []
            for col in range(cols):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            grid.append(row_data)
        self.patterns[self.active_pattern] = grid
        self.pattern_lengths[self.active_pattern] = self.total_steps

    def load_pattern_to_grid(self, pattern_id):
        """Loads a pattern's data from self.patterns into the QTableWidget."""
        length = self.pattern_lengths.get(pattern_id, 64)
        self.total_steps = length
        self.table.setRowCount(length)
        self.table.setColumnCount(self.current_tracks * self.sub_cols)
        self.setup_table_headers()

        grid = self.patterns.get(pattern_id)
        if grid:
            cols = self.current_tracks * self.sub_cols
            for row_idx, row_data in enumerate(grid):
                if row_idx >= length:
                    break
                for col_idx, txt in enumerate(row_data):
                    if col_idx >= cols:
                        break
                    item = self.table.item(row_idx, col_idx)
                    if item is None:
                        item = QTableWidgetItem(txt)
                        self.table.setItem(row_idx, col_idx, item)
                    else:
                        item.setText(txt)
        else:
            self.populate_grid()

        self.recolor_all_cells()
        self.spin_pat_len.blockSignals(True)
        self.spin_pat_len.setValue(length)
        self.spin_pat_len.blockSignals(False)

    def _get_pattern_timing(self, pattern_id):
        """Returns (bpm, lpb, lpm, key, mode) for a pattern, falling back to globals."""
        main_win = self.window()
        meta = self.pattern_meta.get(pattern_id, {})
        bpm = meta.get("bpm", main_win.spin_bpm.value() if main_win else 120)
        lpb = meta.get("lpb", main_win.spin_lpb.value() if main_win else 4)
        lpm = meta.get("lpm", main_win.spin_lpm.value() if main_win else 16)
        key = meta.get("key", self.theory_engine.combo_root.currentText() if hasattr(self, 'theory_engine') else "C")
        mode = meta.get("mode", self.theory_engine.combo_mode.currentText() if hasattr(self, 'theory_engine') else "Chromatic")
        return bpm, lpb, lpm, key, mode

    def _save_pattern_timing(self):
        """Saves current toolbar BPM/LPB/LPM and key/mode for the active pattern."""
        main_win = self.window()
        if not main_win:
            return
        self.pattern_meta[self.active_pattern] = {
            "bpm": main_win.spin_bpm.value(),
            "lpb": main_win.spin_lpb.value(),
            "lpm": main_win.spin_lpm.value(),
            "key": self.theory_engine.combo_root.currentText(),
            "mode": self.theory_engine.combo_mode.currentText(),
        }

    def _apply_pattern_timing(self, pattern_id):
        """Updates toolbar spinners and theory engine to reflect a pattern's settings."""
        main_win = self.window()
        if not main_win:
            return
        bpm, lpb, lpm, key, mode = self._get_pattern_timing(pattern_id)
        main_win.spin_bpm.blockSignals(True)
        main_win.spin_lpb.blockSignals(True)
        main_win.spin_lpm.blockSignals(True)
        main_win.spin_bpm.setValue(bpm)
        main_win.spin_lpb.setValue(lpb)
        main_win.spin_lpm.setValue(lpm)
        main_win.spin_bpm.blockSignals(False)
        main_win.spin_lpb.blockSignals(False)
        main_win.spin_lpm.blockSignals(False)
        # Update theory engine key/mode
        self.theory_engine.combo_root.blockSignals(True)
        self.theory_engine.combo_mode.blockSignals(True)
        self.theory_engine.combo_root.setCurrentText(key)
        self.theory_engine.combo_mode.setCurrentText(mode)
        self.theory_engine.combo_root.blockSignals(False)
        self.theory_engine.combo_mode.blockSignals(False)
        self.theory_engine.update_keyboard()

    def switch_pattern(self, pattern_id):
        """Saves current grid + timing, then loads the requested pattern."""
        if not pattern_id or pattern_id == self.active_pattern:
            return
        if pattern_id not in self.pattern_lengths:
            return
        self._save_pattern_timing()
        self.save_grid_to_pattern()
        self.active_pattern = pattern_id
        self.load_pattern_to_grid(pattern_id)
        self._apply_pattern_timing(pattern_id)
        self.refresh_beat_highlighting()
        # Update combo without re-triggering
        self.pattern_combo.blockSignals(True)
        self.pattern_combo.setCurrentText(pattern_id)
        self.pattern_combo.blockSignals(False)

    def _next_pattern_id(self):
        """Returns the next available pattern ID (A-Z, then AA-AZ, BA-BZ, etc.)."""
        import string
        # Single letters first
        for ch in string.ascii_uppercase:
            if ch not in self.pattern_lengths:
                return ch
        # Double letters: AA, AB, ... AZ, BA, BB, ... ZZ
        for c1 in string.ascii_uppercase:
            for c2 in string.ascii_uppercase:
                pid = c1 + c2
                if pid not in self.pattern_lengths:
                    return pid
        return "??"

    def new_pattern(self):
        """Creates a new empty pattern with the next available ID."""
        pid = self._next_pattern_id()
        self.save_grid_to_pattern()
        self.pattern_lengths[pid] = 64
        self.patterns[pid] = None  # Will be populated by populate_grid
        self.active_pattern = pid
        # Update combo
        self.pattern_combo.blockSignals(True)
        self.pattern_combo.addItem(pid)
        self.pattern_combo.setCurrentText(pid)
        self.pattern_combo.blockSignals(False)
        # Load empty grid
        self.total_steps = 64
        self.table.setRowCount(64)
        self.table.setColumnCount(self.current_tracks * self.sub_cols)
        self.setup_table_headers()
        self.populate_grid()
        self.spin_pat_len.blockSignals(True)
        self.spin_pat_len.setValue(64)
        self.spin_pat_len.blockSignals(False)

    def clone_pattern(self):
        """Clones the current pattern into a new ID."""
        pid = self._next_pattern_id()
        self.save_grid_to_pattern()
        import copy
        self.patterns[pid] = copy.deepcopy(self.patterns.get(self.active_pattern))
        self.pattern_lengths[pid] = self.pattern_lengths[self.active_pattern]
        if self.active_pattern in self.pattern_meta:
            self.pattern_meta[pid] = dict(self.pattern_meta[self.active_pattern])
        # Add to combo and switch
        self.pattern_combo.blockSignals(True)
        self.pattern_combo.addItem(pid)
        self.pattern_combo.blockSignals(False)
        self.switch_pattern(pid)

    def delete_pattern(self):
        """Deletes the current pattern (must have at least one)."""
        if len(self.pattern_lengths) <= 1:
            QMessageBox.warning(self, "Cannot Delete", "You must have at least one pattern.")
            return
        pid = self.active_pattern
        reply = QMessageBox.question(self, "Delete Pattern",
            f"Delete pattern '{pid}'? This also removes it from the order list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        # Remove from data
        self.patterns.pop(pid, None)
        self.pattern_lengths.pop(pid, None)
        self.pattern_meta.pop(pid, None)
        self.order_list = [x for x in self.order_list if x != pid]
        if not self.order_list:
            first = sorted(self.pattern_lengths.keys())[0]
            self.order_list = [first]
        # Remove from combo
        idx = self.pattern_combo.findText(pid)
        self.pattern_combo.blockSignals(True)
        self.pattern_combo.removeItem(idx)
        self.pattern_combo.blockSignals(False)
        # Switch to first available
        new_active = sorted(self.pattern_lengths.keys())[0]
        self.active_pattern = new_active
        self.pattern_combo.blockSignals(True)
        self.pattern_combo.setCurrentText(new_active)
        self.pattern_combo.blockSignals(False)
        self.load_pattern_to_grid(new_active)
        self.refresh_order_display()

    def resize_pattern(self, new_len):
        """Changes the step count of the current pattern."""
        self.save_grid_to_pattern()
        old_len = self.pattern_lengths[self.active_pattern]
        self.pattern_lengths[self.active_pattern] = new_len
        self.total_steps = new_len
        self.table.setRowCount(new_len)
        # If growing, add blank rows
        if new_len > old_len:
            cols = self.current_tracks * self.sub_cols
            for row in range(old_len, new_len):
                for col in range(cols):
                    rem = col % self.sub_cols
                    if rem == 6:
                        item = QTableWidgetItem("")
                        item.setFlags(Qt.ItemFlag.NoItemFlags)
                        item.setBackground(QBrush(QColor("#0f0f0f")))
                    else:
                        text = "---" if rem in [0, 1] else "--"
                        item = QTableWidgetItem(text)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(row, col, item)
        self.setup_table_headers()
        self.recolor_all_cells()
        self.save_grid_to_pattern()

    def order_append(self):
        """Appends the current pattern to the order list."""
        self.order_list.append(self.active_pattern)
        self.refresh_order_display()

    def order_remove_last(self):
        """Removes the last entry from the order list."""
        if len(self.order_list) > 1:
            self.order_list.pop()
            self.refresh_order_display()

    def show_sequence_view(self):
        """Opens a sequence editor dialog for reordering patterns."""
        from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                      QListWidget, QListWidgetItem,
                                      QPushButton, QComboBox, QLabel)
        self.save_grid_to_pattern()
        tracker = self  # capture for closures

        # If window already open, just raise it
        if hasattr(self, '_seq_editor_win') and self._seq_editor_win is not None:
            self._seq_editor_win.raise_()
            self._seq_editor_win.activateWindow()
            return

        win = QWidget(None, Qt.WindowType.Window)
        win.setWindowTitle("Sequence Editor")
        win.resize(380, 420)
        win.setStyleSheet(
            "QWidget { background-color: #1e1e1e; color: #d4d4d4; }"
            "QListWidget { background-color: #1a1a1a; color: #00ffff;"
            " font-family: 'Courier New', monospace; font-size: 13px;"
            " border: 1px solid #333; }"
            "QListWidget::item { padding: 4px 8px; }"
            "QListWidget::item:selected { background: #007acc; color: white; }"
            "QPushButton { background-color: #333; color: white;"
            " border: 1px solid #555; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #444; }"
            "QComboBox { background-color: #333; color: white;"
            " border: 1px solid #555; padding: 2px 6px; }"
            "QLabel { color: #aaa; }"
        )

        layout = QVBoxLayout(win)
        layout.addWidget(QLabel("Drag to reorder • Double-click to jump to pattern"))

        # --- Drag-and-drop list ---
        seq_list = QListWidget()
        seq_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        seq_list.setDefaultDropAction(Qt.DropAction.MoveAction)

        def _label_for(pat_id):
            bpm, lpb, lpm, key, mode = tracker._get_pattern_timing(pat_id)
            beats = lpm // lpb if lpb > 0 else 4
            steps = tracker.pattern_lengths.get(pat_id, 64)
            return f"{pat_id}   {bpm}♪  {beats}/{lpb}   {key} {mode}   [{steps}]"

        for pid in self.order_list:
            item = QListWidgetItem(_label_for(pid))
            item.setData(Qt.ItemDataRole.UserRole, pid)  # store actual ID
            seq_list.addItem(item)

        layout.addWidget(seq_list)

        # --- Auto-apply helper: reads list → updates tracker ---
        def _sync_order():
            new_order = []
            for i in range(seq_list.count()):
                pid = seq_list.item(i).data(Qt.ItemDataRole.UserRole)
                new_order.append(pid)
            if new_order:
                tracker.order_list = new_order
                tracker.refresh_order_display()

        # Auto-apply after drag reorder
        seq_list.model().rowsMoved.connect(lambda *_: _sync_order())

        # --- Add pattern row ---
        add_row = QHBoxLayout()
        combo = QComboBox()
        for pid in sorted(self.pattern_lengths.keys()):
            combo.addItem(pid)
        add_row.addWidget(QLabel("Pattern:"))
        add_row.addWidget(combo)

        btn_add = QPushButton("Add")
        btn_add.setToolTip("Append selected pattern to end of sequence")
        def _add():
            pid = combo.currentText()
            item = QListWidgetItem(_label_for(pid))
            item.setData(Qt.ItemDataRole.UserRole, pid)
            seq_list.addItem(item)
            _sync_order()
        btn_add.clicked.connect(_add)
        add_row.addWidget(btn_add)

        btn_ins = QPushButton("Insert")
        btn_ins.setToolTip("Insert selected pattern above current selection")
        def _insert():
            pid = combo.currentText()
            row = seq_list.currentRow()
            if row < 0:
                row = seq_list.count()
            item = QListWidgetItem(_label_for(pid))
            item.setData(Qt.ItemDataRole.UserRole, pid)
            seq_list.insertItem(row, item)
            _sync_order()
        btn_ins.clicked.connect(_insert)
        add_row.addWidget(btn_ins)
        layout.addLayout(add_row)

        # --- Action buttons ---
        btn_row = QHBoxLayout()

        btn_dup = QPushButton("Duplicate")
        btn_dup.setToolTip("Duplicate the selected entry")
        def _dup():
            row = seq_list.currentRow()
            if row < 0:
                return
            pid = seq_list.item(row).data(Qt.ItemDataRole.UserRole)
            item = QListWidgetItem(_label_for(pid))
            item.setData(Qt.ItemDataRole.UserRole, pid)
            seq_list.insertItem(row + 1, item)
            _sync_order()
        btn_dup.clicked.connect(_dup)
        btn_row.addWidget(btn_dup)

        btn_rm = QPushButton("Remove")
        btn_rm.setToolTip("Remove the selected entry (must keep at least 1)")
        def _remove():
            if seq_list.count() <= 1:
                return
            row = seq_list.currentRow()
            if row >= 0:
                seq_list.takeItem(row)
                _sync_order()
        btn_rm.clicked.connect(_remove)
        btn_row.addWidget(btn_rm)

        btn_up = QPushButton("▲ Up")
        def _move_up():
            row = seq_list.currentRow()
            if row <= 0:
                return
            item = seq_list.takeItem(row)
            seq_list.insertItem(row - 1, item)
            seq_list.setCurrentRow(row - 1)
            _sync_order()
        btn_up.clicked.connect(_move_up)
        btn_row.addWidget(btn_up)

        btn_dn = QPushButton("▼ Down")
        def _move_down():
            row = seq_list.currentRow()
            if row < 0 or row >= seq_list.count() - 1:
                return
            item = seq_list.takeItem(row)
            seq_list.insertItem(row + 1, item)
            seq_list.setCurrentRow(row + 1)
            _sync_order()
        btn_dn.clicked.connect(_move_down)
        btn_row.addWidget(btn_dn)

        layout.addLayout(btn_row)

        # Double-click to jump to pattern
        def _jump(item):
            pid = item.data(Qt.ItemDataRole.UserRole)
            if pid and pid in tracker.pattern_lengths:
                tracker.switch_pattern(pid)
        seq_list.itemDoubleClicked.connect(_jump)

        # Clean up reference on close
        def _on_close(event):
            tracker._seq_editor_win = None
            event.accept()
        win.closeEvent = _on_close

        self._seq_editor_win = win
        win.show()

    def refresh_order_display(self):
        """Updates the order list widget with pattern items showing timing info."""
        self.order_list_widget.clear()
        playing_idx = getattr(self, '_play_seq_idx', -1)
        for i, pid in enumerate(self.order_list):
            from PyQt6.QtWidgets import QListWidgetItem
            # Build display text with timing info
            bpm, lpb, lpm, key, mode = self._get_pattern_timing(pid)
            beats_per_measure = lpm // lpb if lpb > 0 else 4
            label = f"{pid}  {bpm}♪ {beats_per_measure}/{lpb}  {key} {mode}"
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if i == playing_idx:
                item.setBackground(QBrush(QColor("#007acc")))
                item.setForeground(QBrush(QColor("white")))
            self.order_list_widget.addItem(item)
        # Auto-scroll to playing position
        if 0 <= playing_idx < self.order_list_widget.count():
            self.order_list_widget.scrollToItem(
                self.order_list_widget.item(playing_idx))

    def handle_cell_double_click(self, row, col):
        if col % self.sub_cols == 1: # 'Inst' column
            main_win = self.window()
            if hasattr(main_win, 'tabs'):
                main_win.active_tracker_cell = (row, col)
                main_win.tabs.setCurrentIndex(0) # Jump to Sound Design tab!
    def _build_tracks_from_grid(self, grid, num_steps, bank):
        """Reads a 2D grid (list of lists) into track dicts for the Sequencer.
        Supports FX1/FX2, per-track instrument tracking, and OFF events.
        """
        from engine.theory import Theory
        from engine.preset_manager import PresetManager

        # Cache default patch to avoid re-creating Sequencer each call
        if not hasattr(self, '_default_patch'):
            self._default_patch = PresetManager().get_default_patch()

        tracks = []

        # Helper to unwrap bank entries (may be {patch, display, folder} or raw dict)
        def _get_patch(entry):
            if isinstance(entry, dict) and "patch" in entry:
                return entry["patch"]
            return entry

        for t in range(self.current_tracks):
            sequence = []
            track_patch = self._default_patch
            if "INIT" in bank:
                track_patch = _get_patch(bank["INIT"])
            elif bank:
                track_patch = _get_patch(list(bank.values())[0])

            _standalone_pan = []  # PAN FX on rows with no note
            _standalone_vol = []  # VOL FX on rows with no note
            for r in range(num_steps):
                col_base = t * self.sub_cols
                if r >= len(grid):
                    break
                row_data = grid[r]

                note_str = row_data[col_base] if col_base < len(row_data) else ""

                if note_str == "OFF":
                    sequence.append({"step": r, "note": "OFF"})
                    continue

                if not note_str or note_str in ["---", ""]:
                    # Still check for standalone PAN/VOL automation on empty rows
                    fx1_check = row_data[col_base + 4] if col_base + 4 < len(row_data) else ""
                    fx2_check = row_data[col_base + 5] if col_base + 5 < len(row_data) else ""
                    for fxc in (fx1_check, fx2_check):
                        if isinstance(fxc, str):
                            if fxc.startswith("PAN "):
                                try:
                                    pv = int(fxc[4:])
                                    _standalone_pan.append({"step": r, "value": (pv / 127.5) - 1.0})
                                except ValueError:
                                    pass
                            elif fxc.startswith("VOL "):
                                try:
                                    pv = int(fxc[4:])
                                    _standalone_vol.append({"step": r, "level": pv / 255.0})
                                except ValueError:
                                    pass
                    continue

                inst_str = row_data[col_base + 1] if col_base + 1 < len(row_data) else ""
                vel_str = row_data[col_base + 2] if col_base + 2 < len(row_data) else ""
                gate_str = row_data[col_base + 3] if col_base + 3 < len(row_data) else ""
                fx1_str = row_data[col_base + 4] if col_base + 4 < len(row_data) else ""
                fx2_str = row_data[col_base + 5] if col_base + 5 < len(row_data) else ""

                if inst_str and inst_str not in ["---", ""] and inst_str in bank:
                    track_patch = _get_patch(bank[inst_str])

                try:
                    vel = int(vel_str) / 127.0 if vel_str and vel_str != "--" else 0.8
                except ValueError:
                    vel = 0.8
                try:
                    gate = int(gate_str) if gate_str and gate_str != "--" else 2
                except ValueError:
                    gate = 2

                # Support chord notation: "C-4,E-4,G-4" -> list of MIDI notes
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
                    "patch": track_patch,  # Per-event instrument
                }
                if fx1_str and fx1_str != "--":
                    event["fx1"] = fx1_str
                if fx2_str and fx2_str != "--":
                    event["fx2"] = fx2_str
                sequence.append(event)

            # Extract PAN and VOL FX commands into automation keyframes
            # These are track-level commands, not per-event audio FX
            pan_keyframes = []
            vol_keyframes = []
            for evt in sequence:
                for fx_key in ("fx1", "fx2"):
                    fx_str = evt.get(fx_key, "")
                    if isinstance(fx_str, str) and fx_str.startswith("PAN "):
                        try:
                            dec_val = int(fx_str[4:])
                            pan_keyframes.append({"step": evt["step"], "value": (dec_val / 127.5) - 1.0})
                            del evt[fx_key]
                        except (ValueError, KeyError):
                            pass
                    elif isinstance(fx_str, str) and fx_str.startswith("VOL "):
                        try:
                            dec_val = int(fx_str[4:])
                            vol_keyframes.append({"step": evt["step"], "level": dec_val / 255.0})
                            del evt[fx_key]
                        except (ValueError, KeyError):
                            pass

            # Merge standalone keyframes with event-extracted ones
            all_pan = pan_keyframes + _standalone_pan
            all_vol = vol_keyframes + _standalone_vol
            track_dict = {"patch": track_patch, "sequence": sequence}
            if all_pan:
                all_pan.sort(key=lambda kf: kf["step"])
                track_dict["pan_automation"] = all_pan
            if all_vol:
                all_vol.sort(key=lambda kf: kf["step"])
                track_dict["track_volume"] = all_vol
            tracks.append(track_dict)
        return tracks

    def _build_tracks(self, bank, start_row=0):
        """Convenience: builds tracks from the currently displayed table grid."""
        cols = self.current_tracks * self.sub_cols
        grid = []
        for r in range(start_row, self.total_steps):
            row_data = []
            for c in range(cols):
                item = self.table.item(r, c)
                row_data.append(item.text() if item else "")
            grid.append(row_data)
        return self._build_tracks_from_grid(grid, len(grid), bank)

    def play_current_pattern(self):
        """Renders and plays only the current pattern (not full song)."""
        self._save_pattern_timing()
        self.save_grid_to_pattern()
        main_win = self.window()
        bpm, lpb, lpm, key, mode = self._get_pattern_timing(self.active_pattern)
        bank = main_win.workbench_container.bank_data

        grid = self.patterns.get(self.active_pattern)
        pat_len = self.pattern_lengths.get(self.active_pattern, 64)
        if grid is None:
            return
        tracks = self._build_tracks_from_grid(grid, pat_len, bank)

        active_pat = self.active_pattern

        def _render_and_play():
            from engine.playback import Sequencer
            import numpy as np
            seq = Sequencer(44100)
            try:
                audio = seq.render_pattern(pat_len, bpm, tracks)
            except Exception as e:
                import traceback
                print(f"Render Error:\n{traceback.format_exc()}")
                return

            # Calculate timestamps for each step
            step_times = []
            step_time_values = []
            current_time = 0.0
            p_bpm, p_lpb, _, _, _ = self._get_pattern_timing(active_pat)
            step_dur = seq.calculate_step_time(p_bpm, p_lpb)
            for r in range(pat_len):
                step_times.append({"time": current_time, "pat_id": active_pat, "row": r})
                step_time_values.append(current_time)
                current_time += step_dur

            # Schedule UI updates + playback on the main thread
            from PyQt6.QtCore import QMetaObject, Qt as QtNS, Q_ARG
            QMetaObject.invokeMethod(self, "_on_render_done",
                QtNS.ConnectionType.QueuedConnection,
                Q_ARG(object, audio),
                Q_ARG(object, step_times),
                Q_ARG(object, step_time_values),
                Q_ARG(object, [(active_pat, pat_len)]),
                Q_ARG(object, current_time),
                Q_ARG(object, pat_len),
                Q_ARG(object, None))  # no full-song cache

        self.statusBar_msg = "Rendering..."
        if hasattr(main_win, 'statusBar'):
            main_win.statusBar().showMessage("Rendering pattern...")
        threading.Thread(target=_render_and_play, daemon=True).start()

    def play_solo_track(self, track_idx=None):
        """Plays only the specified track (or the selected track if none given)."""
        if track_idx is None:
            sel = self.table.selectedIndexes()
            if not sel:
                return
            col = sel[0].column()
            track_idx = col // self.sub_cols
        if track_idx >= self.current_tracks:
            return

        self.save_grid_to_pattern()
        main_win = self.window()
        bpm = main_win.spin_bpm.value()
        lpb = main_win.spin_lpb.value()
        bank = main_win.workbench_container.bank_data

        grid = self.patterns.get(self.active_pattern)
        pat_len = self.pattern_lengths.get(self.active_pattern, 64)
        if grid is None:
            return

        # Build tracks but only include the selected track
        all_tracks = self._build_tracks_from_grid(grid, pat_len, bank)
        solo_tracks = [all_tracks[track_idx]] if track_idx < len(all_tracks) else []
        if not solo_tracks:
            return

        active_pat = self.active_pattern

        def _render_and_play():
            from engine.playback import Sequencer
            import numpy as np
            seq = Sequencer(44100)
            try:
                audio = seq.render_pattern(pat_len, bpm, solo_tracks)
            except Exception as e:
                import traceback
                print(f"Solo Render Error:\n{traceback.format_exc()}")
                return

            step_times = []
            step_time_values = []
            current_time = 0.0
            step_dur = seq.calculate_step_time(bpm, lpb)
            for r in range(pat_len):
                step_times.append({"time": current_time, "pat_id": active_pat, "row": r})
                step_time_values.append(current_time)
                current_time += step_dur

            from PyQt6.QtCore import QMetaObject, Qt as QtNS, Q_ARG
            QMetaObject.invokeMethod(self, "_on_render_done",
                QtNS.ConnectionType.QueuedConnection,
                Q_ARG(object, audio),
                Q_ARG(object, step_times),
                Q_ARG(object, step_time_values),
                Q_ARG(object, [(active_pat, pat_len)]),
                Q_ARG(object, current_time),
                Q_ARG(object, pat_len),
                Q_ARG(object, None))

        if hasattr(main_win, 'statusBar'):
            main_win.statusBar().showMessage("Rendering solo track...")
        threading.Thread(target=_render_and_play, daemon=True).start()

    def play_sequence(self):
        """Renders and plays the entire song via the order list."""
        print("Master Tracker: Compiling Song from Order List...")
        self._save_pattern_timing()
        self.save_grid_to_pattern()  # Persist current grid first
        main_win = self.window()
        bank = main_win.workbench_container.bank_data

        # Snapshot order list and pattern data for the background thread
        order_snapshot = list(self.order_list)
        pat_lengths_snapshot = dict(self.pattern_lengths)
        pat_timings = {}
        grids = {}
        track_data = {}
        from engine.playback import Sequencer
        seq_tmp = Sequencer(44100)
        for pat_id in order_snapshot:
            pat_timings[pat_id] = self._get_pattern_timing(pat_id)
            grids[pat_id] = self.patterns.get(pat_id)
            pat_len = pat_lengths_snapshot.get(pat_id, 64)
            g = grids[pat_id]
            if g is not None:
                track_data[pat_id] = self._build_tracks_from_grid(g, pat_len, bank)

        def _render_and_play():
            from engine.playback import Sequencer
            import numpy as np
            seq = Sequencer(44100)

            audio_blocks = []
            play_pattern_steps = []
            for pat_id in order_snapshot:
                pat_len = pat_lengths_snapshot.get(pat_id, 64)
                pat_bpm, pat_lpb, _, _, _ = pat_timings[pat_id]
                grid = grids.get(pat_id)
                if grid is None:
                    step_dur = seq.calculate_step_time(pat_bpm, pat_lpb)
                    silence_samples = int(pat_len * step_dur * 44100)
                    audio_blocks.append(np.zeros((silence_samples, 2)))
                    play_pattern_steps.append((pat_id, pat_len, pat_bpm, pat_lpb))
                    continue
                tracks = track_data.get(pat_id, [])
                try:
                    block = seq.render_pattern(pat_len, pat_bpm, tracks, apply_limiter=False)
                    audio_blocks.append(block)
                except Exception as e:
                    import traceback
                    print(f"Render Error in pattern {pat_id}:\n{traceback.format_exc()}")
                    return
                play_pattern_steps.append((pat_id, pat_len, pat_bpm, pat_lpb))

            if not audio_blocks:
                return
            audio = np.concatenate(audio_blocks, axis=0)

            max_val = np.max(np.abs(audio))
            if max_val > 0.98:
                audio = audio * (0.98 / max_val)

            total_song_steps = sum(entry[1] for entry in play_pattern_steps)

            # Precalculate exact timestamps
            step_times = []
            step_time_values = []
            current_time = 0.0
            for pat_id, p_len, p_bpm, p_lpb in play_pattern_steps:
                step_dur = seq.calculate_step_time(p_bpm, p_lpb)
                for r in range(p_len):
                    step_times.append({"time": current_time, "pat_id": pat_id, "row": r})
                    step_time_values.append(current_time)
                    current_time += step_dur

            from PyQt6.QtCore import QMetaObject, Qt as QtNS, Q_ARG
            QMetaObject.invokeMethod(self, "_on_render_done",
                QtNS.ConnectionType.QueuedConnection,
                Q_ARG(object, audio),
                Q_ARG(object, step_times),
                Q_ARG(object, step_time_values),
                Q_ARG(object, play_pattern_steps),
                Q_ARG(object, current_time),
                Q_ARG(object, total_song_steps),
                Q_ARG(object, audio))  # cache for looping

        if hasattr(main_win, 'statusBar'):
            main_win.statusBar().showMessage("Rendering song...")
        threading.Thread(target=_render_and_play, daemon=True).start()

    @pyqtSlot(object, object, object, object, object, object, object)
    def _on_render_done(self, audio, step_times, step_time_values,
                        play_pattern_steps, total_duration, total_song_steps,
                        cached_audio):
        """Called on the main thread after background rendering completes."""
        import numpy as np
        import sounddevice as sd

        if audio.ndim == 2:
            self._rendered_audio = audio[:, 0]
        else:
            self._rendered_audio = audio
        self._play_pattern_steps = play_pattern_steps
        self._total_song_steps = total_song_steps
        self._step_times = step_times
        self._step_time_values = step_time_values  # cached for _update_viz
        self._total_duration = total_duration
        self._cached_full_audio = cached_audio  # for loop restart

        try:
            sd.play(audio, samplerate=44100)
        except Exception as e:
            print("Audio Playback Error:", e)
            return

        if hasattr(self, 'playhead_timer'):
            self.playhead_timer.stop()
        self._play_seq_idx = 0
        self._play_pat_row = 0
        self._play_global_step = 0
        self._play_start_time = time.perf_counter()
        self._play_pause_offset = 0.0
        self._is_playing = True

        # Switch to the first pattern if this is a song play
        if (isinstance(play_pattern_steps, list) and len(play_pattern_steps) > 0
                and len(play_pattern_steps[0]) >= 3):
            # Song mode (tuples have 4 elements)
            first_pat = play_pattern_steps[0][0]
            if first_pat != self.active_pattern:
                self.switch_pattern(first_pat)

        self.table.selectRow(0)
        self._start_viz_timer()

        main_win = self.window()
        if hasattr(main_win, 'statusBar'):
            main_win.statusBar().showMessage("Playing.")

    def playhead_tick(self):
        # Obsolete: replaced by precise perf_counter logic in _update_viz
        pass

    def _update_viz(self):
        """Master Playhead Tick & Oscilloscope Update (runs at ~55fps)."""
        if getattr(self, '_is_playing', False) and hasattr(self, '_play_start_time'):
            # 1. Update Playhead based on exact elapsed audio time
            elapsed = time.perf_counter() - self._play_start_time - self._play_pause_offset
            
            # Check for song end
            if elapsed >= getattr(self, '_total_duration', 0.0):
                main_win = self.window()
                if hasattr(main_win, 'btn_loop') and main_win.btn_loop.isChecked():
                    # Loop: replay cached audio instead of re-rendering
                    cached = getattr(self, '_cached_full_audio', None)
                    if cached is not None:
                        import sounddevice as sd
                        try:
                            sd.play(cached, samplerate=44100)
                        except Exception:
                            pass
                        self._play_start_time = time.perf_counter()
                        self._play_pause_offset = 0.0
                        self._play_global_step = 0
                        self._play_pat_row = 0
                        self._play_seq_idx = 0
                        if self._step_times:
                            first_pat = self._step_times[0]["pat_id"]
                            if first_pat != self.active_pattern:
                                self.switch_pattern(first_pat)
                        self.table.selectRow(0)
                        self.refresh_order_display()
                        return
                    else:
                        self.play_sequence()
                        return
                else:
                    self.stop_sequence()
                    return

            # Find current step via binary search on cached step times
            import bisect
            times = getattr(self, '_step_time_values', None)
            if times is None:
                times = [s["time"] for s in self._step_times]
            idx = bisect.bisect_right(times, elapsed) - 1
            if idx >= 0 and idx < len(self._step_times):
                step_info = self._step_times[idx]
                if self._play_global_step != idx:
                    self._play_global_step = idx
                    self._play_pat_row = step_info["row"]
                    pat_id = step_info["pat_id"]
                    
                    if pat_id != self.active_pattern:
                        self.switch_pattern(pat_id)
                        self.refresh_order_display()
                    
                    offset = getattr(self, '_play_from_offset', 0)
                    self.table.selectRow(self._play_pat_row + offset)

        # 2. Update Oscilloscope Window
        if not hasattr(self, '_rendered_audio') or self._rendered_audio is None:
            return
        import numpy as np
        audio = self._rendered_audio
        total = len(audio)
        total_steps = getattr(self, '_total_song_steps', self.total_steps)
        if total_steps == 0: total_steps = 1
        samples_per_step = total // total_steps
        global_step = getattr(self, '_play_global_step', 0)
        
        # Smooth interpolation between discrete steps based on exact elapsed time
        if getattr(self, '_is_playing', False):
            elapsed = time.perf_counter() - self._play_start_time - self._play_pause_offset
            exact_sample = int(elapsed * 44100)
            center = min(max(0, exact_sample), total - 1)
        else:
            center = global_step * samples_per_step
            
        half_window = 1200
        start = max(0, center - half_window)
        end = min(total, center + half_window)
        chunk = audio[start:end].copy()

        # Downsample to display points
        n_points = 400
        if len(chunk) > n_points:
            step = len(chunk) // n_points
            chunk = chunk[::step][:n_points]

        if len(chunk) < 4:
            return

        # Apply raised-cosine fade at both edges (25% on each side)
        n = len(chunk)
        fade_len = n // 4
        fade_in = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_len)))
        fade_out = 0.5 * (1 + np.cos(np.linspace(0, np.pi, fade_len)))
        envelope = np.ones(n)
        envelope[:fade_len] = fade_in
        envelope[-fade_len:] = fade_out
        chunk = chunk * envelope

        self.viz_curve.setData(chunk)
        self.viz_glow.setData(chunk)

    def _start_viz_timer(self):
        """Starts a fast timer (~30fps) for smooth oscilloscope updates."""
        if not hasattr(self, '_viz_timer'):
            from PyQt6.QtCore import QTimer
            self._viz_timer = QTimer(self)
            self._viz_timer.timeout.connect(self._update_viz)
        self._viz_timer.start(18)  # ~55fps

    def _stop_viz_timer(self):
        """Stops the viz update timer."""
        if hasattr(self, '_viz_timer'):
            self._viz_timer.stop()

    def pause_sequence(self):
        """Pauses the playhead tracing by halting elapsed time tracking."""
        if getattr(self, '_is_playing', False):
            self._is_playing = False
            self._pause_timestamp = time.perf_counter()

    def resume_sequence(self):
        """Resumes the playhead tracking, offsetting timestamps."""
        if not getattr(self, '_is_playing', False) and hasattr(self, '_pause_timestamp'):
            self._is_playing = True
            paused_duration = time.perf_counter() - self._pause_timestamp
            self._play_pause_offset += paused_duration
            
    def stop_sequence(self):
        self._is_playing = False
        self._play_from_offset = 0
        if hasattr(self, 'playhead_timer'):
            self.playhead_timer.stop()
        self._stop_viz_timer()
        self.table.clearSelection()
        self._rendered_audio = None
        self.viz_curve.setData([0] * 200)
        self.viz_glow.setData([0] * 200)
        self.refresh_order_display()

    def toggle_play_pause(self):
        """Spacebar toggle: play current pattern / pause / resume."""
        if getattr(self, '_is_playing', False):
            # Currently playing — pause
            self._is_playing = False
            self.pause_sequence()
            import sounddevice as sd
            sd.stop()
        elif hasattr(self, '_rendered_audio') and self._rendered_audio is not None:
            # Paused with audio still in buffer — resume
            self._is_playing = True
            self.resume_sequence()
        else:
            # Not playing — start fresh
            self._is_playing = True
            self.play_current_pattern()

    def play_from_row(self, start_row):
        """Start playback from a specific row in the current pattern.
        Renders the full pattern but skips audio to the start_row position."""
        self._save_pattern_timing()
        self.save_grid_to_pattern()
        main_win = self.window()

        from engine.playback import Sequencer
        import numpy as np
        seq = Sequencer(44100)

        bpm, lpb, lpm, key, mode = self._get_pattern_timing(self.active_pattern)
        bank = main_win.workbench_container.bank_data

        grid = self.patterns.get(self.active_pattern)
        pat_len = self.pattern_lengths.get(self.active_pattern, 64)
        if grid is None:
            return
        tracks = self._build_tracks_from_grid(grid, pat_len, bank)
        try:
            audio = seq.render_pattern(pat_len, bpm, tracks)
        except Exception as e:
            import traceback
            print(f"Render Error:\n{traceback.format_exc()}")
            return

        # Calculate sample offset for start_row
        step_duration = seq.calculate_step_time(bpm, lpb)
        start_sample = int(start_row * step_duration * 44100)

        if start_sample >= len(audio):
            return

        # Play from offset
        trimmed_audio = audio[start_sample:]

        if trimmed_audio.ndim == 2:
            self._rendered_audio = trimmed_audio[:, 0]
        else:
            self._rendered_audio = trimmed_audio
            
        self._total_song_steps = pat_len - start_row
        self._play_pattern_steps = [(self.active_pattern, pat_len)]
        self._is_playing = True

        import sounddevice as sd
        try:
            sd.play(trimmed_audio, samplerate=44100)
        except Exception as e:
            print("Audio Playback Error:", e)

        if hasattr(self, 'playhead_timer'):
            self.playhead_timer.stop()
            
        self._play_seq_idx = 0
        self._play_pat_row = start_row
        self._play_global_step = 0
        self._play_start_time = time.perf_counter()
        self._play_pause_offset = 0.0
        self._play_from_offset = start_row

        # Calculate exact timestamps for the remaining steps in the pattern
        self._step_times = []
        current_time = 0.0
        for r in range(start_row, pat_len):
            self._step_times.append({
                "time": current_time,
                "pat_id": self.active_pattern,
                "row": r
            })
            current_time += step_duration
        self._total_duration = current_time

        self.table.selectRow(start_row)
        self._start_viz_timer()
