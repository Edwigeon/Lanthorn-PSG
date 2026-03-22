# gui/context_menu.py
"""
Context-aware right-click menus for Lanthorn PSG.
Inspects click target and builds appropriate menus dynamically.
All actions apply to the full selection (Ctrl+click, Shift+click).
"""

from PyQt6.QtWidgets import QMenu, QInputDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QDialogButtonBox, QComboBox
from PyQt6.QtGui import QColor, QBrush, QAction
from PyQt6.QtCore import Qt

# Import centralized FX catalog from the unified manager
from .fx_ui_manager import FX_CATALOG, FX_COMMANDS, FXPopupWindow

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

VELOCITY_PRESETS = [
    ("Pianissimo (pp)", "32"),
    ("Piano (p)",       "64"),
    ("Mezzo-forte (mf)","96"),
    ("Forte (f)",       "112"),
    ("Fortissimo (ff)", "120"),
    ("Maximum",         "127"),
]

GATE_PRESETS = [
    ("1 step",     "1"),
    ("2 steps",    "2"),
    ("4 steps",    "4"),
    ("8 steps",    "8"),
    ("16 steps",   "16"),
    ("32 steps",   "32"),
]

# Smart defaults: auto-fill velocity/gate per folder category
SMART_DEFAULTS = {
    "drums":      {"vel": "127", "gate": "1"},
    "percussion": {"vel": "127", "gate": "1"},
    "bass":       {"vel": "100", "gate": "4"},
    "leads":      {"vel": "90",  "gate": "2"},
    "keys":       {"vel": "80",  "gate": "3"},
    "strings":    {"vel": "70",  "gate": "6"},
    "pads":       {"vel": "60",  "gate": "8"},
    "sfx":        {"vel": "100", "gate": "2"},
}


class TrackerContextMenu:
    """Builds and shows context menus for the tracker grid."""

    @staticmethod
    def show(table_widget, global_pos, tracker_widget):
        """
        Build and display context menu based on which column type was right-clicked.
        Actions apply to all selected cells via Ctrl/Shift selection.
        """
        col = table_widget.currentColumn()
        sub_cols = tracker_widget.sub_cols
        col_type = col % sub_cols  # 0=Note, 1=Inst, 2=Vel, 3=Gate, 4=FX1, 5=FX2, 6=Spacer

        if col_type == 6:
            return  # Spacer column, no menu

        menu = QMenu(table_widget)
        menu.setStyleSheet("""
            QMenu { background-color: #2d2d30; color: #cccccc; border: 1px solid #3f3f46; }
            QMenu::item:selected { background-color: #007acc; color: white; }
            QMenu::separator { background-color: #3f3f46; height: 1px; }
        """)

        # Playback at top of menu
        track_idx = col // sub_cols
        play_menu = menu.addMenu("▶ Play...")

        play_song_action = play_menu.addAction("▶ Play Song (full order list)")
        play_song_action.triggered.connect(tracker_widget.play_sequence)

        play_pat_action = play_menu.addAction(
            f"▶ Play Pattern {tracker_widget.active_pattern}")
        play_pat_action.triggered.connect(tracker_widget.play_current_pattern)

        solo_action = play_menu.addAction(
            f"▶ Solo Track {track_idx + 1}")
        solo_action.triggered.connect(
            lambda checked, t=track_idx: tracker_widget.play_solo_track(t))

        cursor_row = table_widget.currentRow()
        cursor_action = play_menu.addAction(
            f"▶ Play from Row {cursor_row}")
        cursor_action.triggered.connect(
            lambda checked, r=cursor_row: tracker_widget.play_from_row(r))

        play_menu.addSeparator()
        stop_action = play_menu.addAction("⏹ Stop")
        stop_action.triggered.connect(tracker_widget.stop_sequence)

        menu.addSeparator()

        # Copy / Paste
        copy_action = menu.addAction("📋 Copy Selected Cells")
        copy_action.triggered.connect(
            lambda: TrackerContextMenu._copy_selected(table_widget, tracker_widget)
        )
        paste_action = menu.addAction("📌 Paste")
        paste_action.triggered.connect(
            lambda: TrackerContextMenu._paste_selected(table_widget, tracker_widget)
        )

        menu.addSeparator()

        # --- Row Selection ---
        row_menu = menu.addMenu("📐 Select Row...")
        row_track_action = row_menu.addAction(
            f"Select Row {cursor_row} in Track {track_idx + 1}")
        row_track_action.triggered.connect(
            lambda: TrackerContextMenu._select_row_in_track(
                table_widget, tracker_widget, cursor_row, track_idx))
        row_all_action = row_menu.addAction(
            f"Select Row {cursor_row} (All Tracks)")
        row_all_action.triggered.connect(
            lambda: TrackerContextMenu._select_row_all_tracks(
                table_widget, tracker_widget, cursor_row))

        menu.addSeparator()

        # --- Intelligent Selection Tools ---
        smart_menu = menu.addMenu("🧠 Smart Edit")

        # Get current row's inst for context
        track_base = (col // sub_cols) * sub_cols
        inst_col = track_base + 1
        cur_inst_item = table_widget.item(table_widget.currentRow(), inst_col)
        cur_inst = cur_inst_item.text() if cur_inst_item else ""

        if cur_inst and cur_inst != "--":
            # Edit Similar: find all rows with same patch, batch-edit
            edit_sim_menu = smart_menu.addMenu(f"🔗 Edit Similar ({cur_inst})")

            vel_sub = edit_sim_menu.addMenu("🔊 Set Velocity on all")
            for label, val in VELOCITY_PRESETS:
                action = vel_sub.addAction(f"{label}")
                action.triggered.connect(
                    lambda checked, v=val, inst=cur_inst, tb=track_base, sc=sub_cols:
                        TrackerContextMenu._edit_similar(
                            table_widget, tracker_widget, inst, tb, sc, 2, v, "#d4d4d4")
                )

            gate_sub = edit_sim_menu.addMenu("⏱ Set Gate on all")
            for label, val in GATE_PRESETS:
                action = gate_sub.addAction(f"{label}")
                action.triggered.connect(
                    lambda checked, v=val, inst=cur_inst, tb=track_base, sc=sub_cols:
                        TrackerContextMenu._edit_similar(
                            table_widget, tracker_widget, inst, tb, sc, 3, v, "#d4d4d4")
                )

            fx_sim_sub = edit_sim_menu.addMenu("✨ Set FX1 on all")
            for fx_name, fx_code, fx_desc in FX_COMMANDS:
                action = fx_sim_sub.addAction(f"{fx_name} ({fx_code})")
                action.triggered.connect(
                    lambda checked, code=fx_code, inst=cur_inst, tb=track_base, sc=sub_cols:
                        TrackerContextMenu._edit_similar_fx(
                            table_widget, tracker_widget, inst, tb, sc, code)
                )

            clear_sim = edit_sim_menu.addAction("🗑 Clear FX1 on all")
            clear_sim.triggered.connect(
                lambda checked, inst=cur_inst, tb=track_base, sc=sub_cols:
                    TrackerContextMenu._edit_similar(
                        table_widget, tracker_widget, inst, tb, sc, 4, "--", "#555555")
            )

            # Select all rows with same patch
            select_action = smart_menu.addAction(f"🎯 Select all '{cur_inst}' rows")
            select_action.triggered.connect(
                lambda checked, inst=cur_inst, tb=track_base, sc=sub_cols:
                    TrackerContextMenu._select_similar(table_widget, tracker_widget, inst, tb, sc)
            )

        # Fill Pattern: tile selected content through the track
        fill_action = smart_menu.addAction("🔄 Fill Pattern (repeat cell data)")
        fill_action.triggered.connect(
            lambda: TrackerContextMenu._fill_pattern(table_widget, tracker_widget)
        )

        # Repeat Selection: extend a row selection pattern through the track
        repeat_action = smart_menu.addAction("📐 Repeat Selection (extend row pattern)")
        repeat_action.triggered.connect(
            lambda: TrackerContextMenu._repeat_selection(table_widget, tracker_widget)
        )

        menu.addSeparator()

        if col_type == 0:  # Note column
            TrackerContextMenu._build_note_menu(menu, table_widget, tracker_widget)
        elif col_type == 1:  # Inst column
            TrackerContextMenu._build_inst_menu(menu, table_widget, tracker_widget)
        elif col_type == 2:  # Vel column
            TrackerContextMenu._build_vel_menu(menu, table_widget, tracker_widget)
        elif col_type == 3:  # Gate column
            TrackerContextMenu._build_gate_menu(menu, table_widget, tracker_widget)
        elif col_type in [4, 5]:  # FX1 / FX2 columns
            TrackerContextMenu._build_fx_menu(menu, table_widget, tracker_widget)

        # Clear at bottom
        menu.addSeparator()
        clear_action = menu.addAction("🗑 Clear Selected Cells")
        clear_action.triggered.connect(
            lambda: TrackerContextMenu._clear_selected(table_widget, tracker_widget)
        )

        menu.exec(global_pos)

    # --- Helpers to get selected cells in a specific column type ---
    @staticmethod
    def _get_selected_cells(table_widget, tracker_widget, col_type_filter=None):
        """Returns selected items, optionally filtered to a specific column type."""
        sub_cols = tracker_widget.sub_cols
        items = table_widget.selectedItems()
        if col_type_filter is not None:
            items = [it for it in items if it.column() % sub_cols == col_type_filter]
        return items

    @staticmethod
    def _set_text_on_selected(table_widget, tracker_widget, text, color, col_type_filter=None):
        """Applies text + color to all selected cells of a given column type."""
        from PyQt6.QtWidgets import QTableWidgetItem
        items = TrackerContextMenu._get_selected_cells(table_widget, tracker_widget, col_type_filter)
        if not items:
            # Fallback: apply to current cell
            row, col = table_widget.currentRow(), table_widget.currentColumn()
            item = table_widget.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table_widget.setItem(row, col, item)
            items = [item]

        for item in items:
            item.setText(text)
            item.setForeground(QBrush(QColor(color)))

    @staticmethod
    def _set_inst_with_defaults(table_widget, tracker_widget, inst_name, folder):
        """Sets instrument name and applies smart default vel/gate based on folder."""
        from PyQt6.QtWidgets import QTableWidgetItem
        sub_cols = tracker_widget.sub_cols

        # Set the instrument name on selected cells (col_type 1)
        TrackerContextMenu._set_text_on_selected(
            table_widget, tracker_widget, inst_name, "#ffaa00", 1)

        # Look up smart defaults for this folder
        defaults = SMART_DEFAULTS.get(folder.lower(), {}) if folder else {}
        if not defaults:
            return

        # Apply defaults to vel/gate on the same rows
        items = TrackerContextMenu._get_selected_cells(
            table_widget, tracker_widget, 1)  # inst column items
        if not items:
            # Fallback: current cell
            row = table_widget.currentRow()
            col = table_widget.currentColumn()
            rows_cols = [(row, col)]
        else:
            rows_cols = [(item.row(), item.column()) for item in items]

        for row, col in rows_cols:
            track_base = (col // sub_cols) * sub_cols
            vel_col = track_base + 2
            gate_col = track_base + 3

            # Only fill if empty
            vel_item = table_widget.item(row, vel_col)
            if vel_item is None or vel_item.text() in ["--", "---", ""]:
                if vel_item is None:
                    vel_item = QTableWidgetItem()
                    vel_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table_widget.setItem(row, vel_col, vel_item)
                vel_item.setText(defaults["vel"])
                vel_item.setForeground(QBrush(QColor("#d4d4d4")))

            gate_item = table_widget.item(row, gate_col)
            if gate_item is None or gate_item.text() in ["--", "---", ""]:
                if gate_item is None:
                    gate_item = QTableWidgetItem()
                    gate_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table_widget.setItem(row, gate_col, gate_item)
                gate_item.setText(defaults["gate"])
                gate_item.setForeground(QBrush(QColor("#d4d4d4")))

    # --- Note Menu ---
    @staticmethod
    def _build_note_menu(menu, table_widget, tracker_widget):
        # Insert OFF
        off_action = menu.addAction("⏹ Insert OFF")
        off_action.triggered.connect(
            lambda: TrackerContextMenu._set_text_on_selected(
                table_widget, tracker_widget, "OFF", "#ff4444", 0)
        )

        menu.addSeparator()

        # Notes by octave
        for octave in range(2, 8):
            octave_menu = menu.addMenu(f"Octave {octave}")
            for note_name in NOTE_NAMES:
                label = f"{note_name}-{octave}" if "#" not in note_name else f"{note_name}{octave}"
                action = octave_menu.addAction(label)
                note_str = label  # capture
                action.triggered.connect(
                    lambda checked, ns=note_str: TrackerContextMenu._set_text_on_selected(
                        table_widget, tracker_widget, ns, "#00ff00", 0)
                )

        menu.addSeparator()

        # Chords submenu — pick full chord, voicings, or individual notes
        chord_menu = menu.addMenu("🎵 Chords")
        CHORD_SHAPES = {
            "Major":  [(0, "R"), (4, "3"), (7, "5")],
            "Minor":  [(0, "R"), (3, "♭3"), (7, "5")],
            "7th":    [(0, "R"), (4, "3"), (7, "5"), (10, "♭7")],
            "Min7":   [(0, "R"), (3, "♭3"), (7, "5"), (10, "♭7")],
            "Maj7":   [(0, "R"), (4, "3"), (7, "5"), (11, "7")],
            "Sus4":   [(0, "R"), (5, "4"), (7, "5")],
            "Dim":    [(0, "R"), (3, "♭3"), (6, "♭5")],
            "Aug":    [(0, "R"), (4, "3"), (8, "#5")],
            "Sus2":   [(0, "R"), (2, "2"), (7, "5")],
        }
        ALL_NOTES = ["C", "C#", "D", "D#", "E", "F",
                     "F#", "G", "G#", "A", "A#", "B"]

        def _midi_to_str(midi_val):
            o = (midi_val // 12) - 1
            n = ALL_NOTES[midi_val % 12]
            return f"{n}-{o}" if "#" not in n else f"{n}{o}"

        def _make_chord_str(midi_list):
            return ",".join(_midi_to_str(m) for m in midi_list)

        for octave in range(3, 7):
            oct_chord_menu = chord_menu.addMenu(f"Octave {octave}")
            for root_name in ALL_NOTES:
                root_sub = oct_chord_menu.addMenu(f"{root_name}-{octave}")
                root_midi = ALL_NOTES.index(root_name) + (octave + 1) * 12

                for shape_name, intervals in CHORD_SHAPES.items():
                    midi_notes = [root_midi + iv for iv, _ in intervals]
                    labels = [lbl for _, lbl in intervals]
                    full_str = _make_chord_str(midi_notes)

                    shape_sub = root_sub.addMenu(
                        f"{shape_name}  ({full_str})")

                    # Full chord (close voicing)
                    full_action = shape_sub.addAction(
                        f"🎵 Full  ({full_str})")
                    fs = full_str
                    full_action.triggered.connect(
                        lambda checked, c=fs: TrackerContextMenu._set_text_on_selected(
                            table_widget, tracker_widget, c, "#00ffaa", 0))

                    # Wide voicing: root dropped 1 octave
                    wide_notes = [midi_notes[0] - 12] + midi_notes[1:]
                    if wide_notes[0] >= 24:  # Don't go below C-1
                        wide_str = _make_chord_str(wide_notes)
                        wide_action = shape_sub.addAction(
                            f"🌊 Wide  ({wide_str})")
                        ws = wide_str
                        wide_action.triggered.connect(
                            lambda checked, c=ws: TrackerContextMenu._set_text_on_selected(
                                table_widget, tracker_widget, c, "#00ddff", 0))

                    shape_sub.addSeparator()

                    # Common voicings (if 3+ notes)
                    if len(midi_notes) >= 3:
                        # Power chord: Root + 5th
                        pwr = _make_chord_str([midi_notes[0], midi_notes[-1]])
                        pwr_action = shape_sub.addAction(
                            f"⚡ {labels[0]}+{labels[-1]}  ({pwr})")
                        ps = pwr
                        pwr_action.triggered.connect(
                            lambda checked, c=ps: TrackerContextMenu._set_text_on_selected(
                                table_widget, tracker_widget, c, "#00ffaa", 0))

                        # Root + 3rd (or 2nd/4th depending on shape)
                        r3 = _make_chord_str([midi_notes[0], midi_notes[1]])
                        r3_action = shape_sub.addAction(
                            f"🔗 {labels[0]}+{labels[1]}  ({r3})")
                        r3s = r3
                        r3_action.triggered.connect(
                            lambda checked, c=r3s: TrackerContextMenu._set_text_on_selected(
                                table_widget, tracker_widget, c, "#00ffaa", 0))

                        # Wide power: low root + top note
                        wide_pwr = _make_chord_str([midi_notes[0] - 12, midi_notes[-1]])
                        if midi_notes[0] - 12 >= 24:
                            wpwr_action = shape_sub.addAction(
                                f"⚡ Wide {labels[0]}+{labels[-1]}  ({wide_pwr})")
                            wps = wide_pwr
                            wpwr_action.triggered.connect(
                                lambda checked, c=wps: TrackerContextMenu._set_text_on_selected(
                                    table_widget, tracker_widget, c, "#00ddff", 0))

                        shape_sub.addSeparator()

                    # Individual notes with interval labels
                    for i, (iv, lbl) in enumerate(intervals):
                        m = root_midi + iv
                        ns = _midi_to_str(m)
                        note_action = shape_sub.addAction(
                            f"  {lbl}  →  {ns}")
                        nsc = ns
                        note_action.triggered.connect(
                            lambda checked, c=nsc: TrackerContextMenu._set_text_on_selected(
                                table_widget, tracker_widget, c, "#00ff00", 0))

    # --- Instrument Menu ---
    @staticmethod
    def _build_inst_menu(menu, table_widget, tracker_widget):
        main_win = tracker_widget.window()
        if not hasattr(main_win, 'workbench_container'):
            return

        bank_data = main_win.workbench_container.bank_data
        if not bank_data:
            menu.addAction("(No instruments loaded)").setEnabled(False)
            return

        # Group instruments by folder
        folders = {}  # folder_name -> [(key, display_name)]
        root_items = []  # [(key, display_name)]
        
        for key, entry in sorted(bank_data.items()):
            display = entry.get("display", key) if isinstance(entry, dict) else key
            folder = entry.get("folder") if isinstance(entry, dict) else None
            if folder:
                if folder not in folders:
                    folders[folder] = []
                folders[folder].append((key, display))
            else:
                root_items.append((key, display))
        
        patches_menu = menu.addMenu("🎹 Patches")
        
        # Folder submenus first
        for folder_name in sorted(folders.keys()):
            folder_menu = patches_menu.addMenu(f"📁 {folder_name}")
            for key, display in sorted(folders[folder_name], key=lambda x: x[1]):
                action = folder_menu.addAction(f"🎹 {display}")
                action.triggered.connect(
                    lambda checked, n=display, f=folder_name:
                        TrackerContextMenu._set_inst_with_defaults(
                            table_widget, tracker_widget, n, f))
        
        if folders and root_items:
            patches_menu.addSeparator()
        
        # Root-level instruments
        for key, display in sorted(root_items, key=lambda x: x[1]):
            action = patches_menu.addAction(f"🎹 {display}")
            action.triggered.connect(
                lambda checked, n=display:
                    TrackerContextMenu._set_inst_with_defaults(
                        table_widget, tracker_widget, n, None))

    # --- Velocity Menu ---
    @staticmethod
    def _build_vel_menu(menu, table_widget, tracker_widget):
        for label, val in VELOCITY_PRESETS:
            action = menu.addAction(f"🔊 {label}")
            v = val  # capture
            action.triggered.connect(
                lambda checked, vv=v: TrackerContextMenu._set_text_on_selected(
                    table_widget, tracker_widget, vv, "#d4d4d4", 2)
            )

    # --- Gate Menu ---
    @staticmethod
    def _build_gate_menu(menu, table_widget, tracker_widget):
        for label, val in GATE_PRESETS:
            action = menu.addAction(f"⏱ {label}")
            v = val  # capture
            action.triggered.connect(
                lambda checked, vv=v: TrackerContextMenu._set_text_on_selected(
                    table_widget, tracker_widget, vv, "#d4d4d4", 3)
            )

    # --- FX Menu (streamlined — FX Editor handles details) ---
    @staticmethod
    def _build_fx_menu(menu, table_widget, tracker_widget):
        col = table_widget.currentColumn()
        sub_cols = tracker_widget.sub_cols
        fx_col_type = col % sub_cols  # 4 or 5

        # Detect if this row has a chord in the Note column
        row = table_widget.currentRow()
        track_base = (col // sub_cols) * sub_cols
        note_item = table_widget.item(row, track_base)
        has_chord = note_item and "," in (note_item.text() or "")

        # Primary action: open the full FX Editor
        editor_action = menu.addAction("🎛️ Open FX Editor...")
        editor_action.triggered.connect(
            lambda checked, c=fx_col_type: TrackerContextMenu._show_fx_popup(
                table_widget, tracker_widget, c, has_chord))

        menu.addSeparator()

        # Quick presets for the most common effects
        quick_menu = menu.addMenu("⚡ Quick FX")
        quick_presets = [
            ("Vibrato — Light", "VIB 35"),
            ("Vibrato — Heavy", "VIB 137"),
            ("Echo — Short", "ECH 36"),
            ("Echo — Long", "ECH 101"),
            ("Saturation — Warm", "SAT 40"),
            ("Saturation — Crunch", "SAT 180"),
            ("Volume Fade Out", "VOL 0"),
            ("Pan Left", "PAN 0"),
            ("Pan Center", "PAN 128"),
            ("Pan Right", "PAN 255"),
        ]
        for label, fx_str in quick_presets:
            action = quick_menu.addAction(f"  {label}  ({fx_str})")
            fs = fx_str
            ct = fx_col_type
            action.triggered.connect(
                lambda checked, f=fs, c=ct: TrackerContextMenu._set_text_on_selected(
                    table_widget, tracker_widget, f, "#55aaff", c))

    @staticmethod
    def _show_fx_popup(table_widget, tracker_widget, col_type_filter, has_chord=False):
        """Launches the full FXPopupWindow with stacking support."""
        row = table_widget.currentRow()
        col = table_widget.currentColumn()
        item = table_widget.item(row, col)
        initial = item.text() if item else ""

        def _apply(fx_string):
            TrackerContextMenu._set_text_on_selected(
                table_widget, tracker_widget, fx_string, "#55aaff", col_type_filter)

        def _preview(fx_string):
            # Use the currently modified element from the tracker
            if hasattr(tracker_widget, 'play_cell_preview'):
                tracker_widget.play_cell_preview(row, col, fx_override=fx_string)

        # Get the instrument's FX chain for intelligent override toggling
        inst_chain = TrackerContextMenu._get_inst_fx_chain(
            table_widget, tracker_widget, row, col)

        popup = FXPopupWindow(
            parent=table_widget, on_apply=_apply, on_preview=_preview,
            has_chord=has_chord, initial_value=initial, show_override=True,
            inst_fx_chain=inst_chain)
        popup.exec()

    # --- Instrument FX chain lookup ---
    @staticmethod
    def _get_inst_fx_chain(table_widget, tracker_widget, row, col):
        """Returns the instrument's fx_chain list for the track at (row, col).
        Returns [] if unavailable."""
        try:
            sub_cols = tracker_widget.sub_cols
            track_base = (col // sub_cols) * sub_cols
            inst_col = track_base + 1  # Inst column is always offset 1
            inst_item = table_widget.item(row, inst_col)
            inst_name = inst_item.text().strip() if inst_item else ""
            if not inst_name or inst_name in ["---", "--", ""]:
                return []
            main_win = tracker_widget.window()
            if not main_win or not hasattr(main_win, 'workbench_container'):
                return []
            bank = main_win.workbench_container.bank_data
            cat = getattr(main_win.workbench_container, 'active_category', None)
            if cat and cat in bank and inst_name in bank[cat]:
                entry = bank[cat][inst_name]
                patch = entry if isinstance(entry, dict) else {}
                return patch.get("fx_chain", [])
        except Exception:
            pass
        return []

    # --- Clear ---
    @staticmethod
    def _clear_selected(table_widget, tracker_widget):
        """Clears all selected cells back to default placeholders."""
        sub_cols = tracker_widget.sub_cols
        for item in table_widget.selectedItems():
            col_type = item.column() % sub_cols
            if col_type in [0, 1]:
                item.setText("---")
                item.setForeground(QBrush(QColor("#d4d4d4")))
            elif col_type in [2, 3, 4, 5]:
                item.setText("--")
                item.setForeground(QBrush(QColor("#d4d4d4")))

    # --- Copy / Paste ---
    _clipboard = []  # class-level clipboard: [(relative_row, relative_col, text, col_type), ...]

    @staticmethod
    def _copy_selected(table_widget, tracker_widget):
        """Copies selected cells to an internal clipboard."""
        items = table_widget.selectedItems()
        if not items:
            return
        sub_cols = tracker_widget.sub_cols
        min_row = min(it.row() for it in items)
        min_col = min(it.column() for it in items)
        TrackerContextMenu._clipboard = []
        for it in items:
            col_type = it.column() % sub_cols
            TrackerContextMenu._clipboard.append(
                (it.row() - min_row, it.column() - min_col, it.text(), col_type)
            )

    @staticmethod
    def _paste_selected(table_widget, tracker_widget):
        """Pastes clipboard contents starting at the current cell."""
        from PyQt6.QtWidgets import QTableWidgetItem
        if not TrackerContextMenu._clipboard:
            return
        base_row = table_widget.currentRow()
        base_col = table_widget.currentColumn()
        color_map = {
            0: "#00ff00", 1: "#ffaa00", 2: "#d4d4d4",
            3: "#d4d4d4", 4: "#55aaff", 5: "#55aaff",
        }
        for rel_row, rel_col, text, col_type in TrackerContextMenu._clipboard:
            r = base_row + rel_row
            c = base_col + rel_col
            if r >= table_widget.rowCount() or c >= table_widget.columnCount():
                continue
            item = table_widget.item(r, c)
            if item is None:
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table_widget.setItem(r, c, item)
            item.setText(text)
            item.setForeground(QBrush(QColor(color_map.get(col_type, "#d4d4d4"))))

    # --- Smart Edit: Edit Similar ---
    @staticmethod
    def _edit_similar(table_widget, tracker_widget, patch_name, track_base, sub_cols, col_offset, value, color):
        """Finds all rows in this track with the given patch and sets the specified column to value."""
        from PyQt6.QtWidgets import QTableWidgetItem
        inst_col = track_base + 1
        target_col = track_base + col_offset
        count = 0
        for row in range(table_widget.rowCount()):
            inst_item = table_widget.item(row, inst_col)
            if inst_item and inst_item.text() == patch_name:
                item = table_widget.item(row, target_col)
                if item is None:
                    item = QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table_widget.setItem(row, target_col, item)
                item.setText(value)
                item.setForeground(QBrush(QColor(color)))
                count += 1

    @staticmethod
    def _edit_similar_fx(table_widget, tracker_widget, patch_name, track_base, sub_cols, fx_code):
        """Opens an FX dialog, then applies the result to all rows with the given patch."""
        from PyQt6.QtWidgets import QTableWidgetItem
        # Build a quick input for the parameter value
        param, ok = QInputDialog.getText(
            table_widget, f"Set {fx_code} on all '{patch_name}'",
            f"Parameter (0-255):", text="64")
        if ok and param:
            try:
                val = int(param)
                param_str = str(val)
            except ValueError:
                return
            fx_str = f"{fx_code} {param_str}"
            inst_col = track_base + 1
            fx1_col = track_base + 4
            for row in range(table_widget.rowCount()):
                inst_item = table_widget.item(row, inst_col)
                if inst_item and inst_item.text() == patch_name:
                    item = table_widget.item(row, fx1_col)
                    if item is None:
                        item = QTableWidgetItem()
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        table_widget.setItem(row, fx1_col, item)
                    item.setText(fx_str)
                    item.setForeground(QBrush(QColor("#55aaff")))

    # --- Row Selection ---
    @staticmethod
    def _select_row_in_track(table_widget, tracker_widget, row, track_idx):
        """Selects all data columns for a single row within one track."""
        from PyQt6.QtCore import QItemSelectionModel
        sub_cols = tracker_widget.sub_cols
        table_widget.clearSelection()
        sel_model = table_widget.selectionModel()
        track_base = track_idx * sub_cols
        # Select Note, Inst, Vel, Gate, FX1, FX2 (skip spacer at offset 6)
        for c in range(track_base, track_base + min(sub_cols, 6)):
            idx = table_widget.model().index(row, c)
            sel_model.select(idx, QItemSelectionModel.SelectionFlag.Select)

    @staticmethod
    def _select_row_all_tracks(table_widget, tracker_widget, row):
        """Selects all data columns across all tracks for a given row."""
        from PyQt6.QtCore import QItemSelectionModel
        sub_cols = tracker_widget.sub_cols
        num_tracks = tracker_widget.current_tracks
        table_widget.clearSelection()
        sel_model = table_widget.selectionModel()
        for t in range(num_tracks):
            track_base = t * sub_cols
            for c in range(track_base, track_base + min(sub_cols, 6)):
                idx = table_widget.model().index(row, c)
                sel_model.select(idx, QItemSelectionModel.SelectionFlag.Select)

    # --- Smart Edit: Select Similar ---
    @staticmethod
    def _select_similar(table_widget, tracker_widget, patch_name, track_base, sub_cols):
        """Selects all rows in this track that use the given patch."""
        from PyQt6.QtCore import QItemSelectionModel
        inst_col = track_base + 1
        table_widget.clearSelection()
        sel_model = table_widget.selectionModel()
        for row in range(table_widget.rowCount()):
            inst_item = table_widget.item(row, inst_col)
            if inst_item and inst_item.text() == patch_name:
                for c in range(track_base, track_base + sub_cols):
                    idx = table_widget.model().index(row, c)
                    sel_model.select(idx, QItemSelectionModel.SelectionFlag.Select)

    # --- Smart Edit: Fill Pattern ---
    @staticmethod
    def _fill_pattern(table_widget, tracker_widget):
        """Takes the selected block and tiles it through the rest of the track."""
        from PyQt6.QtWidgets import QTableWidgetItem
        ranges = table_widget.selectedRanges()
        if not ranges:
            return

        sel = ranges[0]
        start_row = sel.topRow()
        end_row = sel.bottomRow()
        start_col = sel.leftColumn()
        end_col = sel.rightColumn()

        length = end_row - start_row + 1
        if length < 1:
            return

        sub_cols = tracker_widget.sub_cols
        total_rows = table_widget.rowCount()

        # Capture the source block
        block = []
        for r in range(start_row, end_row + 1):
            row_data = []
            for c in range(start_col, end_col + 1):
                item = table_widget.item(r, c)
                if item:
                    row_data.append((item.text(), item.foreground().color().name()))
                else:
                    row_data.append(("", "#d4d4d4"))
            block.append(row_data)

        # Tile the block forward through the pattern
        cursor = start_row + length
        while cursor + length <= total_rows:
            for i, row_data in enumerate(block):
                for j, (text, color) in enumerate(row_data):
                    r = cursor + i
                    c = start_col + j
                    if r < total_rows and c < table_widget.columnCount():
                        item = table_widget.item(r, c)
                        if item is None:
                            item = QTableWidgetItem()
                            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                            table_widget.setItem(r, c, item)
                        item.setText(text)
                        item.setForeground(QBrush(QColor(color)))
            cursor += length


    # --- Smart Edit: Repeat Selection Pattern ---
    @staticmethod
    def _repeat_selection(table_widget, tracker_widget):
        """Detects the row interval pattern in the current selection and extends
        it through the rest of the pattern. E.g. selecting rows 0, 4, 8 detects
        a stride of 4 and selects 12, 16, 20, ... through the end.
        Works with irregular patterns too: rows 0, 3, 4 repeats as 0,3,4,7,8,11,12..."""
        from PyQt6.QtCore import QItemSelectionModel

        selection = table_widget.selectedRanges()
        if not selection:
            return

        # Collect all selected row numbers and columns
        selected_rows = set()
        col_start = None
        col_end = None
        for rng in selection:
            for r in range(rng.topRow(), rng.bottomRow() + 1):
                selected_rows.add(r)
            if col_start is None or rng.leftColumn() < col_start:
                col_start = rng.leftColumn()
            if col_end is None or rng.rightColumn() > col_end:
                col_end = rng.rightColumn()

        if len(selected_rows) < 2:
            return  # Need at least 2 rows to detect a pattern

        rows_sorted = sorted(selected_rows)
        total_rows = table_widget.rowCount()

        # Compute the gap sequence between selected rows
        gaps = [rows_sorted[i + 1] - rows_sorted[i] for i in range(len(rows_sorted) - 1)]
        cycle_length = rows_sorted[-1] - rows_sorted[0] + gaps[-1]  # full period

        # Build the offset pattern relative to the first selected row
        offsets = [r - rows_sorted[0] for r in rows_sorted]

        # Extend selection forward
        sel_model = table_widget.selectionModel()
        base = rows_sorted[0] + cycle_length
        while base <= total_rows - 1:
            for offset in offsets:
                row = base + offset
                if row < total_rows:
                    for c in range(col_start, col_end + 1):
                        idx = table_widget.model().index(row, c)
                        sel_model.select(idx, QItemSelectionModel.SelectionFlag.Select)
            base += cycle_length


class BankContextMenu:
    """Context menu for the Instrument Bank tree widget."""

    @staticmethod
    def show(bank_tree, global_pos, workbench):
        menu = QMenu(bank_tree)
        menu.setStyleSheet("""
            QMenu { background-color: #2d2d30; color: #cccccc; border: 1px solid #3f3f46; }
            QMenu::item:selected { background-color: #007acc; color: white; }
        """)

        key = workbench._get_selected_key()

        new_action = menu.addAction("➕ New Instrument")
        new_action.triggered.connect(lambda: workbench.add_instrument())

        folder_action = menu.addAction("📁 New Folder")
        folder_action.triggered.connect(lambda: workbench.add_folder())

        if key:
            menu.addSeparator()

            load_action = menu.addAction("📂 Load to Editor")
            load_action.triggered.connect(lambda: workbench.load_instrument())

            save_action = menu.addAction("💾 Store from Editor")
            save_action.triggered.connect(lambda: workbench.save_instrument())

            dup_action = menu.addAction("📋 Duplicate")
            dup_action.triggered.connect(
                lambda: BankContextMenu._duplicate(workbench))

            menu.addSeparator()

            del_action = menu.addAction("🗑 Delete")
            del_action.triggered.connect(
                lambda: workbench.delete_instrument())

            save_disk_action = menu.addAction("💽 Save to Disk")
            save_disk_action.triggered.connect(
                lambda: BankContextMenu._save_to_disk(workbench))

        menu.exec(global_pos)

    @staticmethod
    def _duplicate(workbench):
        key = workbench._get_selected_key()
        if key and key in workbench.bank_data:
            import copy
            entry = workbench.bank_data[key]
            display = entry.get("display", key)
            folder = entry.get("folder")
            new_display = f"{display} (Copy)"
            new_key = f"{folder}/{new_display}" if folder else new_display
            workbench.bank_data[new_key] = {
                "patch": copy.deepcopy(entry["patch"]),
                "display": new_display,
                "folder": folder
            }
            # Save copy to disk
            safe_name = "".join([c for c in new_display if c.isalpha() or c.isdigit() or c=='_']).rstrip()
            workbench.preset_mgr.save_instrument(safe_name, entry["patch"].copy(), folder=folder)
            workbench._populate_bank_tree()

    @staticmethod
    def _save_to_disk(workbench):
        key = workbench._get_selected_key()
        if key and key in workbench.bank_data:
            entry = workbench.bank_data[key]
            folder = entry.get("folder")
            name = key.split("/")[-1] if "/" in key else key
            safe_name = "".join([c for c in name if c.isalpha() or c.isdigit() or c=='_']).rstrip()
            workbench.preset_mgr.save_instrument(safe_name, entry["patch"].copy(), folder=folder)

