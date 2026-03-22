# engine/preset_manager.py
import json
import os
import sys
import shutil

def _get_base_path():
    """Returns the base path for bundled data files (PyInstaller or dev)."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _get_user_preset_dir():
    """Returns a writable preset directory in the user's home."""
    return os.path.join(os.path.expanduser('~'), '.lanthorn_psg', 'presets')

class PresetManager:
    # Canonical patch categories — always created so Save dialog & Bank UI show them
    STANDARD_FOLDERS = [
        "bass", "leads", "pads", "percussion",
        "drums", "keys", "strings", "sfx",
    ]

    def __init__(self, preset_dir=None):
        # Use user-writable dir for presets (supports saving)
        if preset_dir:
            self.preset_dir = preset_dir
        else:
            self.preset_dir = _get_user_preset_dir()
        
        os.makedirs(self.preset_dir, exist_ok=True)
        
        # On first run or when bundled, copy factory presets to user dir
        self._seed_factory_presets()
    
    def _seed_factory_presets(self):
        """Copy bundled factory presets to user dir if they don't exist yet,
        and ensure all standard category folders are present."""
        # Guarantee every standard folder exists (even if empty)
        for folder in self.STANDARD_FOLDERS:
            os.makedirs(os.path.join(self.preset_dir, folder), exist_ok=True)

        bundled_dir = os.path.join(_get_base_path(), 'presets')
        
        # Also check local dev presets dir
        if not os.path.exists(bundled_dir):
            bundled_dir = 'presets'
        
        if not os.path.exists(bundled_dir) or bundled_dir == self.preset_dir:
            return
        
        for root, dirs, files in os.walk(bundled_dir):
            for filename in files:
                if not filename.endswith('.json'):
                    continue
                rel_path = os.path.relpath(os.path.join(root, filename), bundled_dir)
                dest_path = os.path.join(self.preset_dir, rel_path)
                if not os.path.exists(dest_path):
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(os.path.join(root, filename), dest_path)


    def get_default_patch(self):
        """Returns the baseline Lanthorn PSG instrument structure."""
        return {
            "name": "Init Patch",
            "wave_type": "square",
            "duty_cycle": 0.5,
            "attack": 0.05,
            "decay": 0.2,
            "sustain_level": 0.5,
            "release": 0.3,
            "vibrato_speed": 0.0,
            "vibrato_depth": 0.0,
            "tremolo_speed": 0.0,
            "tremolo_depth": 0.0
        }

    def list_folders(self):
        """Returns a sorted list of subdirectory names inside preset_dir."""
        folders = []
        if os.path.exists(self.preset_dir):
            for entry in sorted(os.listdir(self.preset_dir)):
                if os.path.isdir(os.path.join(self.preset_dir, entry)):
                    folders.append(entry)
        return folders

    def list_presets(self, folder=None):
        """Returns a sorted list of preset names (without .json) in a folder.
        If folder is None, lists presets in the root preset_dir."""
        target = os.path.join(self.preset_dir, folder) if folder else self.preset_dir
        presets = []
        if os.path.exists(target):
            for filename in sorted(os.listdir(target)):
                if filename.endswith(".json"):
                    presets.append(filename[:-5])
        return presets

    def list_all(self):
        """Returns a dict: {folder_name: [preset_names], None: [root_presets]}."""
        result = {}
        # Root presets
        root = self.list_presets(folder=None)
        if root:
            result[None] = root
        # Subfolder presets
        for folder in self.list_folders():
            presets = self.list_presets(folder)
            if presets:
                result[folder] = presets
        return result

    def save_instrument(self, name, parameters, folder=None):
        """Writes the parameter dictionary to a JSON file, optionally in a subfolder."""
        safe_name = "".join([c for c in name if c.isalpha() or c.isdigit() or c=='_']).rstrip()
        
        if folder:
            safe_folder = "".join([c for c in folder if c.isalpha() or c.isdigit() or c=='_']).rstrip()
            target_dir = os.path.join(self.preset_dir, safe_folder)
        else:
            target_dir = self.preset_dir
            
        os.makedirs(target_dir, exist_ok=True)
        filepath = os.path.join(target_dir, f"{safe_name}.json")
        
        # Ensure the preset has a name tag inside the file
        parameters["name"] = name 
        
        with open(filepath, 'w') as file:
            json.dump(parameters, file, indent=4)
            
        print(f"[Lanthorn] Saved preset: {filepath}")

    def load_instrument(self, name, folder=None):
        """Reads a JSON file and returns the parameter dictionary."""
        if folder:
            filepath = os.path.join(self.preset_dir, folder, f"{name}.json")
        else:
            filepath = os.path.join(self.preset_dir, f"{name}.json")
        
        if not os.path.exists(filepath):
            print(f"[Lanthorn] Warning: Preset '{name}' not found. Loading Init Patch.")
            return self.get_default_patch()
            
        with open(filepath, 'r') as file:
            parameters = json.load(file)
            
        return parameters

    def create_folder(self, folder_name):
        """Creates a new subfolder in the preset directory."""
        safe_name = "".join([c for c in folder_name if c.isalpha() or c.isdigit() or c=='_']).rstrip()
        target = os.path.join(self.preset_dir, safe_name)
        os.makedirs(target, exist_ok=True)
        print(f"[Lanthorn] Created folder: {target}")
        return safe_name

    def delete_instrument(self, name, folder=None):
        """Deletes a preset JSON file."""
        if folder:
            filepath = os.path.join(self.preset_dir, folder, f"{name}.json")
        else:
            filepath = os.path.join(self.preset_dir, f"{name}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"[Lanthorn] Deleted preset: {filepath}")

    def get_folder_for_category(self, category):
        """Maps a display category name (e.g. 'Bass', 'Leads') to its folder path.
        Returns the full path to the category folder, or self.preset_dir if unrecognized."""
        normalized = category.strip().lower()
        if normalized in self.STANDARD_FOLDERS:
            return os.path.join(self.preset_dir, normalized)
        return self.preset_dir
