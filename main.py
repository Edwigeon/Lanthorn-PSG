# File: lanthorn_psg/main.py

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

# Absolute import from the gui folder
from gui.main_window import LanthornMainWindow

def main():
    print("🕯️ Igniting Lanthorn PSG v0.3...")

    # Force WM_CLASS on X11 before QApplication is created
    os.environ.setdefault("RESOURCE_NAME", "lanthornpsg")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Linux desktop integration
    app.setApplicationName("lanthornpsg")
    app.setDesktopFileName("lanthornpsg")

    # Set application-wide icon (taskbar, window, alt-tab)
    icon_name = 'lanthorn_icon.png'
    candidates = [
        os.path.join(getattr(sys, '_MEIPASS', ''), icon_name),
        os.path.join(os.path.dirname(sys.executable), icon_name),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), icon_name),
    ]
    for p in candidates:
        if os.path.exists(p):
            app.setWindowIcon(QIcon(p))
            break

    window = LanthornMainWindow()
    window.show()

    # On X11/GNOME, explicitly set WM_CLASS so the .desktop file icon is used
    try:
        import subprocess
        wid = int(window.winId())
        subprocess.Popen(
            ["xprop", "-id", str(wid),
             "-f", "WM_CLASS", "8s",
             "-set", "WM_CLASS", "lanthornpsg\0lanthornpsg"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass  # Not on X11 or xprop not available

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
