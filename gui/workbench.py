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
        
        add_layout = QHBoxLayout()
        self.mod_selector = QComboBox()
        self.mod_selector.addItems([
            "ADSR Envelope", "LFO Vibrato", "LFO Tremolo",
            "Pitch Slide", "LoFi (Bitcrush)", "RingMod",
            "Echo Delay", "Retrigger", "Portamento",
            "Saturation", "Detune", "Delay"
        ])
        
        add_btn = QPushButton("+ Add Element")
        add_btn.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        add_btn.clicked.connect(lambda _: self.add_modulator())
        
        add_layout.addWidget(self.mod_selector)
        add_layout.addWidget(add_btn)
        self.rack_layout.addLayout(add_layout)
        
        self.active_mods_layout = QVBoxLayout()
        self.rack_layout.addLayout(self.active_mods_layout)
        self.rack_layout.addStretch()

        rack_group.setLayout(self.rack_layout)

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
        add_btn.setToolTip("Create a new instrument from current settings")
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

    def add_modulator(self, mod_type=None, show_window=True):
        if mod_type is None:
            mod_type = self.mod_selector.currentText()
        if mod_type in self.active_windows:
            return

        mod_container = QWidget()
        mod_layout = QHBoxLayout(mod_container)
        mod_layout.setContentsMargins(0, 0, 0, 0)
        
        open_btn = QPushButton(f"⚙️ {mod_type}")
        open_btn.setStyleSheet("text-align: left; padding: 5px;")
        open_btn.clicked.connect(lambda: self.open_mod_window(mod_type))
        
        remove_btn = QPushButton("X")
        remove_btn.setFixedWidth(30)
        remove_btn.setStyleSheet("background-color: #A52A2A;")
        remove_btn.clicked.connect(lambda: self.remove_modulator(mod_type, mod_container))
        
        mod_layout.addWidget(open_btn)
        mod_layout.addWidget(remove_btn)
        
        self.active_mods_layout.addWidget(mod_container)
        self.active_windows[mod_type] = {"container": mod_container, "window": None}
        if show_window:
            self.open_mod_window(mod_type)

    def remove_modulator(self, mod_type, container_widget):
        if self.active_windows[mod_type]["window"]:
            self.active_windows[mod_type]["window"].close()
        container_widget.deleteLater()
        del self.active_windows[mod_type]

    def open_mod_window(self, mod_type):
        if self.active_windows[mod_type]["window"]:
            self.active_windows[mod_type]["window"].show()
            self.active_windows[mod_type]["window"].raise_()
            return
            
        if mod_type == "ADSR Envelope":
            win = EnvelopeWindow(workbench=self)
            self.active_windows[mod_type]["window"] = win
            win.show()
            
        elif mod_type in ["LFO Vibrato", "LFO Tremolo", "LoFi (Bitcrush)",
                          "RingMod", "Echo Delay", "Pitch Slide",
                          "Retrigger", "Portamento",
                          "Saturation", "Detune", "Delay"]:
            win = GenericModWindow(mod_type, workbench=self)
            self.active_windows[mod_type]["window"] = win
            win.show()

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
        
        # --- Serialize active modulation rack parameters ---
        lfo_data = {}
        
        if "LFO Vibrato" in self.active_windows:
            win = self.active_windows["LFO Vibrato"].get("window")
            if win:
                lfo_data["vibrato_speed"] = 1.0 + (win.rate_val * 5.0)
                lfo_data["vibrato_depth"] = win.depth_val
        
        if "LoFi (Bitcrush)" in self.active_windows:
            win = self.active_windows["LoFi (Bitcrush)"].get("window")
            if win:
                patch["bit_depth"] = 2 + int(win.depth_val * 14)  # 2 to 16 bits
                patch["saturation"] = 1.0 + (win.rate_val * 4.0)  # Rate controls saturation gain
        
        if "RingMod" in self.active_windows:
            win = self.active_windows["RingMod"].get("window")
            if win:
                patch["ring_mod"] = {
                    "carrier_freq": 100.0 + (win.rate_val * 900.0),  # 100-1000 Hz
                    "mix": win.depth_val
                }
        
        if "Echo Delay" in self.active_windows:
            win = self.active_windows["Echo Delay"].get("window")
            if win:
                patch["echo"] = {
                    "delay_time": 0.05 + (win.rate_val * 0.45),  # 50ms to 500ms
                    "feedback": win.depth_val
                }

        if "LFO Tremolo" in self.active_windows:
            win = self.active_windows["LFO Tremolo"].get("window")
            if win:
                lfo_data["tremolo_speed"] = 1.0 + (win.rate_val * 15.0)  # 1-16 Hz
                lfo_data["tremolo_depth"] = win.depth_val

        if "Pitch Slide" in self.active_windows:
            win = self.active_windows["Pitch Slide"].get("window")
            if win:
                patch["pitch_slide"] = {
                    "semitones": win.depth_val * 12.0,  # 0-12 semitones
                    "direction": "up" if win.rate_val >= 0.5 else "down"
                }

        if "Retrigger" in self.active_windows:
            win = self.active_windows["Retrigger"].get("window")
            if win:
                patch["retrigger"] = {
                    "rate_hz": 1.0 + (win.depth_val * 31.0)  # 1-32 Hz
                }

        if "Portamento" in self.active_windows:
            win = self.active_windows["Portamento"].get("window")
            if win:
                patch["portamento"] = {
                    "slide_time": win.depth_val * 0.5  # 0-0.5s
                }

        if "Saturation" in self.active_windows:
            win = self.active_windows["Saturation"].get("window")
            if win:
                patch["saturation"] = 1.0 + (win.depth_val * 4.0)  # 1.0-5.0 gain

        if "Detune" in self.active_windows:
            win = self.active_windows["Detune"].get("window")
            if win:
                patch["detune"] = win.depth_val * 50.0  # 0-50 cents

        if "Delay" in self.active_windows:
            win = self.active_windows["Delay"].get("window")
            if win:
                patch["delay_start"] = win.depth_val  # 0.0-1.0 fraction
        
        if lfo_data:
            patch["lfo"] = lfo_data
            
        return patch

    def update_oscilloscope(self):
        patch = self.get_patch()
        duration = 0.01
        freq = 440.0 
        
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
        
        if "ADSR Envelope" in self.active_windows and self.active_windows["ADSR Envelope"]["window"]:
            win = self.active_windows["ADSR Envelope"]["window"]
            win.slider_a.blockSignals(True)
            win.slider_d.blockSignals(True)
            win.slider_s.blockSignals(True)
            win.slider_r.blockSignals(True)
            
            win.slider_a.setValue(int(self.env_data["attack"] * 100))
            win.slider_d.setValue(int(self.env_data["decay"] * 100))
            win.slider_s.setValue(int(self.env_data["sustain"] * 100))
            win.slider_r.setValue(int(self.env_data["release"] * 100))
            
            win.slider_a.blockSignals(False)
            win.slider_d.blockSignals(False)
            win.slider_s.blockSignals(False)
            win.slider_r.blockSignals(False)
            win.update_display()
        
        # --- 3. Modulation Rack: Auto-add/remove/update modules ---
        lfo_data = patch_data.get("lfo", {})
        echo_data = patch_data.get("echo", {})
        ring_data = patch_data.get("ring_mod", {})
        has_bitcrush = "bit_depth" in patch_data or "saturation" in patch_data
        
        # Mapping: mod_type → (check_condition, setup_function)
        mod_map = {
            "LFO Vibrato": bool(lfo_data),
            "LoFi (Bitcrush)": has_bitcrush,
            "RingMod": bool(ring_data),
            "Echo Delay": bool(echo_data),
            "Saturation": "saturation" in patch_data and not has_bitcrush,
            "Detune": "detune" in patch_data,
            "Delay": "delay_start" in patch_data,
        }
        
        for mod_type, should_exist in mod_map.items():
            currently_exists = mod_type in self.active_windows
            
            if should_exist and not currently_exists:
                # Add the module to the rack
                self.add_modulator(mod_type, show_window=False)
            elif not should_exist and currently_exists:
                # Remove the module from the rack
                container = self.active_windows[mod_type].get("container")
                if container:
                    self.remove_modulator(mod_type, container)
        
        # Now set parameter values on existing mod windows
        if "LFO Vibrato" in self.active_windows:
            win = self.active_windows["LFO Vibrato"].get("window")
            if win and lfo_data:
                # Reverse the math: vibrato_speed = 1.0 + (rate_val * 5.0)
                speed = lfo_data.get("vibrato_speed", 1.0)
                win.rate_val = max(0.0, min(1.0, (speed - 1.0) / 5.0))
                win.depth_val = lfo_data.get("vibrato_depth", 0.5)
                self._set_generic_mod_sliders(win)
        
        if "LoFi (Bitcrush)" in self.active_windows:
            win = self.active_windows["LoFi (Bitcrush)"].get("window")
            if win:
                # Reverse: bit_depth = 2 + int(depth_val * 14)
                bit_depth = patch_data.get("bit_depth", 16)
                win.depth_val = max(0.0, min(1.0, (bit_depth - 2) / 14.0))
                # Reverse: saturation = 1.0 + (rate_val * 4.0)
                sat = patch_data.get("saturation", 1.0)
                win.rate_val = max(0.0, min(1.0, (sat - 1.0) / 4.0))
                self._set_generic_mod_sliders(win)
        
        if "RingMod" in self.active_windows:
            win = self.active_windows["RingMod"].get("window")
            if win and ring_data:
                # Reverse: carrier_freq = 100.0 + (rate_val * 900.0)
                freq = ring_data.get("carrier_freq", 500.0)
                win.rate_val = max(0.0, min(1.0, (freq - 100.0) / 900.0))
                win.depth_val = ring_data.get("mix", 0.5)
                self._set_generic_mod_sliders(win)
        
        if "Echo Delay" in self.active_windows:
            win = self.active_windows["Echo Delay"].get("window")
            if win and echo_data:
                # Reverse: delay_time = 0.05 + (rate_val * 0.45)
                delay = echo_data.get("delay_time", 0.15)
                win.rate_val = max(0.0, min(1.0, (delay - 0.05) / 0.45))
                win.depth_val = echo_data.get("feedback", 0.4)
                self._set_generic_mod_sliders(win)

        if "Saturation" in self.active_windows:
            win = self.active_windows["Saturation"].get("window")
            if win:
                sat = patch_data.get("saturation", 1.0)
                win.depth_val = max(0.0, min(1.0, (sat - 1.0) / 4.0))
                self._set_generic_mod_sliders(win)

        if "Detune" in self.active_windows:
            win = self.active_windows["Detune"].get("window")
            if win:
                cents = patch_data.get("detune", 0.0)
                win.depth_val = max(0.0, min(1.0, cents / 50.0))
                self._set_generic_mod_sliders(win)

        if "Delay" in self.active_windows:
            win = self.active_windows["Delay"].get("window")
            if win:
                win.depth_val = patch_data.get("delay_start", 0.0)
                self._set_generic_mod_sliders(win)
            
        self.update_oscilloscope()

    def _set_generic_mod_sliders(self, win):
        """Helper to sync a GenericModWindow's internal values to its sliders."""
        # The GenericModWindow creates sliders in create_v_slider but doesn't store them
        # as named attributes. We can trigger an update via the window's display.
        if hasattr(win, 'update_display'):
            win.update_display()

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
        """Creates a new instrument, saving into the currently selected folder."""
        text, ok = QInputDialog.getText(self, "New Instrument", "Instrument Name:")
        if ok and text:
            folder = self._get_selected_folder()
            key = f"{folder}/{text}" if folder else text
            if key not in self.bank_data:
                patch = self.get_patch()
                self.bank_data[key] = {"patch": patch, "display": text, "folder": folder}
                # Save to disk
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
    def play_preview(self):
        """Plays a short melody showcasing the patch with all active FX."""
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

        # Melody: (MIDI note, duration in seconds)
        melody = [
            (60, 0.12),   # C4  staccato
            (64, 0.12),   # E4  staccato
            (67, 0.12),   # G4  staccato
            (69, 0.45),   # A4  sustained
            (67, 0.10),   # G4  staccato
            (64, 0.10),   # E4  staccato
            (72, 0.60),   # C5  long sustained
            (74, 0.08),   # D5  quick grace
            (72, 0.40),   # C5  ending sustain
        ]
        gap = 0.02  # tiny silence between notes

        segments = []
        prev_freq = None
        for midi_note, dur in melody:
            freq = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
            note = self.osc.generate(patch["wave_type"], freq, dur)
            if wave_2 and wave_2 != "off" and mix_r > 0.0:
                w2 = self.osc.generate(wave_2, freq, dur)
                note = ((1.0 - mix_r) * note) + (mix_r * w2)

            # Apply ADSR
            note = self.mod.apply_adsr(
                note, attack=min(att, dur * 0.3),
                decay=min(dec, dur * 0.3),
                sustain_level=sus, release=min(rel, dur * 0.4))

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
                # Re-synthesize with frequency profile
                t = np.linspace(0, dur, len(note), endpoint=False)
                phase = np.cumsum(freq_profile / sr) * 2 * np.pi
                note_slid = np.sin(phase)
                # Apply envelope scaling to slid note
                if len(note) > 0 and np.max(np.abs(note)) > 0:
                    env_shape = note / (np.max(np.abs(note)) + 1e-9)
                    note = note_slid * np.abs(env_shape)

            # Apply Portamento (slide from previous note)
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
                bits = patch["bit_depth"]
                note = self.mod.apply_bitcrush(note, bits)
            if "saturation" in patch:
                sat = patch["saturation"]
                note = self.mod.apply_saturation(note, sat)

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

            # Apply Detune (pitch shift via resampling)
            detune_cents = patch.get("detune", 0.0)
            if detune_cents > 0.01:
                ratio = 2.0 ** (detune_cents / 1200.0)
                indices = np.clip(
                    (np.arange(len(note)) * ratio).astype(int),
                    0, len(note) - 1)
                note = note[indices]

            # Apply Delay Start (shift note later)
            delay_frac = patch.get("delay_start", 0.0)
            if delay_frac > 0.01:
                delay_samples = int(delay_frac * len(note) * 0.5)
                if 0 < delay_samples < len(note):
                    shifted = np.zeros(len(note))
                    shifted[delay_samples:] = note[:len(note) - delay_samples]
                    note = shifted

            segments.append(note)
            segments.append(np.zeros(int(sr * gap)))  # gap
            prev_freq = freq

        full = np.concatenate(segments)
        full = full / (np.max(np.abs(full)) + 1e-9) * 0.7  # normalize

        try:
            sd.play(full.astype(np.float32), samplerate=sr)
        except Exception as e:
            print("Audio Playback Error:", e)
