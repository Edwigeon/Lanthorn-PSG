# engine/theory.py
from .constants import ROOT_A4_FREQ

class Theory:
    # Mode Interval Table (Semitones from Root)
    MODES = {
        "chromatic": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "major": [0, 2, 4, 5, 7, 9, 11],
        "minor": [0, 2, 3, 5, 7, 8, 10],
        "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
        "dorian": [0, 2, 3, 5, 7, 9, 10],
        "phrygian": [0, 1, 3, 5, 7, 8, 10]
    }

    @staticmethod
    def string_to_midi(note_str):
        """Converts a tracker string like 'C-4', 'D#5', 'C#4', or 'Db5' into a MIDI integer (0-127)."""
        if not note_str or note_str == "---" or note_str == "OFF":
            return -1
            
        notes_sharp = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        notes_flat  = ["C", "Db",  "D", "Eb",  "E", "F", "Gb",  "G", "Ab",  "A", "Bb",  "B"]
        
        try:
            # Strip dash separator: "C-4" → "C4", "C#4" stays "C#4"
            cleaned = note_str.replace("-", "")
            
            # Check for sharp or flat (2-char note name)
            if len(cleaned) > 1 and cleaned[1] in ('#', 'b'):
                note_char = cleaned[0:2]
            else:
                note_char = cleaned[0]
            octave_str = cleaned[-1]
            if not octave_str.isdigit():
                return -1
                
            octave = int(octave_str)
            if note_char in notes_sharp:
                return notes_sharp.index(note_char) + (octave + 1) * 12
            elif note_char in notes_flat:
                return notes_flat.index(note_char) + (octave + 1) * 12
            else:
                return -1
        except Exception:
            return -1

    @staticmethod
    def midi_to_string(midi_note):
        """Converts a MIDI integer (0-127) back to a tracker string like 'C-4' or 'C#4'."""
        if midi_note is None or midi_note < 0 or midi_note > 127:
            return "---"
        notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        note_name = notes[midi_note % 12]
        octave = (midi_note // 12) - 1
        if '#' in note_name:
            return f"{note_name}{octave}"
        else:
            return f"{note_name}-{octave}"

    @staticmethod
    def note_to_freq(midi_note):
        """Converts a standard MIDI note (0-127) to Frequency in Hz."""
        if midi_note is None or midi_note < 0:
            return 0.0
        # The standard formula for equal temperament tuning
        return ROOT_A4_FREQ * (2.0 ** ((midi_note - 69) / 12.0))

    @staticmethod
    def quantize_to_scale(note, root_note, mode_name="chromatic"):
        """Snaps a MIDI note to the nearest valid interval in a given key/mode."""
        mode_intervals = Theory.MODES.get(mode_name.lower(), Theory.MODES["chromatic"])
        
        # Find the note's relative position to the root (0-11)
        rel_note = (note - root_note) % 12
        octave = (note - root_note) // 12
        
        # Find the closest valid semitone in our mode array
        closest_interval = min(mode_intervals, key=lambda x: abs(x - rel_note))
        
        # Reconstruct and return the "legal" MIDI note
        return root_note + (octave * 12) + closest_interval
