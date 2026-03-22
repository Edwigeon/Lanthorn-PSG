import pyqtgraph as pg
import numpy as np
import sounddevice as sd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QSlider, QGroupBox, QPushButton, QButtonGroup,
    QComboBox, QDialog, QTreeWidget, QTreeWidgetItem,
    QDoubleSpinBox, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

from engine.oscillator import Oscillator
from engine.modifiers import Modifiers
from .fx_ui_manager import FXPopupWindow

# ==========================================
# 1. THE FLOATING MODULATION WINDOW (ADSR)
# ==========================================
class EnvelopeWindow(QDialog):
    def __init__(self, workbench, parent=None):
        super().__init__(parent)
        self.workbench = workbench
        self.setWindowTitle("ADSR Envelope")
        self.setWindowFlags(Qt.WindowType.Tool) 
        self.resize(300, 250)
        self.setStyleSheet("background-color: #252526; color: #cccccc;")

        layout = QVBoxLayout(self)

        self.env_plot_widget = pg.PlotWidget()
        self.env_plot_widget.setFixedHeight(80)
        self.env_plot_widget.setBackground('#151515')
        self.env_plot_widget.setYRange(0, 1.1)
        self.env_plot_widget.hideAxis('bottom')
        self.env_plot_widget.hideAxis('left')
        self.env_plot_widget.setMouseEnabled(x=False, y=False)
        self.env_plot_data = self.env_plot_widget.plot(pen=pg.mkPen('#FF00FF', width=2))
        layout.addWidget(self.env_plot_widget)

        slider_layout = QHBoxLayout()
        self.slider_a = self.create_v_slider("A", slider_layout, workbench.env_data["attack"])
        self.slider_d = self.create_v_slider("D", slider_layout, workbench.env_data["decay"])
        self.slider_s = self.create_v_slider("S", slider_layout, workbench.env_data["sustain"])
        self.slider_r = self.create_v_slider("R", slider_layout, workbench.env_data["release"])
        layout.addLayout(slider_layout)

        self.update_display()

    def create_v_slider(self, label_text, parent_layout, initial_val):
        vbox = QVBoxLayout()
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        slider = QSlider(Qt.Orientation.Vertical)
        slider.setRange(0, 100)
        slider.setValue(int(initial_val * 100))
        
        spinbox = QDoubleSpinBox()
        spinbox.setRange(0.0, 1.0)
        spinbox.setSingleStep(0.01)
        spinbox.setValue(initial_val)
        
        # Cross-connect
        slider.valueChanged.connect(lambda val: spinbox.setValue(val / 100.0))
        spinbox.valueChanged.connect(lambda val, l=label_text: self.on_slider_move(l, val, slider))
        
        vbox.addWidget(label)
        vbox.addWidget(spinbox)
        vbox.addWidget(slider)
        parent_layout.addLayout(vbox)
        return slider

    def on_slider_move(self, param, float_val, slider_ref):
        slider_ref.blockSignals(True)
        slider_ref.setValue(int(float_val * 100))
        slider_ref.blockSignals(False)
        
        if param == "A": self.workbench.env_data["attack"] = float_val
        elif param == "D": self.workbench.env_data["decay"] = float_val
        elif param == "S": self.workbench.env_data["sustain"] = float_val
        elif param == "R": self.workbench.env_data["release"] = float_val
        
        self.update_display()

    def update_display(self):
        a = self.workbench.env_data["attack"]
        d = self.workbench.env_data["decay"]
        s = self.workbench.env_data["sustain"]
        r = self.workbench.env_data["release"]
        
        x_coords = [0, a, a + d, a + d + 0.5, a + d + 0.5 + r]
        y_coords = [0, 1.0, s, s, 0]
        
        self.env_plot_widget.setXRange(0, 3.5)
        self.env_plot_data.setData(x_coords, y_coords)

class GenericModWindow(QDialog):
    def __init__(self, title, workbench, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Tool)
        self.resize(300, 200)
        self.setStyleSheet("background-color: #252526; color: #cccccc;")
        
        layout = QVBoxLayout(self)
        
        self.title = title
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setFixedHeight(80)
        self.plot_widget.setBackground('#151515')
        self.plot_widget.hideAxis('bottom')
        self.plot_widget.hideAxis('left')
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_data = self.plot_widget.plot(pen=pg.mkPen('#00FFFF', width=2))
        layout.addWidget(self.plot_widget)
        
        slider_layout = QHBoxLayout()
        self.depth_val = 0.5
        self.rate_val = 0.5
        
        self.create_v_slider("Depth", slider_layout, self.depth_val, is_depth=True)
        self.create_v_slider("Rate", slider_layout, self.rate_val, is_depth=False)
        layout.addLayout(slider_layout)
        
        self.update_display()

    def create_v_slider(self, label_text, parent_layout, initial_val, is_depth):
        vbox = QVBoxLayout()
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        slider = QSlider(Qt.Orientation.Vertical)
        slider.setRange(0, 100)
        slider.setValue(int(initial_val * 100))
        
        spinbox = QDoubleSpinBox()
        spinbox.setRange(0.0, 1.0)
        spinbox.setSingleStep(0.01)
        spinbox.setValue(initial_val)
        
        slider.valueChanged.connect(lambda val: spinbox.setValue(val / 100.0))
        spinbox.valueChanged.connect(lambda val, d=is_depth, s=slider: self.on_slider_move(d, val, s))
        
        vbox.addWidget(label)
        vbox.addWidget(spinbox)
        vbox.addWidget(slider)
        parent_layout.addLayout(vbox)
        return slider

    def on_slider_move(self, is_depth, float_val, slider_ref):
        slider_ref.blockSignals(True)
        slider_ref.setValue(int(float_val * 100))
        slider_ref.blockSignals(False)
        if is_depth:
            self.depth_val = float_val
        else:
            self.rate_val = float_val
        self.update_display()

    def update_display(self):
        import math
        x = np.linspace(0, 4*math.pi, 200)
        if "LFO" in self.title:
            freq = 1.0 + (self.rate_val * 5.0)
            y = np.sin(x * freq) * self.depth_val
        elif "LoFi" in self.title:
            steps = 2 + int(self.depth_val * 14) # 2 to 16 bits
            y = np.round(np.sin(x) * steps) / steps
        elif "Echo" in self.title:
            # Fake decay visualization
            y = np.exp(-x * (1.0 - self.rate_val + 0.1)) * np.sin(10 * x) * self.depth_val
        elif "Pitch" in self.title:
            # Slide up or down based on rate_val
            direction = 1.0 if self.rate_val >= 0.5 else -1.0
            sweep = x / x[-1] * self.depth_val * direction
            y = np.sin(x + sweep * 2 * math.pi)
        elif "Retrigger" in self.title:
            # Square wave gate visualization
            gate_freq = 1.0 + self.depth_val * 8.0
            gate = (np.sign(np.sin(x * gate_freq)) + 1) / 2
            y = np.sin(x * 3) * gate
        elif "Portamento" in self.title:
            # Slide between two frequencies
            slide_point = int(self.depth_val * len(x))
            freq1, freq2 = 1.0, 2.0
            freqs = np.ones(len(x)) * freq1
            if slide_point > 0 and slide_point < len(x):
                freqs[:slide_point] = np.linspace(freq1, freq2, slide_point)
            freqs[slide_point:] = freq2
            y = np.sin(x * freqs) * 0.8
        elif "Saturation" in self.title:
            drive = 1.0 + self.depth_val * 10.0
            y = np.tanh(np.sin(x) * drive) / (np.tanh(drive) + 1e-9)
        elif "Detune" in self.title:
            cents = self.depth_val * 50.0
            ratio = 2.0 ** (cents / 1200.0)
            y = np.sin(x) * 0.5 + np.sin(x * ratio) * 0.5
        elif "Delay" in self.title:
            shift = int(self.depth_val * len(x) * 0.5)
            y = np.zeros_like(x)
            if shift < len(x):
                y[shift:] = np.sin(x[:len(x) - shift]) * 0.8
        else:
            y = np.sin(x) * self.depth_val
            
        self.plot_data.setData(x, y)

# ==========================================
# 2. THE MAIN WORKBENCH
# ==========================================
class WorkbenchWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.osc = Oscillator(44100)
        self.mod = Modifiers(44100)
        
        self.env_data = {"attack": 0.05, "decay": 0.2, "sustain": 0.5, "release": 0.3}
        self.active_windows = {}
        self.active_category = None  # Tracks which test was last used for context-aware saving

        self.init_ui()
        self.update_oscilloscope()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # --- 1. MAIN OSCILLOSCOPE ---
        self.plot_widget = pg.PlotWidget(title="Core Waveform (0.01s)")
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.setYRange(-1.1, 1.1)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.hideAxis('bottom')
        self.plot_data = self.plot_widget.plot(pen=pg.mkPen('#00FFFF', width=2))
        layout.addWidget(self.plot_widget, stretch=1)

        # --- 2. CORE OSCILLATORS (Permanent UI) ---
        osc_group = QGroupBox("Core Oscillators")
        osc_group.setStyleSheet("color: #cccccc;")
        osc_main_layout = QVBoxLayout()
        
        # Osc 1 Row
        osc1_layout = QHBoxLayout()
        osc1_label = QLabel("Osc 1:")
        osc1_label.setFixedWidth(40)
        osc1_layout.addWidget(osc1_label)
        
        self.wave1_btn_group = QButtonGroup(self)
        self.wave1_btn_group.setExclusive(True)
        wave1_types = ["sine", "square", "triangle", "sawtooth", "noise"]
        for idx, w_type in enumerate(wave1_types):
            btn = QPushButton(w_type.capitalize())
            btn.setCheckable(True)
            if w_type == "square": btn.setChecked(True)
            self.wave1_btn_group.addButton(btn, id=idx)
            osc1_layout.addWidget(btn)
        self.wave1_btn_group.buttonClicked.connect(self.update_oscilloscope)
        
        # Osc 2 Row
        osc2_layout = QHBoxLayout()
        osc2_label = QLabel("Osc 2:")
        osc2_label.setFixedWidth(40)
        osc2_layout.addWidget(osc2_label)
        
        self.wave2_btn_group = QButtonGroup(self)
        self.wave2_btn_group.setExclusive(True)
        wave2_types = ["off", "sine", "square", "triangle", "sawtooth", "noise"]
        for idx, w_type in enumerate(wave2_types):
            btn = QPushButton(w_type.capitalize())
            btn.setCheckable(True)
            if w_type == "off": btn.setChecked(True)
            self.wave2_btn_group.addButton(btn, id=idx)
            osc2_layout.addWidget(btn)
        self.wave2_btn_group.buttonClicked.connect(self.update_oscilloscope)
        
        # Mix Slider Row
        mix_layout = QHBoxLayout()
        mix_label = QLabel("Mix:")
        mix_label.setFixedWidth(40)
        self.slider_mix = QSlider(Qt.Orientation.Horizontal)
        self.slider_mix.setRange(0, 100)
        self.slider_mix.setValue(0)
        self.slider_mix.valueChanged.connect(self.update_oscilloscope)
        mix_layout.addWidget(mix_label)
        mix_layout.addWidget(self.slider_mix)

        osc_main_layout.addLayout(osc1_layout)
        osc_main_layout.addLayout(osc2_layout)
        osc_main_layout.addLayout(mix_layout)
        osc_group.setLayout(osc_main_layout)

        # --- 3. DYNAMIC MODULATION RACK ---
        rack_group = QGroupBox("Modulation Rack")
        rack_group.setStyleSheet("color: #cccccc;")
        self.rack_layout = QVBoxLayout()

        # "Edit FX Chain..." button opens the unified FX Editor
        edit_chain_btn = QPushButton("🎛️ Edit FX Chain...")
        edit_chain_btn.setToolTip("Open the FX Editor to build and edit your effect chain")
        edit_chain_btn.setStyleSheet(
            "background-color: #264f78; color: #55aaff; font-weight: bold; padding: 6px;")
        edit_chain_btn.clicked.connect(lambda: self._open_rack_fx_editor())
        self.rack_layout.addWidget(edit_chain_btn)

        self.active_mods_layout = QVBoxLayout()
        self.rack_layout.addLayout(self.active_mods_layout)
        self.rack_layout.addStretch()

        rack_group.setLayout(self.rack_layout)

        # FX chain storage: list of fx_string items (e.g. ["VIB 68", "SAT 40"])
        self._rack_fx_chain = []

        # Reverse lookup: FX code → human-readable name
        from .fx_ui_manager import FX_CATALOG
        self.FX_CODE_TO_NAME = {code: info["name"] for code, info in FX_CATALOG.items()}

        # --- 4. INSTRUMENT BANK ---
        bank_group = QGroupBox("Instrument Bank")
        bank_group.setStyleSheet("color: #cccccc;")
        bank_layout = QVBoxLayout()
        
        self.bank_tree = QTreeWidget()
        self.bank_tree.setHeaderHidden(True)
        self.bank_tree.setStyleSheet(
            "QTreeWidget { background-color: #1e1e1e; color: #00FFFF; "
            "font-family: 'Courier New', monospace; border: none; }"
            "QTreeWidget::item:selected { background-color: #264f78; }"
            "QTreeWidget::branch { background-color: #1e1e1e; }"
        )
        self.bank_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bank_tree.customContextMenuRequested.connect(self._show_bank_context_menu)
        self.bank_tree.itemDoubleClicked.connect(lambda item, col: self.load_instrument())
        
        self.bank_data = {}  # key = "folder/name" or just "name", value = patch dict
        
        # Load Existing Presets (with folder support)
        from engine.preset_manager import PresetManager
        import os
        self.preset_mgr = PresetManager()
        all_presets = self.preset_mgr.list_all()
        
        for folder, preset_names in all_presets.items():
            for preset_name in preset_names:
                patch_data = self.preset_mgr.load_instrument(preset_name, folder=folder)
                if folder:
                    key = f"{folder}/{preset_name}"
                else:
                    key = preset_name
                display_name = patch_data.get("name", preset_name)
                self.bank_data[key] = {"patch": patch_data, "display": display_name, "folder": folder}
                    
        if len(self.bank_data) == 0:
            self.bank_data["INIT"] = {"patch": self.get_patch(), "display": "INIT", "folder": None}
        
        self._populate_bank_tree()
        bank_layout.addWidget(self.bank_tree)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("+ New")
        add_btn.setToolTip("Create a new blank instrument")
        add_btn.setStyleSheet("background-color: #3f3f46;")
        add_btn.clicked.connect(lambda _: self.add_instrument())

        folder_btn = QPushButton("📁 Folder")
        folder_btn.setToolTip("Create a new category folder")
        folder_btn.setStyleSheet("background-color: #3f3f46;")
        folder_btn.clicked.connect(lambda _: self.add_folder())

        save_btn = QPushButton("↑ Store")
        save_btn.setToolTip("Store current knob settings into the selected instrument")
        save_btn.setStyleSheet("background-color: #3f3f46;")
        save_btn.clicked.connect(lambda _: self.save_instrument())

        save_as_btn = QPushButton("↑ Save As")
        save_as_btn.setToolTip("Save current settings as a new instrument with a new name")
        save_as_btn.setStyleSheet("background-color: #3f3f46;")
        save_as_btn.clicked.connect(lambda _: self.save_instrument_as())

        load_btn = QPushButton("↓ Recall")
        load_btn.setToolTip("Recall the selected instrument's settings into the knobs")
        load_btn.setStyleSheet("background-color: #3f3f46;")
        load_btn.clicked.connect(lambda _: self.load_instrument())

        del_btn = QPushButton("✕ Delete")
        del_btn.setToolTip("Delete the selected instrument from the bank")
        del_btn.setStyleSheet("background-color: #552222; color: #ffaaaa;")
        del_btn.clicked.connect(lambda _: self.delete_instrument())

        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(folder_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(save_as_btn)
        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(del_btn)
        bank_layout.addLayout(btn_layout)
        bank_group.setLayout(bank_layout)

        # Assemble lower layout horizontally
        lower_layout = QHBoxLayout()
        lower_layout.addWidget(rack_group, stretch=1)
        lower_layout.addWidget(osc_group, stretch=1)
        lower_layout.addWidget(bank_group, stretch=1)
        
        layout.addLayout(lower_layout, stretch=2)

        # --- 5. CONTEXTUAL TEST BUTTONS ---
        test_group = QGroupBox("Test Patch")
        test_group.setStyleSheet("color: #cccccc;")
        test_layout = QHBoxLayout()

        test_categories = [
            ("🎸 Bass",  "bass"),
            ("🎹 Lead",  "leads"),
            ("🌊 Pad",   "pads"),
            ("🎶 Arp",   "keys"),
            ("🥁 Drums", "drums"),
            ("⚡ SFX",   "sfx"),
        ]
        for label, cat in test_categories:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "background-color: #333; color: #ccc; padding: 4px 8px; font-size: 11px;")
            btn.setToolTip(f"Play a {cat}-style test phrase")
            btn.clicked.connect(lambda checked, c=cat: self.play_test(c))
            test_layout.addWidget(btn)

        test_group.setLayout(test_layout)
        layout.addWidget(test_group)

    def _populate_bank_tree(self):
        """Populates the QTreeWidget from bank_data, grouping by folder."""
        self.bank_tree.clear()
        folders = {}  # folder_name -> QTreeWidgetItem
        root_items = []
        
        for key, entry in sorted(self.bank_data.items()):
            display = entry["display"]
            folder = entry.get("folder")
            
            item = QTreeWidgetItem()
            item.setText(0, display)
            item.setData(0, Qt.ItemDataRole.UserRole, key)  # Store the lookup key
            
            if folder:
                if folder not in folders:
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, f"📁 {folder}")
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, f"__folder__:{folder}")
                    font = folder_item.font(0)
                    font.setBold(True)
                    folder_item.setFont(0, font)
                    folders[folder] = folder_item
                folders[folder].addChild(item)
            else:
                root_items.append(item)
        
        # Add folders first (sorted), then root items
        for folder_name in sorted(folders.keys()):
            self.bank_tree.addTopLevelItem(folders[folder_name])
            folders[folder_name].setExpanded(True)
        for item in root_items:
            self.bank_tree.addTopLevelItem(item)
        
        if self.bank_tree.topLevelItemCount() > 0:
            self.bank_tree.setCurrentItem(self.bank_tree.topLevelItem(0))

    def _get_selected_key(self):
        """Returns the bank_data key for the currently selected preset, or None."""
        item = self.bank_tree.currentItem()
        if not item:
            return None
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key and key.startswith("__folder__:"):
            return None  # It's a folder, not a preset
        return key

    def _get_selected_folder(self):
        """Returns the folder name for the current selection context."""
        item = self.bank_tree.currentItem()
        if not item:
            return None
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key and key.startswith("__folder__:"):
            return key.replace("__folder__:", "")
        # If it's a child of a folder, get parent folder
        parent = item.parent()
        if parent:
            pkey = parent.data(0, Qt.ItemDataRole.UserRole)
            if pkey and pkey.startswith("__folder__:"):
                return pkey.replace("__folder__:", "")
        return None

    def _open_rack_fx_editor(self):
        """Opens the unified FX Editor pre-loaded with the current rack chain."""
        initial = " : ".join(self._rack_fx_chain) if self._rack_fx_chain else ""

        def _on_apply(fx_string):
            self._apply_fx_chain(fx_string)

        def _on_preview(fx_string):
            self._fx_preview_handler(fx_string)

        popup = FXPopupWindow(
            parent=self, on_apply=_on_apply, on_preview=_on_preview,
            initial_value=initial)

        # Pre-populate the stack list from current chain
        if self._rack_fx_chain:
            popup.stack_list.clear()
            for item in self._rack_fx_chain:
                popup.stack_list.addItem(item)
            popup._update_preview()

        popup.exec()

    def _edit_rack_item(self, index):
        """Opens the FX Editor to edit a single existing item in the chain."""
        if index < 0 or index >= len(self._rack_fx_chain):
            return
        fx_item = self._rack_fx_chain[index]

        def _on_apply(fx_string):
            # Replace just this one item (take only the first FX if user stacked)
            items = [s.strip() for s in fx_string.split(":") if s.strip() and s.strip() != "--"]
            if items:
                self._rack_fx_chain[index] = items[0]
            self._rebuild_rack_display()
            self.update_oscilloscope()
            # Sync ENV if needed
            code = items[0].split()[0] if items else ""
            if code == "ENV":
                self._sync_fx_to_generic("__env__", items[0])

        def _on_preview(fx_string):
            self._fx_preview_handler(fx_string)

        popup = FXPopupWindow(
            parent=self, on_apply=_on_apply, on_preview=_on_preview,
            initial_value=fx_item)

        # Clear the stack — we're editing a single item, not building a chain
        popup.stack_list.clear()
        popup._update_preview()

        popup.exec()

    def _apply_fx_chain(self, fx_string):
        """Applies the FX Editor result to the rack chain and rebuilds the display."""
        if fx_string and fx_string != "--":
            self._rack_fx_chain = [item.strip() for item in fx_string.split(":") if item.strip()]
        else:
            self._rack_fx_chain = []

        # Sync each effect to backward-compat data (env_data, active_windows etc.)
        for fx_item in self._rack_fx_chain:
            parts = fx_item.strip().split()
            if len(parts) >= 2:
                code = parts[0]
                # Sync ENV to env_data
                if code == "ENV":
                    self._sync_fx_to_generic("__env__", fx_item)
                else:
                    self._sync_fx_to_generic(code, fx_item)

        self._rebuild_rack_display()
        self.update_oscilloscope()

    def _rebuild_rack_display(self):
        """Rebuilds the visual rack items from `_rack_fx_chain`."""
        # Clear existing items
        while self.active_mods_layout.count():
            child = self.active_mods_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self._rack_fx_chain:
            empty_label = QLabel("  No effects — click Edit FX Chain to add")
            empty_label.setStyleSheet("color: #555; font-style: italic; padding: 4px;")
            self.active_mods_layout.addWidget(empty_label)
            return

        for i, fx_item in enumerate(self._rack_fx_chain):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 1, 2, 1)

            # Readable label: "VIB 68" → "🌊 Vibrato  (68)"
            label_text = self._fx_label_for_code(fx_item)
            item_btn = QPushButton(label_text)
            item_btn.setStyleSheet(
                "text-align: left; padding: 4px 8px; background-color: #2d2d30;"
                "color: #55aaff; border: 1px solid #3f3f46; border-radius: 3px;")
            item_btn.setToolTip(f"Click to edit  •  {fx_item}")
            item_btn.clicked.connect(lambda checked=False, ix=i: self._edit_rack_item(ix))

            remove_btn = QPushButton("✕")
            remove_btn.setFixedWidth(26)
            remove_btn.setStyleSheet(
                "background-color: #5a2020; color: #ff6666; font-weight: bold;"
                "border: 1px solid #733; border-radius: 3px;")
            idx = i  # capture index
            remove_btn.clicked.connect(lambda checked=False, ix=idx: self._remove_rack_item(ix))

            row_layout.addWidget(item_btn, stretch=1)
            row_layout.addWidget(remove_btn)
            self.active_mods_layout.addWidget(row)

    def _remove_rack_item(self, index):
        """Removes a single item from the FX chain by index."""
        if 0 <= index < len(self._rack_fx_chain):
            self._rack_fx_chain.pop(index)
            self._rebuild_rack_display()
            self.update_oscilloscope()

    def _fx_label_for_code(self, fx_item):
        """Converts 'VIB 68' → '🌊 Vibrato  (68)' for display."""
        parts = fx_item.strip().split(None, 1)
        code = parts[0] if parts else "?"
        param = parts[1] if len(parts) > 1 else ""
        name = self.FX_CODE_TO_NAME.get(code, code)
        # Grab the category emoji from the catalog
        from .fx_ui_manager import FX_CATALOG
        info = FX_CATALOG.get(code, {})
        cat = info.get("category", "")
        emoji = cat.split(" ")[0] if cat else "⚙️"
        return f"{emoji} {name}  ({param})" if param else f"{emoji} {name}"

    def get_patch(self):
        active_btn1 = self.wave1_btn_group.checkedId()
        wave1_types = ["sine", "square", "triangle", "sawtooth", "noise"]
        w1 = wave1_types[active_btn1] if active_btn1 >= 0 else "square"
        
        active_btn2 = self.wave2_btn_group.checkedId()
        wave2_types = ["off", "sine", "square", "triangle", "sawtooth", "noise"]
        w2 = wave2_types[active_btn2] if active_btn2 >= 0 else "off"
        
        patch = {
            "wave_type": w1,
            "mix": self.slider_mix.value() / 100.0,
            "envelope": {
                "attack": self.env_data["attack"],
                "decay": self.env_data["decay"],
                "sustain_level": self.env_data["sustain"],
                "release": self.env_data["release"]
            }
        }
        
        if w2 != "off":
            patch["wave_type_2"] = w2
        
        # --- Serialize the FX chain from the rack ---
        if self._rack_fx_chain:
            patch["fx_chain"] = list(self._rack_fx_chain)

        return patch

    def update_oscilloscope(self):
        patch = self.get_patch()
        duration = 0.01
        from engine.constants import ROOT_A4_FREQ
        freq = ROOT_A4_FREQ
        
        raw_wave = self.osc.generate(patch["wave_type"], freq, duration)
        
        wave_2 = patch.get("wave_type_2")
        mix_ratio = patch.get("mix", 0.0)
        
        if wave_2 and wave_2 != "off" and mix_ratio > 0.0:
            w2 = self.osc.generate(wave_2, freq, duration)
            raw_wave = ((1.0 - mix_ratio) * raw_wave) + (mix_ratio * w2)
        
        x_axis = np.linspace(0, duration, len(raw_wave))
        self.plot_data.setData(x_axis, raw_wave)
        
    def load_patch(self, patch_data):
        """Fully populates all Workbench controls from a patch dictionary."""
        self.slider_mix.blockSignals(True)
        
        # --- 1. Wave Selectors ---
        w1_type = patch_data.get("wave_type", "square").lower()
        for btn in self.wave1_btn_group.buttons():
            if btn.text().lower() == w1_type:
                btn.setChecked(True)
                
        w2_type = patch_data.get("wave_type_2", "off").lower()
        for btn in self.wave2_btn_group.buttons():
            if btn.text().lower() == w2_type:
                btn.setChecked(True)
                
        self.slider_mix.setValue(int(patch_data.get("mix", 0.0) * 100))
        self.slider_mix.blockSignals(False)
        
        # --- 2. ADSR Envelope ---
        env = patch_data.get("envelope", patch_data)
        self.env_data["attack"] = env.get("attack", 0.05)
        self.env_data["decay"] = env.get("decay", 0.2)
        self.env_data["sustain"] = env.get("sustain_level", env.get("sustain", 0.5))
        self.env_data["release"] = env.get("release", 0.3)
        
        # --- 3. FX Chain: load from patch and rebuild rack ---
        fx_chain = patch_data.get("fx_chain", [])
        if fx_chain and isinstance(fx_chain, list):
            self._rack_fx_chain = list(fx_chain)
        else:
            # Backward compat: convert legacy fields to fx_chain items
            self._rack_fx_chain = []
            self._migrate_legacy_fx(patch_data)

        # Sync ENV items back to env_data
        for fx_item in self._rack_fx_chain:
            parts = fx_item.strip().split()
            if len(parts) >= 2 and parts[0] == "ENV":
                self._sync_fx_to_generic("__env__", fx_item)

        self._rebuild_rack_display()
        self.update_oscilloscope()

    def _set_generic_mod_sliders(self, win):
        """Helper to sync a GenericModWindow's internal values to its sliders."""
        from PyQt6.QtWidgets import QSlider
        sliders = win.findChildren(QSlider)
        if len(sliders) >= 1:
            sliders[0].blockSignals(True)
            sliders[0].setValue(int(win.depth_val * 100))
            sliders[0].blockSignals(False)
        if len(sliders) >= 2:
            sliders[1].blockSignals(True)
            sliders[1].setValue(int(win.rate_val * 100))
            sliders[1].blockSignals(False)
        if hasattr(win, 'update_display'):
            win.update_display()

    def _sync_fx_to_generic(self, mod_type, fx_string):
        """Syncs FX string data back to legacy stores (e.g. env_data for ADSR)."""
        parts = fx_string.strip().split()
        if len(parts) < 2:
            return
        code = parts[0]

        # ADSR envelope: "ENV 5.20.50.30"
        if code == "ENV":
            adsr_parts = parts[1].split(".")
            if len(adsr_parts) >= 4:
                try:
                    self.env_data["attack"] = int(adsr_parts[0]) / 100.0
                    self.env_data["decay"] = int(adsr_parts[1]) / 100.0
                    self.env_data["sustain"] = int(adsr_parts[2]) / 100.0
                    self.env_data["release"] = int(adsr_parts[3]) / 100.0
                except ValueError:
                    pass

    def _migrate_legacy_fx(self, patch_data):
        """Converts legacy preset fields into _rack_fx_chain items.
        Called when loading a patch that has no 'fx_chain' key."""
        chain = self._rack_fx_chain  # already []

        # ADSR from envelope sub-dict
        env = patch_data.get("envelope", {})
        if env and isinstance(env, dict):
            a = int(env.get("attack", 0.05) * 100)
            d = int(env.get("decay", 0.2) * 100)
            s = int(env.get("sustain_level", env.get("sustain", 0.5)) * 100)
            r = int(env.get("release", 0.3) * 100)
            chain.append(f"ENV {a}.{d}.{s}.{r}")

        # LFO → VIB / TRM
        lfo = patch_data.get("lfo", {})
        if lfo and isinstance(lfo, dict):
            vib_speed = lfo.get("vibrato_speed", 0.0)
            vib_depth = lfo.get("vibrato_depth", 0.0)
            if vib_depth > 0:
                p1 = min(15, max(0, int((vib_speed - 1.0) / 1.0)))
                p2 = min(15, max(0, int(vib_depth * 15)))
                chain.append(f"VIB {(p1 << 4) | p2}")

            trm_speed = lfo.get("tremolo_speed", 0.0)
            trm_depth = lfo.get("tremolo_depth", 0.0)
            if trm_depth > 0:
                p1 = min(15, max(0, int((trm_speed - 1.0) / 1.0)))
                p2 = min(15, max(0, int(trm_depth * 15)))
                chain.append(f"TRM {(p1 << 4) | p2}")

        # Saturation
        sat = patch_data.get("saturation", 0.0)
        if sat and sat > 1.0:
            p = min(255, max(0, int((sat - 1.0) / 4.0 * 255)))
            chain.append(f"SAT {p}")

        # Echo
        echo = patch_data.get("echo", {})
        if echo and isinstance(echo, dict):
            delay = echo.get("delay_time", 0.15)
            fb = echo.get("feedback", 0.4)
            p1 = min(15, max(0, int((delay - 0.01) / 0.05)))
            p2 = min(15, max(0, int(fb * 15)))
            chain.append(f"ECH {(p1 << 4) | p2}")

        # Ring Mod
        ring = patch_data.get("ring_mod", {})
        if ring and isinstance(ring, dict):
            mix = ring.get("mix", 0.5)
            p = min(255, max(0, int(mix * 255)))
            chain.append(f"RNG {p}")

        # Portamento
        port = patch_data.get("portamento", {})
        if port and isinstance(port, dict):
            slide = port.get("slide_time", 0.1)
            p = min(255, max(0, int(slide / 0.5 * 255)))
            chain.append(f"PRT {p}")

        # Detune
        detune = patch_data.get("detune", 0.0)
        if detune and detune > 0:
            p = min(255, max(0, int(detune / 50.0 * 255)))
            chain.append(f"DTN {p}")

        # Delay start
        dly = patch_data.get("delay_start", 0.0)
        if dly and dly > 0:
            p = min(255, max(0, int(dly * 255)))
            chain.append(f"DLY {p}")

        # Retrigger
        retrig = patch_data.get("retrigger", {})
        if retrig and isinstance(retrig, dict):
            hz = retrig.get("rate_hz", 1.0)
            p = min(255, max(0, int((hz - 1.0) / 31.0 * 255)))
            chain.append(f"RTG {p}")

        # Pitch slide
        pslide = patch_data.get("pitch_slide", {})
        if pslide and isinstance(pslide, dict):
            semi = pslide.get("semitones", 0.0)
            direction = pslide.get("direction", "up")
            p = min(255, max(0, int(semi / 12.0 * 255)))
            code = "SUP" if direction == "up" else "SDN"
            chain.append(f"{code} {p}")

        # Bit depth (LoFi)
        bit_depth = patch_data.get("bit_depth", 0)
        if bit_depth and bit_depth > 0 and bit_depth < 16:
            p = min(255, max(0, int((bit_depth - 2) / 14.0 * 255)))
            chain.append(f"CUT {p}")

    def _fx_preview_handler(self, fx_string):
        """Plays the active test pattern with the current patch to preview an FX.
        Resolves the instrument folder to pick the right test melody."""
        # 1. Try the currently selected instrument's folder
        cat = self._get_selected_folder()
        # 2. Fall back to active_category (last used test button)
        if not cat:
            cat = self.active_category
        # 3. Default
        if not cat:
            cat = "leads"
        melody = self.TEST_PATTERNS.get(cat, self.TEST_PATTERNS["leads"])
        self._play_melody(melody)

    def _show_bank_context_menu(self, pos):
        """Show the instrument bank right-click context menu."""
        from .context_menu import BankContextMenu
        BankContextMenu.show(self.bank_tree, self.bank_tree.mapToGlobal(pos), self)

    def add_folder(self):
        """Creates a new category folder in the preset directory."""
        text, ok = QInputDialog.getText(self, "New Folder", "Folder Name:")
        if ok and text:
            self.preset_mgr.create_folder(text)
            self._populate_bank_tree()

    def add_instrument(self):
        """Creates a new blank instrument, saving into the currently selected folder."""
        text, ok = QInputDialog.getText(self, "New Instrument", "Instrument Name:")
        if ok and text:
            folder = self._get_selected_folder()
            key = f"{folder}/{text}" if folder else text
            if key not in self.bank_data:
                # Blank default patch — NOT the current UI state
                patch = {
                    "wave_type": "square",
                    "mix": 0.0,
                    "envelope": {
                        "attack": 5, "decay": 20,
                        "sustain_level": 50, "release": 30
                    }
                }
                self.bank_data[key] = {"patch": patch, "display": text, "folder": folder}
                # Context-aware: use active_category if no folder selected
                save_folder = folder or self.active_category
                if save_folder:
                    key = f"{save_folder}/{text}"
                    self.bank_data[key] = {"patch": patch, "display": text, "folder": save_folder}
                # Save to disk
                safe_name = "".join([c for c in text if c.isalpha() or c.isdigit() or c=='_']).rstrip()
                self.preset_mgr.save_instrument(safe_name, patch, folder=save_folder)
                self._populate_bank_tree()

    def save_instrument_as(self):
        """Saves the current patch as a new instrument with a new name."""
        text, ok = QInputDialog.getText(self, "Save As", "New Instrument Name:")
        if ok and text:
            folder = self._get_selected_folder() or self.active_category
            patch = self.get_patch()
            key = f"{folder}/{text}" if folder else text
            self.bank_data[key] = {"patch": patch, "display": text, "folder": folder}
            safe_name = "".join([c for c in text if c.isalpha() or c.isdigit() or c=='_']).rstrip()
            self.preset_mgr.save_instrument(safe_name, patch, folder=folder)
            self._populate_bank_tree()
                
    def save_instrument(self):
        key = self._get_selected_key()
        if key and key in self.bank_data:
            entry = self.bank_data[key]
            patch = self.get_patch()
            entry["patch"] = patch
            # Save to disk
            folder = entry.get("folder")
            name = key.split("/")[-1] if "/" in key else key
            safe_name = "".join([c for c in name if c.isalpha() or c.isdigit() or c=='_']).rstrip()
            self.preset_mgr.save_instrument(safe_name, patch, folder=folder)
            
    def load_instrument(self):
        key = self._get_selected_key()
        if key and key in self.bank_data:
            patch = self.bank_data[key]["patch"]
            if patch:
                self.load_patch(patch)

    def delete_instrument(self):
        key = self._get_selected_key()
        if key and key in self.bank_data:
            entry = self.bank_data[key]
            display = entry.get("display", key)
            reply = QMessageBox.question(self, "Delete Instrument",
                f"Delete '{display}' from the bank?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                name = key.split("/")[-1] if "/" in key else key
                folder = entry.get("folder")
                safe_name = "".join([c for c in name if c.isalpha() or c.isdigit() or c=='_']).rstrip()
                self.preset_mgr.delete_instrument(safe_name, folder=folder)
                del self.bank_data[key]
                self._populate_bank_tree()
    def _open_fx_editor(self):
        """Opens the unified FX popup for experimentation (no cell target)."""
        def _on_apply(fx_string):
            print(f"[FX Editor] Output: {fx_string}")
        popup = FXPopupWindow(parent=self, on_apply=_on_apply)
        popup.exec()

    # ---- Contextual Test Patterns ----
    # Each category has its own note array and timing to showcase the patch
    # in a musically appropriate context.

    TEST_PATTERNS = {
        "bass": [
            # Deep, rhythmic bass line — mostly C2/E2/G2
            (36, 0.25), (36, 0.15), (None, 0.10),
            (40, 0.20), (43, 0.20), (36, 0.40),
            (None, 0.05), (36, 0.10), (38, 0.10),
            (40, 0.30), (43, 0.25), (36, 0.50),
        ],
        "leads": [
            # Melodic lead — C4 to C5 range
            (60, 0.12), (64, 0.12), (67, 0.12), (72, 0.40),
            (71, 0.10), (69, 0.10), (67, 0.30),
            (64, 0.15), (60, 0.15), (67, 0.50),
        ],
        "pads": [
            # Chord + melody mix: shows both texture and detail
            ([60, 64, 67], 0.90),       # C major chord
            (72, 0.30),                 # C5 melody note
            (71, 0.30),                 # B4
            (None, 0.10),
            ([57, 60, 64], 0.90),       # A minor chord
            (69, 0.30),                 # A4 melody note
            (67, 0.30),                 # G4
            (None, 0.10),
            ([53, 57, 60], 0.90),       # F major chord
            (65, 0.30),                 # F4 melody note
            (64, 0.30),                 # E4
            (None, 0.10),
            ([55, 59, 62], 0.90),       # G major chord
            (67, 0.40),                 # G4 resolving note
        ],
        "keys": [
            # Fast arp-style run — even staccato
            (60, 0.08), (64, 0.08), (67, 0.08), (72, 0.08),
            (76, 0.08), (72, 0.08), (67, 0.08), (64, 0.08),
            (60, 0.08), (64, 0.08), (67, 0.08), (72, 0.08),
            (76, 0.12), (79, 0.12), (84, 0.20),
        ],
        "drums": [
            # Percussive hits — short, spaced, varied pitch
            (36, 0.06), (None, 0.14),
            (42, 0.04), (None, 0.06),
            (42, 0.04), (None, 0.06),
            (38, 0.06), (None, 0.14),
            (42, 0.04), (None, 0.06),
            (36, 0.06), (36, 0.06), (None, 0.04),
            (38, 0.08), (None, 0.12),
        ],
        "sfx": [
            # SFX showcase — wide range sweeps, varied timing
            (72, 0.15), (84, 0.10), (96, 0.08),
            (None, 0.10),
            (48, 0.30), (36, 0.20),
            (None, 0.15),
            (60, 0.05), (72, 0.05), (84, 0.05), (96, 0.05),
            (None, 0.10),
            (36, 0.60),
        ],
    }

    def play_test(self, category):
        """Plays a category-appropriate test phrase and sets active_category."""
        self.active_category = category
        melody = self.TEST_PATTERNS.get(category, self.TEST_PATTERNS["leads"])
        self._play_melody(melody)

    def play_preview(self):
        """Plays a short melody showcasing the patch with all active FX."""
        # Default preview uses the lead test pattern
        self._play_melody(self.TEST_PATTERNS["leads"])

    def _play_melody(self, melody):
        """Synthesizes and plays a list of (midi_note_or_None, duration) tuples."""
        import numpy as np
        patch = self.get_patch()
        sr = 44100
        env = patch.get("envelope", {})
        att = env.get("attack", 0.05)
        dec = env.get("decay", 0.2)
        sus = env.get("sustain", env.get("sustain_level", 0.5))
        rel = env.get("release", 0.3)
        wave_2 = patch.get("wave_type_2")
        mix_r = patch.get("mix", 0.0)

        gap = 0.02
        segments = []
        prev_freq = None

        for entry in melody:
            # Support chords: entry can be ([midi, midi, ...], dur) or (midi, dur) or (None, dur)
            if isinstance(entry[0], list):
                midi_notes, dur = entry
            else:
                midi_note, dur = entry
                midi_notes = [midi_note] if midi_note is not None else None

            if midi_notes is None:
                # Rest
                segments.append(np.zeros(int(sr * dur)))
                continue

            # Generate and sum all notes in the chord
            chord_wave = np.zeros(int(sr * dur))
            for midi_note in midi_notes:

                from engine.constants import ROOT_A4_FREQ
                freq = ROOT_A4_FREQ * (2.0 ** ((midi_note - 69) / 12.0))
                note = self.osc.generate(patch["wave_type"], freq, dur)
                if wave_2 and wave_2 != "off" and mix_r > 0.0:
                    w2 = self.osc.generate(wave_2, freq, dur)
                    note = ((1.0 - mix_r) * note) + (mix_r * w2)

                note = self.mod.apply_adsr(
                    note, attack=min(att, dur * 0.3),
                    decay=min(dec, dur * 0.3),
                    sustain_level=sus, release=min(rel, dur * 0.4))

                # Ensure same length
                target_len = len(chord_wave)
                if len(note) > target_len:
                    note = note[:target_len]
                elif len(note) < target_len:
                    note = np.pad(note, (0, target_len - len(note)))

                chord_wave += note

            # Normalize chord so it doesn't clip
            if len(midi_notes) > 1:
                peak = np.max(np.abs(chord_wave))
                if peak > 0.95:
                    chord_wave *= 0.95 / peak

            note = chord_wave
            freq = ROOT_A4_FREQ * (2.0 ** ((midi_notes[0] - 69) / 12.0))  # Use root for FX

            # Apply Pitch Slide
            pitch_slide = patch.get("pitch_slide")
            if pitch_slide:
                semis = pitch_slide.get("semitones", 0)
                if pitch_slide.get("direction") == "up":
                    end_freq = freq * (2.0 ** (semis / 12.0))
                else:
                    end_freq = freq / (2.0 ** (semis / 12.0))
                freq_profile = self.mod.generate_slide_profile(
                    freq, end_freq, dur, dur * 0.8)
                t = np.linspace(0, dur, len(note), endpoint=False)
                phase = np.cumsum(freq_profile / sr) * 2 * np.pi
                note_slid = np.sin(phase)
                if len(note) > 0 and np.max(np.abs(note)) > 0:
                    env_shape = note / (np.max(np.abs(note)) + 1e-9)
                    note = note_slid * np.abs(env_shape)

            # Apply Portamento
            porta = patch.get("portamento", {})
            slide_time = porta.get("slide_time", 0.0)
            if prev_freq and slide_time > 0 and prev_freq != freq:
                slide_samples = min(int(sr * slide_time), len(note))
                if slide_samples > 0:
                    slide_freqs = np.linspace(prev_freq, freq, slide_samples)
                    phase = np.cumsum(slide_freqs / sr) * 2 * np.pi
                    slide_part = np.sin(phase) * note[:slide_samples]
                    note[:slide_samples] = slide_part

            # Apply LoFi / Bitcrush
            if "bit_depth" in patch:
                note = self.mod.apply_bitcrush(note, patch["bit_depth"])
            if "saturation" in patch:
                note = self.mod.apply_saturation(note, patch["saturation"])

            # Apply Tremolo
            lfo = patch.get("lfo", {})
            trem_speed = lfo.get("tremolo_speed", 0)
            trem_depth = lfo.get("tremolo_depth", 0)
            if trem_speed > 0 and trem_depth > 0:
                note = self.mod.apply_tremolo(note, trem_speed, trem_depth)

            # Apply Vibrato
            vib_speed = lfo.get("vibrato_speed", 0)
            vib_depth = lfo.get("vibrato_depth", 0)
            if vib_speed > 0 and vib_depth > 0:
                t = np.linspace(0, dur, len(note), endpoint=False)
                lfo_wave = np.sin(2 * np.pi * vib_speed * t)
                note = note * (1.0 + vib_depth * 0.1 * lfo_wave)

            # Apply Ring Mod
            ring = patch.get("ring_mod")
            if ring:
                note = self.mod.apply_ring_mod(
                    note, ring.get("carrier_freq", 500.0), ring.get("mix", 0.5))

            # Apply Echo
            echo = patch.get("echo")
            if echo:
                note = self.mod.apply_echo(
                    note, echo.get("delay_time", 0.15), echo.get("feedback", 0.4))

            # Apply Retrigger
            retrig = patch.get("retrigger")
            if retrig:
                note = self.mod.apply_retrigger(note, retrig.get("rate_hz", 16.0))

            # Apply standalone Saturation
            sat_gain = patch.get("saturation")
            if sat_gain and sat_gain > 1.0 and "bit_depth" not in patch:
                note = self.mod.apply_saturation(note, sat_gain)

            # Apply Detune
            detune_cents = patch.get("detune", 0.0)
            if detune_cents > 0.01:
                ratio = 2.0 ** (detune_cents / 1200.0)
                indices = np.clip(
                    (np.arange(len(note)) * ratio).astype(int),
                    0, len(note) - 1)
                note = note[indices]

            # Apply Delay Start
            delay_frac = patch.get("delay_start", 0.0)
            if delay_frac > 0.01:
                delay_samples = int(delay_frac * len(note) * 0.5)
                if 0 < delay_samples < len(note):
                    shifted = np.zeros(len(note))
                    shifted[delay_samples:] = note[:len(note) - delay_samples]
                    note = shifted

            segments.append(note)
            segments.append(np.zeros(int(sr * gap)))
            prev_freq = freq

        full = np.concatenate(segments)
        full = full / (np.max(np.abs(full)) + 1e-9) * 0.7

        try:
            sd.stop()
            sd.play(full.astype(np.float32), samplerate=sr)
        except Exception as e:
            print("Audio Playback Error:", e)
