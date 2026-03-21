# psg_runtime_hook.py
# PyInstaller runtime hook — runs before main.py inside the frozen bundle.
# Points pydub at the bundled ffmpeg/ffprobe executables so MP3 export works
# without the user needing to install ffmpeg separately.

import os
import sys

def _find_ffmpeg():
    """Return the directory containing the bundled ffmpeg binaries, or None."""
    # When frozen by PyInstaller, _MEIPASS is the temp extraction directory.
    base = getattr(sys, '_MEIPASS', None)
    if base:
        candidate = os.path.join(base, 'ffmpeg')
        if os.path.isdir(candidate):
            return candidate

    # Not frozen (dev mode) — look in tools\ffmpeg\ next to the script.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(script_dir, 'tools', 'ffmpeg')
    if os.path.isdir(candidate):
        return candidate

    return None


ffmpeg_dir = _find_ffmpeg()
if ffmpeg_dir:
    # Prepend so pydub finds our bundled copy before any system install.
    os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')

    # Also set pydub's explicit converter paths (pydub ≥ 0.23 honours these).
    ffmpeg_exe  = os.path.join(ffmpeg_dir, 'ffmpeg.exe')
    ffprobe_exe = os.path.join(ffmpeg_dir, 'ffprobe.exe')
    if os.path.isfile(ffmpeg_exe):
        os.environ.setdefault('PYDUB_FFMPEG',  ffmpeg_exe)
    if os.path.isfile(ffprobe_exe):
        os.environ.setdefault('PYDUB_FFPROBE', ffprobe_exe)
