# gui/context_menu.py
"""
Context-aware right-click menus for Lanthorn PSG.
Inspects click target and builds appropriate menus dynamically.
All actions apply to the full selection (Ctrl+click, Shift+click).
"""

from PyQt6.QtWidgets import QMenu, QInputDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QDialogButtonBox, QComboBox
from PyQt6.QtGui import QColor, QBrush, QAction
from PyQt6.QtCore import Qt

# FX command definitions: (display_name, code_prefix, description)
FX_COMMANDS = [
    ("Arpeggio",    "ARP", "Alternate +X, +Y semitones"),
    ("Slide Up",    "SUP", "Pitch bend up"),
    ("Slide Down",  "SDN", "Pitch bend down"),
    ("Portamento",  "PRT", "Glide to next note"),
    ("Vibrato",     "VIB", "Speed / Depth override"),
    ("Volume",      "VOL", "Set velocity (0-127)"),
    ("Echo",        "ECH", "Delay / Feedback"),
    ("Tremolo",     "TRM", "Speed / Depth"),
    ("Ring Mod",    "RNG", "Carrier mix amount"),
    ("Note Cut",    "CUT", "Delayed note cut"),
    ("Retrigger",   "RTG", "Stutter gate effect"),
    ("Saturation",  "SAT", "Harmonic saturation / drive"),
]

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
                    lambda checked, n=display: TrackerContextMenu._set_text_on_selected(
                        table_widget, tracker_widget, n, "#ffaa00", 1)
                )
        
        if folders and root_items:
            patches_menu.addSeparator()
        
        # Root-level instruments
        for key, display in sorted(root_items, key=lambda x: x[1]):
            action = patches_menu.addAction(f"🎹 {display}")
            action.triggered.connect(
                lambda checked, n=display: TrackerContextMenu._set_text_on_selected(
                    table_widget, tracker_widget, n, "#ffaa00", 1)
            )

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

    # --- FX Menu (categorized with presets and conflict detection) ---
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

        # ARP presets change based on chord detection
        if has_chord:
            arp_presets = [
                ("↑ Up (fast)",       "04"),
                ("↑ Up (slow)",       "08"),
                ("↓ Down (fast)",     "14"),
                ("↓ Down (slow)",     "18"),
                ("↕ Ping-Pong",      "24"),
                ("↕ Ping-Pong (slow)","28"),
                ("🎲 Random",         "34"),
                ("🎲 Random (slow)",  "38"),
            ]
            arp_desc = "Chord ARP: hi=pattern(0↑1↓2↕3🎲), lo=subdivisions"
        else:
            arp_presets = [
                ("Minor 3+5", "55"), ("Major 3+5", "71"),
                ("Octave",    "12"), ("Power 5+Oct", "124"),
            ]
            arp_desc = "+X,+Y semitones (hi=X, lo=Y)"

        # FX categories with presets
        FX_CATEGORIES = {
            "🎵 Pitch": [
                ("Arpeggio",   "ARP", arp_desc, arp_presets),
                ("Slide Up",   "SUP", "Pitch bend up (0-255 = 0-12 semitones)",
                    [("Subtle", "21"), ("Medium", "64"), ("Deep", "128"), ("Full Octave", "255")]),
                ("Slide Down", "SDN", "Pitch bend down (0-255 = 0-12 semitones)",
                    [("Subtle", "21"), ("Medium", "64"), ("Deep", "128"), ("Full Octave", "255")]),
                ("Portamento", "PRT", "Glide to next note",
                    [("Fast", "32"), ("Medium", "96"), ("Slow", "160"), ("Very Slow", "224")]),
                ("Detune",     "DTN", "Detune in cents",
                    [("Slight", "8"), ("Warm", "24"), ("Wide", "64"), ("Extreme", "128")]),
            ],
            "🌊 Modulation": [
                ("Vibrato",    "VIB", "hi=speed, lo=depth",
                    [("Gentle", "36"), ("Standard", "68"), ("Fast", "100"), ("Intense", "136")]),
                ("Tremolo",    "TRM", "hi=speed, lo=depth",
                    [("Gentle", "35"), ("Pulse", "70"), ("Fast", "104"), ("Chop", "138")]),
                ("Ring Mod",   "RNG", "Carrier mix amount",
                    [("Touch", "32"), ("Metallic", "96"), ("Harsh", "160"), ("Full", "255")]),
                ("Saturation", "SAT", "Harmonic drive / warmth",
                    [("Warm", "32"), ("Drive", "96"), ("Crunch", "160"), ("Fuzz", "255")]),
            ],
            "🔊 Dynamics": [
                ("Volume",     "VOL", "Volume level (0-255)",
                    [("Silent", "0"), ("Quiet", "48"), ("Half", "128"), ("Full", "255")]),
                ("Note Cut",   "CUT", "Delayed cut position",
                    [("Quick", "32"), ("Half", "128"), ("Late", "192"), ("Near End", "240")]),
                ("Pan",        "PAN", "Stereo position",
                    [("Hard Left", "0"), ("Left", "64"), ("Center", "128"), ("Right", "192"), ("Hard Right", "255")]),
                ("Retrigger",  "RTG", "Stutter gate (0-255 = 1-32 Hz)",
                    [("Slow", "32"), ("Medium", "96"), ("Fast", "160"), ("Buzz", "255")]),
            ],
            "⏱ Time": [
                ("Echo",       "ECH", "p1=delay x 50ms, p2=feedback",
                    [("Short", "34"), ("Medium", "68"), ("Long", "104"), ("Wash", "138")]),
                ("Delay",      "DLY", "Delay note start",
                    [("Nudge", "16"), ("Swing", "64"), ("Half", "128"), ("Late", "192")]),
            ],
        }

        # Conflicting FX when a chord is present (PRT still warned)
        CHORD_CONFLICTS = {
            "PRT": "⚠ PRT + Chord: glides each note independently — may sound muddy",
        }

        for cat_name, fx_list in FX_CATEGORIES.items():
            cat_menu = menu.addMenu(cat_name)
            for display_name, prefix, desc, presets in fx_list:
                # Check for chord conflicts
                conflict = CHORD_CONFLICTS.get(prefix) if has_chord else None

                fx_sub = cat_menu.addMenu(f"{display_name}  ({prefix})")
                fx_sub.setToolTip(desc)

                if conflict and prefix == "ARP":
                    # Disable ARP on chords entirely
                    warn = fx_sub.addAction(conflict)
                    warn.setEnabled(False)
                    continue
                elif conflict:
                    # Show warning but allow usage
                    warn = fx_sub.addAction(conflict)
                    warn.setEnabled(False)
                    fx_sub.addSeparator()

                # Quick presets
                for preset_label, dec_val in presets:
                    fx_str = f"{prefix} {dec_val}"
                    action = fx_sub.addAction(f"  {preset_label}  ({fx_str})")
                    fs = fx_str
                    ct = fx_col_type
                    action.triggered.connect(
                        lambda checked, f=fs, c=ct: TrackerContextMenu._set_text_on_selected(
                            table_widget, tracker_widget, f, "#55aaff", c))

                fx_sub.addSeparator()

                # Custom slider option
                custom_action = fx_sub.addAction("🔧 Custom...")
                pfx = prefix
                ds = desc
                ct2 = fx_col_type
                custom_action.triggered.connect(
                    lambda checked, p=pfx, d=ds, c=ct2: TrackerContextMenu._show_fx_dialog(
                        table_widget, tracker_widget, p, d, c))

    @staticmethod
    def _show_fx_dialog(table_widget, tracker_widget, prefix, description, col_type_filter):
        """Shows a smart FX parameter dialog with per-type slider controls."""
        from PyQt6.QtWidgets import QSpinBox

        # Define which FX use dual parameters and their labels (stored bitwise using >>4 and &0xF)
        DUAL_PARAM_FX = {
            "ARP": ("Pattern / +X semi", "Subdivisions / +Y semi"),
            "VIB": ("Speed (0=off, F=fast)", "Depth (0=none, F=deep)"),
            "TRM": ("Speed (0=off, F=fast)", "Depth (0=none, F=deep)"),
            "ECH": ("Delay (0=short, F=long)", "Feedback (0=dry, F=wet)"),
        }

        SINGLE_BYTE_FX = {
            "VOL": "Volume Level  (0=Silent > 255=Full)",
            "PAN": "Stereo Position  (0=Left, 128=Center, 255=Right)",
            "PRT": "Slide Time  (0=Fast > 255=Very Slow)",
            "SUP": "Pitch Bend Up  (0=None > 255=Full Octave, 80% slide)",
            "SDN": "Pitch Bend Down  (0=None > 255=Full Octave, 80% slide)",
            "CUT": "Cut Position  (0=Immediate > 255=Near End)",
            "DTN": "Detune  (0=None > 255=Extreme)",
            "DLY": "Delay Start  (0=None > 255=Late)",
            "RNG": "Ring Mod Mix  (0=Dry > 255=Full)",
            "RTG": "Retrigger Rate  (0=Slow 1Hz > 255=Buzz 32Hz)",
            "SAT": "Saturation  (0=Clean > 255=Heavy Fuzz)",
        }

        is_dual = prefix in DUAL_PARAM_FX

        dlg = QDialog(table_widget)
        dlg.setWindowTitle(f"{prefix} — {description}")
        dlg.setFixedSize(360, 280 if is_dual else 200)
        dlg.setStyleSheet("""
            QDialog { background-color: #252526; color: #cccccc; }
            QSlider::groove:horizontal { background: #3f3f46; height: 6px; border-radius: 3px; }
            QSlider::handle:horizontal { background: #007acc; width: 14px; margin: -4px 0; border-radius: 7px; }
            QLabel { color: #cccccc; }
            QSpinBox { background-color: #333; color: #00ff88; border: 1px solid #555;
                       font-family: 'Courier New'; font-size: 12px; padding: 2px; min-width: 45px; }
        """)
        layout = QVBoxLayout(dlg)

        # Title
        desc_label = QLabel(f"⚡ {prefix} — {description}")
        desc_label.setStyleSheet("font-weight: bold; color: #55aaff; font-size: 13px;")
        layout.addWidget(desc_label)

        # Live preview
        preview_label = QLabel("Output: -- --")
        preview_label.setStyleSheet(
            "font-family: 'Courier New'; font-size: 16px; color: #00ff88; font-weight: bold;")

        if is_dual:
            hi_label_text, lo_label_text = DUAL_PARAM_FX[prefix]

            # --- High parameter ---
            hi_row = QHBoxLayout()
            hi_lbl = QLabel(f"Hi: {hi_label_text}")
            hi_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            hi_slider = QSlider(Qt.Orientation.Horizontal)
            hi_slider.setRange(0, 15)
            hi_slider.setValue(0)
            hi_spin = QSpinBox()
            hi_spin.setRange(0, 15)
            hi_row.addWidget(hi_lbl, 2)
            hi_row.addWidget(hi_slider, 4)
            hi_row.addWidget(hi_spin, 1)
            layout.addLayout(hi_row)

            # --- Low parameter ---
            lo_row = QHBoxLayout()
            lo_lbl = QLabel(f"Lo: {lo_label_text}")
            lo_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            lo_slider = QSlider(Qt.Orientation.Horizontal)
            lo_slider.setRange(0, 15)
            lo_slider.setValue(0)
            lo_spin = QSpinBox()
            lo_spin.setRange(0, 15)
            lo_row.addWidget(lo_lbl, 2)
            lo_row.addWidget(lo_slider, 4)
            lo_row.addWidget(lo_spin, 1)
            layout.addLayout(lo_row)

            # Sync sliders ↔ spinboxes
            hi_slider.valueChanged.connect(hi_spin.setValue)
            hi_spin.valueChanged.connect(hi_slider.setValue)
            lo_slider.valueChanged.connect(lo_spin.setValue)
            lo_spin.valueChanged.connect(lo_slider.setValue)

            def _update_preview(*_):
                combined = (hi_slider.value() << 4) | lo_slider.value()
                preview_label.setText(f"Output: {prefix} {combined}")
            hi_slider.valueChanged.connect(_update_preview)
            lo_slider.valueChanged.connect(_update_preview)
            _update_preview()

            def _get_value():
                return (hi_slider.value() << 4) | lo_slider.value()

        else:
            single_desc = SINGLE_BYTE_FX.get(prefix, "Parameter (0-255)")

            param_row = QHBoxLayout()
            param_lbl = QLabel(single_desc)
            param_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            layout.addWidget(param_lbl)

            val_row = QHBoxLayout()
            val_slider = QSlider(Qt.Orientation.Horizontal)
            val_slider.setRange(0, 255)
            val_slider.setValue(0)
            val_spin = QSpinBox()
            val_spin.setRange(0, 255)
            val_row.addWidget(val_slider, 5)
            val_row.addWidget(val_spin, 1)
            layout.addLayout(val_row)

            # Sync slider ↔ spinbox
            val_slider.valueChanged.connect(val_spin.setValue)
            val_spin.valueChanged.connect(val_slider.setValue)

            def _update_preview_single(*_):
                preview_label.setText(f"Output: {prefix} {val_slider.value()}")
            val_slider.valueChanged.connect(_update_preview_single)
            _update_preview_single()

            def _get_value():
                return val_slider.value()

        layout.addWidget(preview_label)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.setStyleSheet("QPushButton { background-color: #333; color: #ccc; padding: 4px 16px; }")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            param_str = str(_get_value())
            fx_str = f"{prefix} {param_str}"
            TrackerContextMenu._set_text_on_selected(
                table_widget, tracker_widget, fx_str, "#55aaff", col_type_filter)

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

