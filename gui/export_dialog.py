# gui/export_dialog.py
"""
Unified Export Dialog for Lanthorn PSG.
Provides file name, directory, format (WAV/OGG/MP3), 
and multi-quality selection for all audio exports.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QGroupBox, QFileDialog,
    QDialogButtonBox, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import os
from engine.paths import get_export_tracks_dir, get_export_sfx_dir


class ExportDialog(QDialog):
    """
    Unified export dialog that returns:
        - filename (str): base name without extension
        - directory (str): export directory path
        - format (str): "wav", "ogg", or "mp3"
        - qualities (list[str]): selected quality profiles
    """

    def __init__(self, parent=None, title="Export Audio", default_name="untitled",
                 export_type="tracks"):
        super().__init__(parent)
        # Pick default dir based on export type
        if export_type == "sfx":
            default_dir = get_export_sfx_dir()
        else:
            default_dir = get_export_tracks_dir()
        self._default_dir = default_dir
        self.setWindowTitle(title)
        self.setFixedSize(460, 380)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #cccccc; }
            QGroupBox { 
                color: #888; font-weight: bold; border: 1px solid #3f3f46; 
                border-radius: 6px; margin-top: 8px; padding-top: 14px; 
            }
            QGroupBox::title { subcontrol-position: top left; padding: 2px 8px; }
            QLineEdit { 
                background-color: #2d2d30; color: #e0e0e0; border: 1px solid #3f3f46; 
                border-radius: 4px; padding: 6px; font-size: 13px; 
            }
            QComboBox { 
                background-color: #2d2d30; color: #e0e0e0; border: 1px solid #3f3f46; 
                border-radius: 4px; padding: 4px; 
            }
            QPushButton { 
                background-color: #333; color: #ccc; border: 1px solid #3f3f46; 
                border-radius: 4px; padding: 6px 12px; 
            }
            QPushButton:hover { background-color: #444; }
            QCheckBox { color: #cccccc; spacing: 6px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QLabel { color: #aaa; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # --- Title ---
        title_label = QLabel(f"🎵 {title}")
        title_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #55aaff; padding: 4px 0;")
        layout.addWidget(title_label)
        
        # === File Name ===
        name_group = QGroupBox("File Name")
        name_layout = QHBoxLayout()
        self.name_input = QLineEdit(default_name)
        self.name_input.setPlaceholderText("Enter file name...")
        name_layout.addWidget(self.name_input)
        name_group.setLayout(name_layout)
        layout.addWidget(name_group)
        
        # === Export Directory ===
        dir_group = QGroupBox("Export Directory")
        dir_layout = QHBoxLayout()
        self.dir_input = QLineEdit(self._default_dir)
        self.dir_input.setReadOnly(True)
        dir_layout.addWidget(self.dir_input, stretch=1)
        
        browse_btn = QPushButton("📁 Browse")
        browse_btn.setStyleSheet("background-color: #2a4a6a; color: #8cc8ff;")
        browse_btn.clicked.connect(self._browse_dir)
        dir_layout.addWidget(browse_btn)
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)
        
        # === Format & Quality Row ===
        options_layout = QHBoxLayout()
        
        # Format selector
        fmt_group = QGroupBox("Format")
        fmt_layout = QVBoxLayout()
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["WAV", "OGG", "MP3"])
        self.fmt_combo.setCurrentText("WAV")
        fmt_layout.addWidget(self.fmt_combo)
        fmt_group.setLayout(fmt_layout)
        options_layout.addWidget(fmt_group)
        
        # Quality checkboxes
        q_group = QGroupBox("Quality Profiles")
        q_layout = QVBoxLayout()
        
        self.cb_hq = QCheckBox("HQ — 44.1kHz / 16-bit")
        self.cb_hq.setChecked(True)
        self.cb_hq.setStyleSheet("QCheckBox { color: #44ff88; }")
        
        self.cb_mid = QCheckBox("MidFi — 22kHz / 16-bit")
        self.cb_mid.setStyleSheet("QCheckBox { color: #ffcc44; }")
        
        self.cb_retro = QCheckBox("Retro — 11kHz / 8-bit")
        self.cb_retro.setStyleSheet("QCheckBox { color: #ff6644; }")
        
        q_layout.addWidget(self.cb_hq)
        q_layout.addWidget(self.cb_mid)
        q_layout.addWidget(self.cb_retro)
        q_group.setLayout(q_layout)
        options_layout.addWidget(q_group)
        
        layout.addLayout(options_layout)
        
        # === Buttons ===
        btn_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        btn_layout.addStretch()
        
        export_btn = QPushButton("💾 Export")
        export_btn.setStyleSheet("""
            QPushButton { 
                background-color: #007acc; color: white; font-weight: bold; 
                font-size: 14px; padding: 8px 24px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #0098ff; }
        """)
        export_btn.clicked.connect(self.accept)
        btn_layout.addWidget(export_btn)
        
        layout.addLayout(btn_layout)
    
    def _browse_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", self.dir_input.text()
        )
        if directory:
            self.dir_input.setText(directory)
    
    def get_export_settings(self):
        """Returns the export configuration as a dict."""
        qualities = []
        if self.cb_hq.isChecked():
            qualities.append("HQ")
        if self.cb_mid.isChecked():
            qualities.append("MidFi")
        if self.cb_retro.isChecked():
            qualities.append("Retro")
        
        if not qualities:
            qualities = ["HQ"]  # Fallback
        
        return {
            "filename": self.name_input.text().strip() or "untitled",
            "directory": self.dir_input.text().strip() or self._default_dir,
            "format": self.fmt_combo.currentText().lower(),
            "qualities": qualities,
        }
