# engine/paths.py
"""
Centralized path management for Lanthorn PSG.

All user-facing directories live under:
    Documents/Lanthorn-PSG/
        Projects/           Tracker .csv files
        SFX/                SFX .sfx.csv files
        Exports/
            Tracks/         Tracker audio exports
            SFX/            SFX audio exports

OneDrive-aware: checks OneDrive/Documents first on Windows.
"""

import os
import sys
import platform


def get_documents_dir():
    """Resolves the user's Documents folder, accounting for OneDrive on Windows."""
    if platform.system() == "Windows":
        user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        # Check OneDrive-redirected Documents first
        onedrive = os.path.join(user_profile, "OneDrive", "Documents")
        if os.path.isdir(onedrive):
            return onedrive
        # Standard Windows Documents
        standard = os.path.join(user_profile, "Documents")
        if os.path.isdir(standard):
            return standard
    # Fallback (macOS / Linux / last resort)
    return os.path.expanduser("~/Documents")


def get_lanthorn_root():
    """Root of all Lanthorn user data: Documents/Lanthorn-PSG/"""
    return os.path.join(get_documents_dir(), "Lanthorn-PSG")


def get_projects_dir():
    """Default directory for tracker .csv project files."""
    return os.path.join(get_lanthorn_root(), "Projects")


def get_sfx_dir():
    """Default directory for SFX .sfx.csv files."""
    return os.path.join(get_lanthorn_root(), "SFX")


def get_export_tracks_dir():
    """Default directory for tracker audio exports."""
    return os.path.join(get_lanthorn_root(), "Exports", "Tracks")


def get_export_sfx_dir():
    """Default directory for SFX audio exports."""
    return os.path.join(get_lanthorn_root(), "Exports", "SFX")


def ensure_all_dirs():
    """Creates the full Lanthorn-PSG directory tree if it doesn't exist."""
    for d in [get_projects_dir(), get_sfx_dir(),
              get_export_tracks_dir(), get_export_sfx_dir()]:
        os.makedirs(d, exist_ok=True)
    # Seed demo projects on first run
    seed_demo_projects()


def _get_bundled_projects_dir():
    """Finds the bundled projects/ folder shipped with the app."""
    import shutil
    candidates = [
        # PyInstaller frozen bundle
        os.path.join(getattr(sys, '_MEIPASS', ''), 'projects'),
        # Next to the executable
        os.path.join(os.path.dirname(sys.executable), 'projects'),
        # Next to the source file (development)
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'projects'),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def seed_demo_projects():
    """Copies bundled demo CSV files to the user's Projects directory.
    Only copies files that don't already exist (won't overwrite user work).
    """
    import shutil
    bundled = _get_bundled_projects_dir()
    if not bundled:
        return

    dest = get_projects_dir()
    for filename in os.listdir(bundled):
        if not filename.lower().endswith('.csv'):
            continue
        src_path = os.path.join(bundled, filename)
        dst_path = os.path.join(dest, filename)
        if not os.path.exists(dst_path):
            try:
                shutil.copy2(src_path, dst_path)
                print(f"[Lanthorn] Seeded demo project: {filename}")
            except Exception as e:
                print(f"[Lanthorn] Could not copy {filename}: {e}")

