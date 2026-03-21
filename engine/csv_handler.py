import csv
import os
import json

class CsvHandler:
    @staticmethod
    def save_project(filepath, tracker_widget, bank_data, bpm=120, lpb=4, key="C", mode="Chromatic", lpm=16):
        """Serializes a V1.1 project: Header, Patches, Order List, Patterns."""
        try:
            # Persist current grid before saving
            tracker_widget.save_grid_to_pattern()
            
            with open(filepath, mode='w', newline='') as file:
                writer = csv.writer(file)
                
                # --- 1. GLOBAL HEADER ---
                writer.writerow([
                    "LANTHORN_V1.1",
                    tracker_widget.current_tracks,
                    tracker_widget.sub_cols,
                    bpm, lpb, key, mode, lpm
                ])
                
                # --- 2. PATCHES ---
                # Collect all instruments used across all patterns
                used_instruments = set()
                for pat_id, grid in tracker_widget.patterns.items():
                    if grid is None:
                        continue
                    for row_data in grid:
                        for t in range(tracker_widget.current_tracks):
                            col_base = t * tracker_widget.sub_cols
                            if col_base + 1 < len(row_data):
                                inst = row_data[col_base + 1]
                                if inst and inst not in ["---", ""]:
                                    used_instruments.add(inst)
                
                for inst_name in used_instruments:
                    if inst_name in bank_data:
                        entry = bank_data[inst_name]
                        # Extract patch from wrapper format, or use raw dict
                        patch = entry.get("patch", entry) if isinstance(entry, dict) and "patch" in entry else entry
                        patch_json = json.dumps(patch)
                        writer.writerow(["PATCH", inst_name, patch_json])
                
                # --- 3. ORDER LIST ---
                writer.writerow(["--- ORDER LIST ---", "SeqIndex", "PatternID"])
                for idx, pat_id in enumerate(tracker_widget.order_list):
                    writer.writerow(["SEQ", idx, pat_id])
                
                # --- 4. PATTERNS ---
                writer.writerow(["--- PATTERNS ---", "Type", "ID", "Length"])
                for pat_id in sorted(tracker_widget.pattern_lengths.keys()):
                    pat_len = tracker_widget.pattern_lengths[pat_id]
                    meta = tracker_widget.pattern_meta.get(pat_id, {})
                    row = ["PATTERN", pat_id, pat_len]
                    # Append per-pattern overrides if they exist
                    if meta:
                        row.extend([
                            meta.get("bpm", ""), meta.get("lpb", ""), meta.get("lpm", ""),
                            meta.get("key", ""), meta.get("mode", "")
                        ])
                    writer.writerow(row)
                    
                    grid = tracker_widget.patterns.get(pat_id)
                    if grid is None:
                        continue
                        
                    for r, row_data in enumerate(grid):
                        if r >= pat_len:
                            break
                        # Collect non-empty event data per track
                        for t in range(tracker_widget.current_tracks):
                            col_base = t * tracker_widget.sub_cols
                            note = row_data[col_base] if col_base < len(row_data) else ""
                            inst = row_data[col_base + 1] if col_base + 1 < len(row_data) else ""
                            vel = row_data[col_base + 2] if col_base + 2 < len(row_data) else ""
                            gate = row_data[col_base + 3] if col_base + 3 < len(row_data) else ""
                            fx1 = row_data[col_base + 4] if col_base + 4 < len(row_data) else ""
                            fx2 = row_data[col_base + 5] if col_base + 5 < len(row_data) else ""
                            
                            if any(v and v not in ["---", "--", ""] for v in [note, inst, vel, gate, fx1, fx2]):
                                writer.writerow(["EVENT", r, t, note, inst, vel, gate, fx1, fx2])
                                
            return True, "Project saved successfully."
        except Exception as e:
            return False, f"Error saving project: {str(e)}"

    @staticmethod
    def load_project(filepath, tracker_widget, bank_data):
        """Reads a V1.1 CSV file and populates the tracker's pattern architecture."""
        if not os.path.exists(filepath):
            return False, "File does not exist."
            
        try:
            with open(filepath, mode='r', newline='') as file:
                reader = csv.reader(file)
                rows = list(reader)
                
                if not rows or rows[0][0] != "LANTHORN_V1.1":
                    return False, "Invalid or unsupported Lanthorn V1.1 project file."
                    
                # --- 1. PARSE HEADER ---
                header = rows[0]
                current_tracks = int(header[1])
                sub_cols = int(header[2])
                bpm = int(header[3]) if len(header) > 3 else 120
                lpb = int(header[4]) if len(header) > 4 else 4
                m_key = header[5] if len(header) > 5 else "C"
                m_mode = header[6] if len(header) > 6 else "Chromatic"
                lpm = int(header[7]) if len(header) > 7 else 16
                
                # Apply to main window
                main_win = tracker_widget.window()
                main_win.spin_bpm.setValue(bpm)
                main_win.spin_lpb.setValue(lpb)
                main_win.spin_lpm.setValue(lpm)
                tracker_widget.theory_engine.combo_root.setCurrentText(m_key)
                tracker_widget.theory_engine.combo_mode.setCurrentText(m_mode)
                tracker_widget.current_tracks = current_tracks
                tracker_widget.sub_cols = sub_cols
                
                # --- 2. STATE MACHINE PARSER ---
                state = "PATCHES"
                order_list = []
                patterns = {}
                pattern_lengths = {}
                tracker_widget.pattern_meta = {}  # Clear stale timing from previous file
                active_pattern_id = None
                
                for row_data in rows[1:]:
                    if not row_data:
                        continue
                    tag = row_data[0]
                    
                    # Detect section separators
                    if tag == "--- ORDER LIST ---":
                        state = "ORDER"
                        continue
                    elif tag == "--- PATTERNS ---":
                        state = "PATTERNS"
                        continue
                    
                    # Process based on state
                    if tag == "PATCH" and len(row_data) >= 3:
                        inst_name = row_data[1]
                        # Skip if this patch already exists in the bank (e.g. from presets)
                        if inst_name in bank_data:
                            continue
                        try:
                            bank_data[inst_name] = {
                                "patch": json.loads(row_data[2]),
                                "display": inst_name,
                                "folder": "custom"
                            }
                        except json.JSONDecodeError:
                            print(f"[Lanthorn] Failed parsing embedded patch: {inst_name}")
                    
                    elif state == "ORDER" and tag == "SEQ" and len(row_data) >= 3:
                        order_list.append(row_data[2])
                    
                    elif state == "PATTERNS" and tag == "PATTERN" and len(row_data) >= 3:
                        active_pattern_id = row_data[1]
                        pat_len = int(row_data[2])
                        pattern_lengths[active_pattern_id] = pat_len
                        # Per-pattern overrides (optional fields 3-7)
                        meta = {}
                        if len(row_data) > 3 and row_data[3]:
                            meta["bpm"] = int(row_data[3])
                        if len(row_data) > 4 and row_data[4]:
                            meta["lpb"] = int(row_data[4])
                        if len(row_data) > 5 and row_data[5]:
                            meta["lpm"] = int(row_data[5])
                        if len(row_data) > 6 and row_data[6]:
                            meta["key"] = row_data[6].strip()
                        if len(row_data) > 7 and row_data[7]:
                            meta["mode"] = row_data[7].strip()
                        if meta:
                            tracker_widget.pattern_meta[active_pattern_id] = meta
                        # Initialize empty grid
                        cols = current_tracks * sub_cols
                        patterns[active_pattern_id] = []
                        for r in range(pat_len):
                            row = []
                            for c in range(cols):
                                rem = c % sub_cols
                                row.append("---" if rem in [0, 1] else ("--" if rem < 6 else ""))
                            patterns[active_pattern_id].append(row)
                    
                    elif state == "PATTERNS" and tag == "EVENT" and len(row_data) >= 9 and active_pattern_id:
                        row_idx = int(row_data[1])
                        trk_idx = int(row_data[2])
                        col_base = trk_idx * sub_cols
                        
                        if row_idx >= pattern_lengths.get(active_pattern_id, 0):
                            continue
                        if trk_idx >= current_tracks:
                            continue
                        
                        grid = patterns[active_pattern_id]
                        if row_data[3]: grid[row_idx][col_base] = row_data[3]
                        if row_data[4]: grid[row_idx][col_base + 1] = row_data[4]
                        if row_data[5]: grid[row_idx][col_base + 2] = row_data[5]
                        if row_data[6]: grid[row_idx][col_base + 3] = row_data[6]
                        if row_data[7]: grid[row_idx][col_base + 4] = row_data[7]
                        if row_data[8]: grid[row_idx][col_base + 5] = row_data[8]
                
                # --- 3. APPLY TO TRACKER ---
                if not order_list or not pattern_lengths:
                    return False, "No patterns or order list found in file."
                
                tracker_widget.patterns = patterns
                tracker_widget.pattern_lengths = pattern_lengths
                tracker_widget.order_list = order_list
                tracker_widget.active_pattern = order_list[0]
                
                # Rebuild the pattern combo box
                tracker_widget.pattern_combo.blockSignals(True)
                tracker_widget.pattern_combo.clear()
                for pid in sorted(pattern_lengths.keys()):
                    tracker_widget.pattern_combo.addItem(pid)
                tracker_widget.pattern_combo.setCurrentText(order_list[0])
                tracker_widget.pattern_combo.blockSignals(False)
                
                # Load the first pattern into the grid
                tracker_widget.load_pattern_to_grid(order_list[0])
                # Apply first pattern's timing overrides to the toolbar
                tracker_widget._apply_pattern_timing(order_list[0])
                tracker_widget.refresh_beat_highlighting()
                tracker_widget.refresh_order_display()
                tracker_widget.update_button_states()
                
            return True, "Project loaded successfully."
        except Exception as e:
            return False, f"Error loading project: {str(e)}"
