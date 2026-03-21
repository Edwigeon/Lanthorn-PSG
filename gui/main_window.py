# File: lanthorn_psg/gui/main_window.py

import os
import json
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QToolBar, QPushButton, QSpinBox, QLabel, QFileDialog,
    QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QTextBrowser, QDoubleSpinBox, QCheckBox, QHBoxLayout
)
from PyQt6.QtGui import QAction, QKeySequence, QFont, QIcon
from PyQt6.QtCore import Qt

# Import your custom UI modules
from .workbench import WorkbenchWidget
from .tracker import TrackerWidget
from .visualizer import SfxCanvas
from .export_dialog import ExportDialog
from engine.csv_handler import CsvHandler
from export.wave_baker import WaveBaker

class LanthornMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lanthorn PSG v0.3 — Tracker & SFX Painter")
        self.resize(1280, 720)

        # Application icon — resolve for PyInstaller bundle, dist folder, or dev mode
        import os, sys
        icon_name = 'lanthorn_icon.png'
        candidates = [
            os.path.join(getattr(sys, '_MEIPASS', ''), icon_name),          # PyInstaller temp
            os.path.join(os.path.dirname(sys.executable), icon_name),       # next to binary
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), icon_name),  # dev
        ]
        for p in candidates:
            if os.path.exists(p):
                self.setWindowIcon(QIcon(p))
                break
        self._current_project_path = None  # For quick-save
        self._current_sfx_path = None       # For SFX quick-save
        self._unsaved_changes = False       # Dirty flag for exit confirmation
        
        # Expanded Dark Theme to include the Menu Bar styling (enforcing Monospace)
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; font-family: 'Courier New', Courier, monospace; }
            QWidget { background-color: #252526; color: #d4d4d4; font-family: 'Courier New', Courier, monospace; }
            QMenuBar { background-color: #2d2d30; color: #cccccc; }
            QMenuBar::item:selected { background-color: #3f3f46; }
            QMenu { background-color: #2d2d30; color: #cccccc; border: 1px solid #3f3f46; }
            QMenu::item:selected { background-color: #007acc; color: white; }
            QTabWidget::pane { border: 1px solid #3f3f46; background-color: #1e1e1e; }
            QTabBar::tab { background: #2d2d30; color: #cccccc; padding: 8px 20px; border: 1px solid #3f3f46; }
            QTabBar::tab:selected { background: #007acc; color: white; }
            QStatusBar { background: #007acc; color: white; font-weight: bold; }
            QScrollBar:vertical { background: #3a3a3a; width: 12px; margin: 0px; border-radius: 6px; }
            QScrollBar::handle:vertical { background: #6e6e6e; min-height: 20px; border-radius: 6px; }
            QScrollBar::handle:vertical:hover { background: #909090; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar:horizontal { background: #3a3a3a; height: 12px; margin: 0px; border-radius: 6px; }
            QScrollBar::handle:horizontal { background: #6e6e6e; min-width: 20px; border-radius: 6px; }
            QScrollBar::handle:horizontal:hover { background: #909090; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        """)

        self.create_menu_bar()
        self.create_transport_bar()
        self.init_ui()

    def create_transport_bar(self):
        """Builds the Universal Transport Bar available across all tabs."""
        toolbar = QToolBar("Transport")
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        # 1. Playback Controls
        btn_play = QPushButton("▶ Play")
        btn_play.clicked.connect(self.global_play)
        
        btn_pause = QPushButton("⏸ Pause")
        btn_pause.clicked.connect(self.global_pause)
        
        btn_stop = QPushButton("⏹ Stop")
        btn_stop.clicked.connect(self.global_stop)
        
        self.btn_loop = QPushButton("🔁 Loop")
        self.btn_loop.setCheckable(True)
        
        for btn in [btn_play, btn_pause, btn_stop, self.btn_loop]:
            btn.setStyleSheet("background-color: #3f3f46; color: white; padding: 5px; font-weight: bold;")
            toolbar.addWidget(btn)
            
        toolbar.addSeparator()

        # 2. BPM Control
        lbl_bpm = QLabel("  BPM: ")
        self.spin_bpm = QSpinBox()
        self.spin_bpm.setRange(20, 999)
        self.spin_bpm.setValue(120)
        toolbar.addWidget(lbl_bpm)
        toolbar.addWidget(self.spin_bpm)

        toolbar.addSeparator()

        # 3. Time Signature / Stepping Controls
        lbl_lpb = QLabel("  Lines/Beat: ")
        self.spin_lpb = QSpinBox()
        self.spin_lpb.setRange(1, 16)
        self.spin_lpb.setValue(4)
        
        lbl_lpm = QLabel("  Lines/Measure: ")
        self.spin_lpm = QSpinBox()
        self.spin_lpm.setRange(1, 64)
        self.spin_lpm.setValue(16)

        toolbar.addWidget(lbl_lpb)
        toolbar.addWidget(self.spin_lpb)
        toolbar.addWidget(lbl_lpm)
        toolbar.addWidget(self.spin_lpm)

    def global_play(self):
        """Routes playback command depending on the active Tab."""
        idx = self.tabs.currentIndex()
        if idx == 0:
            if hasattr(self.workbench_container, 'play_preview'):
                self.workbench_container.play_preview()
        elif idx == 1:
            if hasattr(self.tracker_container, 'play_sequence'):
                self.tracker_container.play_sequence()
        elif idx == 2:
            if hasattr(self.visual_canvas, 'play_sfx'):
                self.visual_canvas.play_sfx()

    def global_pause(self):
        """Pauses or resumes audio playback and the playhead timer."""
        tracker = self.tracker_container if hasattr(self, 'tracker_container') else None
        
        if hasattr(self, '_is_paused') and self._is_paused:
            # Resume
            self._is_paused = False
            self.statusBar().showMessage("Resumed.")
            if tracker and hasattr(tracker, 'resume_sequence'):
                tracker.resume_sequence()
        else:
            # Pause — do NOT call sd.stop() as it destroys the stream
            self._is_paused = True
            self.statusBar().showMessage("Paused.")
            if tracker and hasattr(tracker, 'pause_sequence'):
                tracker.pause_sequence()

    def global_stop(self):
        """Halts all background sounddevice audio and stops UI timers."""
        import sounddevice as sd
        self._is_paused = False
        try:
            sd.stop()
        except Exception:
            pass
        if hasattr(self, 'tracker_container') and hasattr(self.tracker_container, 'stop_sequence'):
            self.tracker_container.stop_sequence()

    def create_menu_bar(self):
        """Builds the top utility dropdown menus."""
        menu_bar = self.menuBar()

        # ─── FILE MENU ───
        file_menu = menu_bar.addMenu("File")

        # -- Project --
        new_action = QAction("📄 New Project", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.setStatusTip("Start a fresh project")
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)

        load_action = QAction("📂 Open Project...", self)
        load_action.setShortcut(QKeySequence("Ctrl+O"))
        load_action.setStatusTip("Open a tracker project (.csv)")
        load_action.triggered.connect(self.load_project)
        file_menu.addAction(load_action)

        save_action = QAction("💾 Save Project...", self)
        save_action.setStatusTip("Save tracker project to CSV")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        # -- SFX Canvas --
        load_sfx_action = QAction("🎨 Open SFX Canvas...", self)
        load_sfx_action.setStatusTip("Open an SFX canvas (.sfx.csv)")
        load_sfx_action.triggered.connect(self.load_sfx_project)
        file_menu.addAction(load_sfx_action)

        save_sfx_action = QAction("🎨 Save SFX Canvas...", self)
        save_sfx_action.setStatusTip("Save SFX canvas to .sfx.csv")
        save_sfx_action.triggered.connect(self.save_sfx_project)
        file_menu.addAction(save_sfx_action)

        file_menu.addSeparator()

        # -- Export --
        export_audio_action = QAction("💽 Export Tracker Audio...", self)
        export_audio_action.setStatusTip("Render tracker to WAV/OGG/MP3")
        export_audio_action.triggered.connect(self.export_tracker_audio)
        file_menu.addAction(export_audio_action)

        export_sfx_action = QAction("🔊 Export SFX Audio...", self)
        export_sfx_action.setStatusTip("Render SFX canvas to audio file")
        export_sfx_action.triggered.connect(self.export_sfx_audio)
        file_menu.addAction(export_sfx_action)

        file_menu.addSeparator()

        # -- Settings --
        settings_action = QAction("⚙ Settings...", self)
        settings_action.setStatusTip("A4 tuning, export directory")
        settings_action.triggered.connect(self.show_settings_dialog)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("❌ Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ─── Keyboard Shortcuts (hidden) ───
        save_shortcut = QAction("Quick Save", self)
        save_shortcut.setShortcut(QKeySequence("Ctrl+S"))
        save_shortcut.triggered.connect(self.quick_save)
        self.addAction(save_shortcut)

        # ─── HELP MENU ───
        help_menu = menu_bar.addMenu("Help")

        help_action = QAction("📖 Keyboard Shortcuts & Help...", self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self.show_help_dialog)
        help_menu.addAction(help_action)

        help_menu.addSeparator()

        about_action = QAction("ℹ About", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _show_about_dialog(self):
        """Minimal About dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle("About Lanthorn PSG")
        dlg.setFixedSize(340, 240)
        dlg.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a2e, stop:1 #16213e);
            }
            QLabel { color: #ddd; }
        """)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(30, 25, 30, 20)
        layout.setSpacing(10)

        # Title
        title = QLabel("Lanthorn PSG")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #ffcc00; letter-spacing: 2px;")
        layout.addWidget(title)

        # Description
        desc = QLabel("Programmable Sound Generator\nTracker & SFX Painter")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("font-size: 12px; color: #88aacc;")
        layout.addWidget(desc)

        # Version
        ver = QLabel("Version 0.3")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("font-size: 13px; color: #aaccee; margin-top: 4px;")
        layout.addWidget(ver)

        layout.addStretch()

        # Author & License
        footer = QLabel("Created by Edwigeon\nOpen Source · MIT License")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("font-size: 11px; color: #667788;")
        layout.addWidget(footer)

        dlg.exec()

    def new_project(self):
        """Resets everything to a blank project."""
        reply = QMessageBox.question(self, "New Project",
            "Start a new project? Unsaved changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Stop any playback
        self.global_stop()

        # Reset tracker
        tracker = self.tracker_container
        tracker.patterns = {"A": None}
        tracker.pattern_lengths = {"A": 64}
        tracker.pattern_meta = {}  # Clear stale per-pattern timing
        tracker.order_list = ["A"]
        tracker.active_pattern = "A"
        tracker.total_steps = 64
        tracker.current_tracks = 4
        tracker.pattern_combo.blockSignals(True)
        tracker.pattern_combo.clear()
        tracker.pattern_combo.addItem("A")
        tracker.pattern_combo.blockSignals(False)
        tracker.spin_pat_len.blockSignals(True)
        tracker.spin_pat_len.setValue(64)
        tracker.spin_pat_len.blockSignals(False)
        tracker.table.setRowCount(64)
        tracker.table.setColumnCount(tracker.current_tracks * tracker.sub_cols)
        tracker.setup_table_headers()
        tracker.populate_grid()
        tracker.recolor_all_cells()
        tracker.refresh_order_display()

        # Reset bank
        self.workbench_container.bank_data.clear()
        self.workbench_container._populate_bank_tree()

        # Reset globals
        self.spin_bpm.setValue(120)
        self.spin_lpb.setValue(4)
        self._current_project_path = None
        self._unsaved_changes = False
        self._update_status_context()
        self.statusBar().showMessage("New project created.")

    def load_project(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Load Lanthorn Project", "", "CSV Files (*.csv);;All Files (*)")
        if filename:
            tracker = self.tracker_container
            workbench = self.workbench_container
            success, msg = CsvHandler.load_project(filename, tracker, workbench.bank_data)
            if success:
                self._current_project_path = filename
                self._unsaved_changes = False
                self._update_status_context()
                self.statusBar().showMessage(f"Loaded: {filename}")
                workbench._populate_bank_tree()
            else:
                QMessageBox.critical(self, "Error Loading Project", msg)

    def save_project(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Lanthorn Project", "", "CSV Files (*.csv);;All Files (*)")
        if filename:
            if not filename.endswith('.csv'):
                filename += '.csv'
            self._save_to_path(filename)

    def quick_save(self):
        """Saves to the current file path without showing a dialog. Falls back to Save As."""
        if self._current_project_path:
            self._save_to_path(self._current_project_path)
        else:
            self.save_project()

    def _save_to_path(self, filename):
        """Internal: serialize and write the project to the given path."""
        tracker = self.tracker_container
        workbench = self.workbench_container
        success, msg = CsvHandler.save_project(
            filename, tracker, workbench.bank_data,
            self.spin_bpm.value(), self.spin_lpb.value(),
            tracker.theory_engine.combo_root.currentText(),
            tracker.theory_engine.combo_mode.currentText(),
            self.spin_lpm.value()
        )
        if success:
            self._current_project_path = filename
            self._unsaved_changes = False
            self._update_status_context()
            self.statusBar().showMessage(f"Saved: {filename}")
        else:
            QMessageBox.critical(self, "Error Saving Project", msg)

    def export_tracker_audio(self):
        """Renders the full song (all patterns via order list) and exports."""
        dlg = ExportDialog(self, title="Export Tracker Audio", default_name="tracker_export")
        if dlg.exec() != ExportDialog.DialogCode.Accepted:
            return

        settings = dlg.get_export_settings()

        try:
            from PyQt6.QtWidgets import QProgressDialog, QApplication
            tracker = self.tracker_container
            tracker._save_pattern_timing()
            tracker.save_grid_to_pattern()
            bank = self.workbench_container.bank_data

            from engine.playback import Sequencer
            import numpy as np
            seq = Sequencer(44100)

            total_patterns = len(tracker.order_list)
            progress = QProgressDialog("Rendering audio...", "Cancel", 0, total_patterns + 1, self)
            progress.setWindowTitle("Exporting")
            progress.setMinimumDuration(0)
            progress.setValue(0)
            QApplication.processEvents()

            audio_blocks = []
            for i, pat_id in enumerate(tracker.order_list):
                if progress.wasCanceled():
                    self.statusBar().showMessage("Export cancelled.")
                    return
                progress.setValue(i)
                progress.setLabelText(f"Rendering pattern {pat_id} ({i+1}/{total_patterns})...")
                QApplication.processEvents()

                pat_len = tracker.pattern_lengths.get(pat_id, 64)
                pat_bpm, pat_lpb, _, _, _ = tracker._get_pattern_timing(pat_id)
                grid = tracker.patterns.get(pat_id)
                if grid is None:
                    step_dur = seq.calculate_step_time(pat_bpm, pat_lpb)
                    silence = int(pat_len * step_dur * 44100)
                    audio_blocks.append(np.zeros((silence, 2)))
                    continue
                tracks = tracker._build_tracks_from_grid(grid, pat_len, bank)
                block = seq.render_pattern(pat_len, pat_bpm, tracks, apply_limiter=False)
                audio_blocks.append(block)

            progress.setLabelText("Writing file(s)...")
            progress.setValue(total_patterns)
            QApplication.processEvents()

            audio = np.concatenate(audio_blocks, axis=0)

            # Project-wide normalization (identical to play_sequence)
            max_val = np.max(np.abs(audio))
            if max_val > 0.98:
                audio = audio * (0.98 / max_val)

            baker = WaveBaker(export_dir=settings["directory"])
            exported = baker.multi_export(
                settings["filename"], audio,
                settings["format"], settings["qualities"]
            )

            progress.setValue(total_patterns + 1)
            progress.close()

            file_list = "\n".join(f"• {os.path.basename(f)}" for f in exported)
            self.statusBar().showMessage(f"Exported {len(exported)} file(s)")
            QMessageBox.information(self, "Export Complete",
                f"Tracker audio exported!\n\n{file_list}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export: {str(e)}")

    def export_sfx_audio(self):
        """Renders the SFX Painter canvas and exports via ExportDialog."""
        dlg = ExportDialog(self, title="Export SFX", default_name="sfx_export")
        if dlg.exec() != ExportDialog.DialogCode.Accepted:
            return
        
        settings = dlg.get_export_settings()
        
        try:
            import numpy as np
            audio = self.visual_canvas.render_sfx_to_array()
            if audio is None or len(audio) == 0:
                QMessageBox.warning(self, "No SFX Data", "Paint some sounds on the SFX canvas first!")
                return
            
            # Convert mono to stereo for compatibility
            if audio.ndim == 1:
                audio = np.column_stack([audio, audio])
            
            baker = WaveBaker(export_dir=settings["directory"])
            exported = baker.multi_export(
                settings["filename"], audio,
                settings["format"], settings["qualities"]
            )
            
            file_list = "\n".join(f"• {os.path.basename(f)}" for f in exported)
            self.statusBar().showMessage(f"Exported {len(exported)} SFX file(s)")
            QMessageBox.information(self, "SFX Export Complete",
                f"SFX audio exported!\n\n{file_list}")
        except Exception as e:
            QMessageBox.critical(self, "SFX Export Error", f"Failed to export SFX: {str(e)}")

    def init_ui(self):
        self.active_tracker_cell = None
        
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Application Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs)

        # --- 1. Tab 1: Instrument Lab (Sound Design) ---
        self.workbench_container = WorkbenchWidget()
        self.tabs.addTab(self.workbench_container, "Instrument Lab")
        
        # --- 2. Tab 2: Master Tracker (Composition) ---
        self.tracker_container = TrackerWidget()
        self.tabs.addTab(self.tracker_container, "Master Tracker")
        
        # --- 3. Tab 3: SFX Painter (Audio Foley) ---
        self.visual_canvas = SfxCanvas()
        self.tabs.addTab(self.visual_canvas, "SFX Painter")
        
        # Set 'Master Tracker' as the default active tab
        self.tabs.setCurrentIndex(1)

        # Connect time signature controls to tracker beat highlighting
        self.spin_lpb.valueChanged.connect(
            lambda val: self.tracker_container.refresh_beat_highlighting(val, self.spin_lpm.value()))
        self.spin_lpm.valueChanged.connect(
            lambda val: self.tracker_container.refresh_beat_highlighting(self.spin_lpb.value(), val))
        
        # Apply initial highlighting now that tracker is parented
        self.tracker_container.refresh_beat_highlighting()

        # Mark project dirty when tracker cells are edited
        self.tracker_container.table.cellChanged.connect(self._mark_dirty)
        # Update status bar context when switching tabs
        self.tabs.currentChanged.connect(lambda _: self._update_status_context())

        # Add Bottom Status Bar
        self._update_status_context()

    # ==========================================================
    #           SFX SAVE / LOAD  (LANTHORN_SFX format)
    # ==========================================================

    def save_sfx_project(self):
        """Save the SFX Painter canvas to a .sfx.csv file."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save SFX Canvas", "", "SFX Files (*.sfx.csv);;All Files (*)")
        if not filename:
            return
        if not filename.endswith('.sfx.csv'):
            filename += '.sfx.csv'

        try:
            state = self.visual_canvas.get_state()
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["LANTHORN_SFX", "1.0"])
                writer.writerow(["STATE", json.dumps(state)])
            self._current_sfx_path = filename
            self.statusBar().showMessage(f"SFX saved: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "SFX Save Error", str(e))

    def load_sfx_project(self):
        """Load an SFX Painter canvas from a .sfx.csv file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load SFX Canvas", "", "SFX Files (*.sfx.csv);;CSV Files (*.csv);;All Files (*)")
        if not filename:
            return

        try:
            import csv
            with open(filename, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)

            if not rows or rows[0][0] != "LANTHORN_SFX":
                QMessageBox.warning(self, "Wrong File Type",
                    "This file does not have a LANTHORN_SFX header.\n"
                    "It may be a tracker project — use Load Project instead.")
                return

            state_json = rows[1][1] if len(rows) > 1 and len(rows[1]) > 1 else "{}"
            state = json.loads(state_json)
            self.visual_canvas.set_state(state)
            self._current_sfx_path = filename
            self.statusBar().showMessage(f"SFX loaded: {filename}")
            self.tabs.setCurrentIndex(2)  # Jump to SFX tab
        except Exception as e:
            QMessageBox.critical(self, "SFX Load Error", str(e))

    # ==========================================================
    #           HELP / SETTINGS DIALOGS
    # ==========================================================

    def show_help_dialog(self):
        """Shows contextual help based on the active tab."""
        dlg = QDialog(self)
        dlg.setMinimumSize(620, 580)
        dlg.setStyleSheet("QDialog { background: #1e1e1e; color: #ddd; }")
        layout = QVBoxLayout(dlg)

        text = QTextBrowser()
        text.setOpenExternalLinks(False)
        text.setStyleSheet(
            "QTextBrowser { background: #252526; color: #ccc; border: 1px solid #3f3f46;"
            " font-family: 'Courier New', monospace; font-size: 12px; padding: 10px; }")

        tab_idx = self.tabs.currentIndex()
        tab_names = {0: "Instrument Lab", 1: "Master Tracker", 2: "SFX Painter"}
        tab_name = tab_names.get(tab_idx, "General")
        dlg.setWindowTitle(f"Help \u2014 {tab_name}")

        # --- Global shortcuts (always shown) ---
        html = (
            "<h2 style='color:#55aaff;'>\u2328 Global Shortcuts</h2>"
            "<table cellpadding='4'>"
            "<tr><td style='color:#00ff88; width:100px;'>Ctrl+N</td><td>New Project</td></tr>"
            "<tr><td style='color:#00ff88;'>Ctrl+O</td><td>Open Project (.csv)</td></tr>"
            "<tr><td style='color:#00ff88;'>Ctrl+S</td><td>Quick Save</td></tr>"
            "<tr><td style='color:#00ff88;'>Ctrl+Q</td><td>Quit</td></tr>"
            "<tr><td style='color:#00ff88;'>Space</td><td>Play / Pause (toggle)</td></tr>"
            "<tr><td style='color:#00ff88;'>Shift+Space</td><td>Play from Cursor (selected row)</td></tr>"
            "<tr><td style='color:#00ff88;'>F1</td><td>This Help Dialog (contextual per tab)</td></tr>"
            "</table>"
            "<hr style='border: 1px solid #3f3f46;'>"
        )

        if tab_idx == 0:
            html += (
                "<h2 style='color:#ffaa00;'>\U0001f3b9 Instrument Lab</h2>"
                "<p style='color:#aaa;'>Design and manage instrument presets.</p>"
                "<h3 style='color:#55aaff;'>Oscillator Section</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ffaa;'>OSC 1 buttons</td><td>Primary waveform: Sine, Square, Sawtooth, Triangle, Noise</td></tr>"
                "<tr><td style='color:#00ffaa;'>OSC 2 buttons</td><td>Secondary waveform (dual oscillator)</td></tr>"
                "<tr><td style='color:#00ffaa;'>Mix slider</td><td>Blend ratio between OSC 1 and OSC 2</td></tr>"
                "<tr><td style='color:#00ffaa;'>Duty Cycle</td><td>Pulse width for square wave (0.0-1.0)</td></tr>"
                "</table>"
                "<h3 style='color:#55aaff;'>Envelope (ADSR)</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ffaa;'>Attack</td><td>Time to reach full volume</td></tr>"
                "<tr><td style='color:#00ffaa;'>Decay</td><td>Time to fall to sustain level</td></tr>"
                "<tr><td style='color:#00ffaa;'>Sustain</td><td>Volume during held note (0.0-1.0)</td></tr>"
                "<tr><td style='color:#00ffaa;'>Release</td><td>Fade out time after note ends</td></tr>"
                "</table>"
                "<h3 style='color:#55aaff;'>Modulation Rack</h3>"
                "<p>Click <b style='color:#00ff88;'>+ Add Element</b> to add modifiers:</p>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ffaa;'>Vibrato</td><td>Pitch wobble (speed + depth)</td></tr>"
                "<tr><td style='color:#00ffaa;'>Tremolo</td><td>Volume pulsing</td></tr>"
                "<tr><td style='color:#00ffaa;'>Saturation</td><td>Warm distortion</td></tr>"
                "<tr><td style='color:#00ffaa;'>Bit Crush</td><td>Lo-fi (16=clean, 8=NES, 4=extreme)</td></tr>"
                "<tr><td style='color:#00ffaa;'>Echo</td><td>Delay + feedback</td></tr>"
                "<tr><td style='color:#00ffaa;'>Ring Mod</td><td>Metallic/bell tones</td></tr>"
                "<tr><td style='color:#00ffaa;'>Pitch Slide</td><td>Pitch bend over time</td></tr>"
                "<tr><td style='color:#00ffaa;'>Retrigger</td><td>Stutter gate effect</td></tr>"
                "<tr><td style='color:#00ffaa;'>Portamento</td><td>Glide between notes</td></tr>"
                "</table>"
                "<p>\u2699\ufe0f to edit, X to remove. Preview plays with all active FX.</p>"
                "<h3 style='color:#55aaff;'>Instrument Bank</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ffaa;'>+ New</td><td>Save current knobs as new preset</td></tr>"
                "<tr><td style='color:#00ffaa;'>\U0001f4c1 Folder</td><td>Create category subfolder</td></tr>"
                "<tr><td style='color:#00ffaa;'>\u2191 Store</td><td>Overwrite selected preset</td></tr>"
                "<tr><td style='color:#00ffaa;'>\u2193 Recall</td><td>Load preset into knobs</td></tr>"
                "<tr><td style='color:#00ffaa;'>\u2715 Delete</td><td>Remove from bank and disk</td></tr>"
                "</table>"
                "<p><b>Right-click</b> tree for: Duplicate, Save to Disk, New Folder.</p>"
            )

        elif tab_idx == 1:
            html += (
                "<h2 style='color:#ffaa00;'>\U0001f3bc Master Tracker</h2>"
                "<p style='color:#aaa;'>Compose music using the step sequencer.</p>"
                "<h3 style='color:#55aaff;'>Grid Navigation</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ff88; width:140px;'>Arrow Keys</td><td>Move cursor</td></tr>"
                "<tr><td style='color:#00ff88;'>Shift+Click</td><td>Select range</td></tr>"
                "<tr><td style='color:#00ff88;'>Ctrl+Click</td><td>Multi-select</td></tr>"
                "<tr><td style='color:#00ff88;'>Delete / Backspace</td><td>Clear cells to defaults</td></tr>"
                "<tr><td style='color:#00ff88;'>Ctrl+Z / Ctrl+Y</td><td>Undo / Redo</td></tr>"
                "<tr><td style='color:#00ff88;'>Ctrl+L</td><td>Loop selection (clone N times)</td></tr>"
                "<tr><td style='color:#00ff88;'>Enter (on FX)</td><td>FX Interpolation Sweep</td></tr>"
                "</table>"
                "<h3 style='color:#55aaff;'>Column Types (per track)</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ff00; width:60px;'>Note</td><td>C-4, G#5, OFF, or chords: C-4,E-4,G-4</td></tr>"
                "<tr><td style='color:#ffaa00;'>Inst</td><td>Instrument name from bank</td></tr>"
                "<tr><td style='color:#d4d4d4;'>Vel</td><td>Velocity 0-127 (decimal)</td></tr>"
                "<tr><td style='color:#d4d4d4;'>Gate</td><td>Gate length in steps (decimal)</td></tr>"
                "<tr><td style='color:#55aaff;'>FX1/FX2</td><td>FX command: VIB 3A, SUP 40, PAN 80</td></tr>"
                "</table>"
                "<h3 style='color:#55aaff;'>Toolbar Buttons</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ffaa;'>+ New</td><td>Create new empty pattern</td></tr>"
                "<tr><td style='color:#00ffaa;'>\u29c9 Clone</td><td>Duplicate current pattern</td></tr>"
                "<tr><td style='color:#00ffaa;'>\u2715 Del</td><td>Delete current pattern</td></tr>"
                "<tr><td style='color:#00ffaa;'>Steps spinner</td><td>Set step count (8-128)</td></tr>"
                "<tr><td style='color:#00ffaa;'>+ / - tracks</td><td>Add or remove tracks (1-16)</td></tr>"
                "<tr><td style='color:#00ffaa;'>\u25b6 Pat</td><td>Play current pattern only</td></tr>"
                "<tr><td style='color:#00ffaa;'>\u25b6 Solo</td><td>Solo the selected track</td></tr>"
                "<tr><td style='color:#00ffaa;'>+ Seq / - Seq</td><td>Add/remove from order list</td></tr>"
                "<tr><td style='color:#00ffaa;'>SeqEdit</td><td>Open Sequence Editor dialog</td></tr>"
                "</table>"
                "<h3 style='color:#55aaff;'>Right-Click Context Menu</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#ffaa00; width:80px;'>Note</td><td>Notes, OFF, Chords (Maj, Min, 7th, Sus, Dim, Aug)</td></tr>"
                "<tr><td style='color:#ffaa00;'>Inst</td><td>\U0001f3b9 Patches \u2192 browse by folder (\U0001f4c1 bass, drums, keys...)</td></tr>"
                "<tr><td style='color:#ffaa00;'>Vel</td><td>Presets: pp, p, mf, f, ff, Max</td></tr>"
                "<tr><td style='color:#ffaa00;'>Gate</td><td>Presets: 1, 2, 4, 8, 16 steps</td></tr>"
                "<tr><td style='color:#ffaa00;'>FX</td><td>Categorized FX + custom dial</td></tr>"
                "<tr><td style='color:#ffaa00;'>Any</td><td>\u25b6 Play, \U0001f4cb Copy/Paste, \U0001f9e0 Smart Edit, \U0001f5d1 Clear</td></tr>"
                "</table>"
                "<h3 style='color:#55aaff;'>\U0001f9e0 Smart Edit</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ffaa;'>\U0001f517 Edit Similar</td>"
                "<td>Batch change Vel/Gate/FX on all rows with same patch</td></tr>"
                "<tr><td style='color:#00ffaa;'>\U0001f3af Select Similar</td>"
                "<td>Highlight all rows with same instrument</td></tr>"
                "<tr><td style='color:#00ffaa;'>\U0001f504 Fill Pattern</td>"
                "<td>Tile selected block through entire pattern</td></tr>"
                "<tr><td style='color:#00ffaa;'>\U0001f4d0 Repeat Selection</td>"
                "<td>Extend row selection pattern (e.g. every 4th row)</td></tr>"
                "</table>"
                "<h3 style='color:#55aaff;'>Sequence Editor</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ffaa;'>Add / Insert</td><td>Append or insert pattern entry</td></tr>"
                "<tr><td style='color:#00ffaa;'>Duplicate</td><td>Copy sequence entry</td></tr>"
                "<tr><td style='color:#00ffaa;'>Remove</td><td>Delete entry (keep \u2265 1)</td></tr>"
                "<tr><td style='color:#00ffaa;'>\u25b2 Up / \u25bc Down</td><td>Reorder entries</td></tr>"
                "<tr><td style='color:#00ffaa;'>Apply</td><td>Commit new order</td></tr>"
                "</table>"
            )

        elif tab_idx == 2:
            html += (
                "<h2 style='color:#ffaa00;'>\U0001f3a8 SFX Painter</h2>"
                "<p style='color:#aaa;'>Draw sound effects on a 3-layer piano roll.</p>"
                "<h3 style='color:#55aaff;'>Canvas Tools</h3>"
                "<table cellpadding='3'>"
                "<tr><td style='color:#00ffaa; width:80px;'>Paint</td><td>Click/drag to draw notes</td></tr>"
                "<tr><td style='color:#00ffaa;'>Erase</td><td>Remove notes by clicking</td></tr>"
                "<tr><td style='color:#00ffaa;'>Line</td><td>Draw straight line between points</td></tr>"
                "<tr><td style='color:#00ffaa;'>Curve</td><td>Draw smooth curve</td></tr>"
                "</table>"
                "<h3 style='color:#55aaff;'>Layers</h3>"
                "<p>3 independent layers for layering elements.<br>"
                "Each layer can have different waveforms.</p>"
                "<h3 style='color:#55aaff;'>File</h3>"
                "<p>Save/Load via File menu using <code>.sfx.csv</code> format.<br>"
                "Independent from tracker projects.</p>"
            )

        html += (
            "<hr style='border: 1px solid #3f3f46;'>"
            "<h3 style='color:#55aaff;'>FX Quick Reference</h3>"
            "<table cellpadding='2' style='font-size:11px;'>"
            "<tr><td style='color:#55aaff;'>ARP</td><td>Arpeggio</td>"
            "<td style='color:#55aaff;'>SUP</td><td>Slide Up</td>"
            "<td style='color:#55aaff;'>SDN</td><td>Slide Down</td></tr>"
            "<tr><td style='color:#55aaff;'>PRT</td><td>Portamento</td>"
            "<td style='color:#55aaff;'>VIB</td><td>Vibrato</td>"
            "<td style='color:#55aaff;'>TRM</td><td>Tremolo</td></tr>"
            "<tr><td style='color:#55aaff;'>VOL</td><td>Volume</td>"
            "<td style='color:#55aaff;'>ECH</td><td>Echo</td>"
            "<td style='color:#55aaff;'>CUT</td><td>Note Cut</td></tr>"
            "<tr><td style='color:#55aaff;'>PAN</td><td>Pan</td>"
            "<td style='color:#55aaff;'>RNG</td><td>Ring Mod</td>"
            "<td style='color:#55aaff;'>RTG</td><td>Retrigger</td></tr>"
            "</table>"
        )

        text.setHtml(html)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("background: #333; color: #ccc; padding: 6px 20px;")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.exec()


    def show_settings_dialog(self):
        """Shows a simple settings dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setFixedSize(400, 200)
        dlg.setStyleSheet("""
            QDialog { background: #1e1e1e; color: #ddd; }
            QLabel { color: #aaa; }
            QLineEdit, QDoubleSpinBox { background: #2d2d30; color: #ccc;
                border: 1px solid #3f3f46; padding: 4px; }
        """)
        layout = QFormLayout(dlg)

        # A4 Tuning
        tuning_spin = QDoubleSpinBox()
        tuning_spin.setRange(400.0, 480.0)
        tuning_spin.setDecimals(1)
        tuning_spin.setSuffix(" Hz")
        tuning_spin.setValue(getattr(self, '_a4_tuning', 440.0))
        layout.addRow("A4 Tuning:", tuning_spin)

        # Default Export Directory
        export_dir = QLineEdit(
            getattr(self, '_default_export_dir',
                    os.path.expanduser("~/Documents/Lanthorn Exports")))
        layout.addRow("Export Directory:", export_dir)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._a4_tuning = tuning_spin.value()
            self._default_export_dir = export_dir.text()
            # Write tuning back into the engine constants so it takes effect
            import engine.constants as _ec
            _ec.ROOT_A4_FREQ = self._a4_tuning
            self.statusBar().showMessage(
                f"Settings updated — A4={self._a4_tuning}Hz, Export: {self._default_export_dir}")

    def _mark_dirty(self, *_args):
        """Called on any tracker cell edit to flag unsaved changes."""
        self._unsaved_changes = True
        self._update_status_context()

    def closeEvent(self, event):
        """Prompt to save before closing if there are unsaved changes."""
        if self._unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before exiting?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                self.save_project()
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def _update_status_context(self):
        """Show the current project or SFX name in the status bar."""
        idx = self.tabs.currentIndex()
        parts = []
        if self._current_project_path:
            name = os.path.basename(self._current_project_path)
            parts.append(f"Project: {name}")
        else:
            parts.append("Project: (untitled)")
        if idx == 2 and self._current_sfx_path:
            sfx_name = os.path.basename(self._current_sfx_path)
            parts.append(f"SFX: {sfx_name}")
        if self._unsaved_changes:
            parts.append("[modified]")
        self.statusBar().showMessage(" | ".join(parts))
