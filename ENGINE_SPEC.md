# LANTHORN PSG — ENGINE SPECIFICATION V0.3.3
Tracker + SFX Painter

## TABLE OF CONTENTS
1. [Architecture Overview]
2. [Constants & Tuning]
3. [Oscillator (oscillator.py)]
4. [Modifiers — Signal Processing Chain (modifiers.py)]
5. [Music Theory Engine (theory.py)]
6. [Preset Manager (preset_manager.py)]
7. [Sequencer & Render Pipeline (playback.py)]
8. [FX Command Reference]
9. [FX Stacking & Override System]
10. [Master Automation Commands]
11. [Chord System & Arpeggiator]
12. [CSV File Format (V1.1)]
13. [Pattern System & Order List]
14. [Track Column Layout]
15. [Playback Modes & Loop System]
16. [Stereo Panning System]
17. [SFX Canvas]
18. [FX Editor]
19. [Keyboard Shortcuts]
20. [Context Menus (Right-Click)]
21. [Smart Edit Tools]
22. [Thread Safety & Undo]
23. [File Paths & Directory Structure]
24. [Retro Visualizer]
---

## 1. ARCHITECTURE OVERVIEW

Lanthorn PSG is a software-rendered programmable sound generator built around a tracker interface. Audio is pre-computed into numpy arrays before playback via `sounddevice`.

### GUI Layer (PyQt6)
- **Instrument Lab** → Sound design workbench + Instrument bank
- **Tracker Grid** → `_build_tracks_from_grid()` → Sequencer
- **SFX Canvas** → 3-layer piano-roll painter

### Engine Layer
- **Oscillator**: Generates raw waveforms from frequency profiles.
- **Modifiers**: ADSR, Tremolo, Vibrato, Saturation, Bitcrush, Echo, Ring Mod, Retrigger, PWM, Portamento, Pitch Sweep.
- **Theory**: MIDI ↔ Frequency conversion, scale quantization, note string conversion.
- **Sequencer**: Per-event rendering, FX chain, FX stacking/override, stereo mix, pan automation, volume automation, master automation (MVL/CVL/MPN/CPN), limiter.
- **PresetManager**: JSON instrument save/load with factory preset seeding.
- **CsvHandler**: V1.1 project serialization.

**Output**: `sounddevice.play()` → Speakers

---

## 2. CONSTANTS & TUNING (constants.py)

| Constant | Value | Purpose |
| :--- | :--- | :--- |
| `HIFI_SAMPLE_RATE` | 44100 Hz | CD-quality rendering |
| `HIFI_BIT_DEPTH` | 24-bit | Hi-fi export depth |
| `LOFI_SAMPLE_RATE` | 11025 Hz | Lo-fi / retro rendering |
| `LOFI_BIT_DEPTH` | 8-bit | Lo-fi export depth |
| `ROOT_A4_FREQ` | 440.0 Hz | A4 concert pitch standard |
| `DEFAULT_BPM` | 120 | Initial project tempo |
| `CHANNELS` | 8 | Default track count |
| `STEPS_PER_PATTERN` | 16 | Legacy default (now 64) |

**Frequency Formula (Equal Temperament):**
`freq(midi) = 440.0 × 2^((midi - 69) / 12)`

---

## 3. OSCILLATOR (oscillator.py)

The Oscillator generates raw mathematical waveforms. It accepts either a static frequency (int/float) or a dynamic frequency array (numpy) for real-time modulation effects.

**CLASS**: `Oscillator(sample_rate=44100)`

**METHOD**: `generate(wave_type, frequency, duration, duty_cycle=0.5)`
- Returns: `numpy float64` array of audio samples.

### Phase Integration
Instead of using instantaneous frequency, the oscillator integrates frequency over time to compute continuous phase:
`phase[n] = Σ(freq[0..n]) / sample_rate`
This prevents phase discontinuities during pitch modulation.

### Supported Waveforms
| Type | Description |
| :--- | :--- |
| `sine` | `sin(2π × phase)` — Pure tone, no harmonics |
| `square` | PWM via `duty_cycle`: `+1` if `(phase%1 < duty)`, else `-1` |
| `sawtooth` | `2 × (phase%1) - 1` — All harmonics, bright/buzzy |
| `triangle` | `abs(sawtooth) × 2 - 1` — Odd harmonics, mellow |
| `noise` | Uniform random `[-1, +1]` — Frequency-independent |

### Dual Oscillator
Patches can define `wave_type` + `wave_type_2` with a configurable mix ratio. The render pipeline generates both waveforms and blends them:
`output = (1 - mix) × wave1 + mix × wave2`

---

## 4. MODIFIERS — SIGNAL PROCESSING CHAIN (modifiers.py)

**CLASS**: `Modifiers(sample_rate=44100)`

Uses a cached time-axis helper (`_time_axis`, LRU cache size 16) to avoid reallocating `np.linspace` arrays for repeated buffer lengths.

### Amplitude Shaping
- `apply_adsr(wave, attack, decay, sustain_level, release)`
  Generates an ADSR envelope and multiplies it with the waveform. Times in seconds. Sustain level 0.0-1.0. Early-exit optimization when envelope is flat.
- `apply_tremolo(wave, speed_hz, depth)`
  Amplitude modulation via sine LFO: `1.0 - depth × 0.5 × (1 + sin(2π × speed × t))`

### Pitch & Timing Modulation
- `generate_vibrato_profile(base_freq, duration, speed_hz, depth_semitones)`
  Returns a frequency array: `freq × 2^((sin(LFO) × depth) / 12)`
- `generate_slide_profile(start_freq, end_freq, duration, slide_time)`
  Linear frequency interpolation. Slide portion is clamped to not exceed total duration.
- `generate_pitch_sweep(start_freq, end_freq, duration)`
  Logarithmic (geometric) frequency sweep via `np.geomspace`. Frequencies floored at 1 Hz to prevent `log(0)`.

### Timbral Effects
- `apply_saturation(wave, gain)` — Soft clipping via `tanh(wave × gain)`. No-op if gain ≤ 1.0.
- `apply_bitcrush(wave, bits)` — Reduces amplitude resolution to 2^bits levels. No-op if bits ≥ 16.
- `generate_pwm_profile(duration, lfo_speed, depth, base_width)` — Time-varying duty cycle array.
- `apply_ring_mod(wave, carrier_freq, mix)` — Carrier sine multiplication for inharmonic sidebands. Wet/dry mix.
- `apply_retrigger(wave, rate_hz)` — Chops audio into bursts via square wave gate.
- `apply_echo(wave, delay_time, feedback, num_taps=6)` — Multi-tap delay with exponential decay. Each tap applies `gain *= feedback`.

---

## 5. MUSIC THEORY ENGINE (theory.py)

**CLASS**: `Theory` (static methods)

- `string_to_midi(note_str)`: Converts tracker notation to MIDI integer. Accepts formats: `C-4`, `C#4`, `Db5`, `C4`. Returns -1 for `---`, `OFF`, or invalid input.
- `midi_to_string(midi_note)`: Converts MIDI integer to tracker notation. Natural notes use dash separator (`C-4`), sharps use compact format (`C#4`). Returns `---` for out of range.
- `note_to_freq(midi_note)`: `440 × 2^((midi - 69) / 12)`
- `quantize_to_scale(note, root_note, mode_name)`: Snaps note to nearest valid scale degree. Uses minimum-distance algorithm on mode interval array.

### Supported Modes
| Mode | Intervals (semitones from root) |
| :--- | :--- |
| Chromatic | 0 1 2 3 4 5 6 7 8 9 10 11 |
| Major (Ionian) | 0 2 4 5 7 9 11 |
| Minor (Aeolian) | 0 2 3 5 7 8 10 |
| Harmonic Minor | 0 2 3 5 7 8 11 |
| Dorian | 0 2 3 5 7 9 10 |
| Phrygian | 0 1 3 5 7 8 10 |

---

## 6. PRESET MANAGER (preset_manager.py)

**CLASS**: `PresetManager(preset_dir=None)`

### Storage
- **User directory**: `~/.lanthorn_psg/presets/` (writable, survives app updates)
- **Factory presets**: Bundled in the app, copied to user dir on first run via `_seed_factory_presets()`
- **Standard folders** (always created): `bass`, `leads`, `pads`, `percussion`, `drums`, `keys`, `strings`, `sfx`

### Methods
- `get_default_patch()` — Returns the baseline Init Patch dictionary.
- `list_folders()` — Sorted list of subdirectory names.
- `list_presets(folder)` — Sorted list of JSON filenames in a folder.
- `save_preset(patch_dict, filename, folder)` — Writes JSON to `preset_dir/folder/filename.json`.
- `load_preset(filename, folder)` — Reads JSON from disk.
- `delete_preset(filename, folder)` — Removes file from disk.

### Default Patch Properties
| Parameter | Default |
| :--- | :--- |
| `name` | Init Patch |
| `wave_type` | square |
| `duty_cycle` | 0.5 |
| `attack` | 0.05s |
| `decay` | 0.20s |
| `sustain_level` | 0.5 |
| `release` | 0.30s |
| `vibrato_speed` | 0.0 Hz |
| `vibrato_depth` | 0.0 semitones |
| `tremolo_speed` | 0.0 Hz |
| `tremolo_depth` | 0.0 |

### Full Patch Schema
```json
{
  "name": "string",
  "wave_type": "sine|square|sawtooth|triangle|noise",
  "wave_type_2": "string|null",
  "mix": 0.5,
  "duty_cycle": 0.5,
  "envelope": {
    "attack": 0.05,
    "decay": 0.20,
    "sustain_level": 0.5,
    "release": 0.30
  },
  "lfo": {
    "vibrato_speed": 0.0,
    "vibrato_depth": 0.0,
    "tremolo_speed": 0.0,
    "tremolo_depth": 0.0
  },
  "portamento": {
    "slide_time": 0.0
  },
  "saturation": 1.0,
  "bit_depth": 16,
  "echo": {
    "delay_time": 0.0,
    "feedback": 0.0
  },
  "ring_mod": {
    "carrier_freq": 500.0,
    "mix": 0.0
  },
  "fx_chain": []
}
```

---

## 7. SEQUENCER & RENDER PIPELINE (playback.py)

**CLASS**: `Sequencer(sample_rate=44100)`
- Internal instances: `Oscillator`, `Modifiers`, `PresetManager`
- State: `master_vol` (1.0), `master_pan` (0.0) — persist across patterns for song-level automation.

### Step Timing
`step_time = (60 / bpm) / lines_per_beat`
Example: 120 BPM, 4 LPB → 0.125s (125ms) per step.

### Render Pipeline (`render_pattern`)
1. **Collect Macros**: Scan all tracks for MVL/CVL/MPN/CPN commands. These are extracted and applied at the master level, not per-track.
2. **Per-Track Rendering**:
   - Initialize mono mix buffer.
   - Retrieve track-level patch.
   - **For each event**:
     - **NOTE OFF**: 5ms fade-out at sample position, silence after.
     - **Patch Override**: Extract per-event instrument if set.
     - **Pitch Resolution**:
       - Check for PRT (portamento) → linear slide from previous note.
       - Check for SUP/SDN → pitch bend profile over 80% of note duration.
       - Otherwise → vibrato profile from patch LFO settings.
     - **Generation**:
       - Generate waveform 1 with frequency profile.
       - If dual oscillator: generate waveform 2, blend by mix ratio.
     - **Chord Normalization**: `sum / √(num_notes)`.
     - **Signal Chain** (legacy patches without fx_chain):
       - Saturation → Bitcrushing → Tremolo → Echo → Ring Mod
     - **ADSR Envelope**: Applied after timbral effects.
     - **FX Commands**: Applied via `_apply_fx_to_event()` (see §8-9).
     - **Velocity Scaling**: Final amplitude multiply.
     - **Mix** into track buffer.
3. **Track Volume Automation**: Keyframe interpolation via `_apply_automation()`.
4. **Pan Automation**: Generate sample-accurate pan envelope, apply stereo gain split.
5. **Master Mix**:
   - Sum all tracks into stereo buffer.
   - Apply MVL/CVL volume automation.
   - Apply MPN/CPN pan automation.
   - Apply optional master volume multiplier.
6. **Limiter**: Brick-wall normalize to max 0.98 (can be disabled for multi-pattern concatenation).

---

## 8. FX COMMAND REFERENCE

FX commands use the format: `CMD XX` (decimal 0-255). Dual-parameter commands split the byte: `High = XX >> 4`, `Low = XX & 0xF`.

### 📐 Envelope
| CMD | Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `ENV` | ADSR Envelope | adsr | A.D.S.R — four-value envelope shaping |

### 🎵 Pitch
| CMD | Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `ARP` | Arpeggio | dual | Single: Hi/Lo = semitone offsets. Chord: Hi = pattern, Lo = subdivisions |
| `SUP` | Slide Up | byte | 0-255 → 0-12 semitone bend up over 80% of gate time |
| `SDN` | Slide Down | byte | 0-255 → 0-12 semitone bend down over 80% of gate time |
| `PRT` | Portamento | byte | 0-255 → glide time 0.01-0.5s from previous note |
| `DTN` | Detune | byte | 0-255 → 0-50 cents pitch offset via resampling |

### 🌊 Modulation
| CMD | Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `VIB` | Vibrato | dual | Hi = Speed (1-16 Hz), Lo = Depth (0-1 semitone) |
| `TRM` | Tremolo | dual | Hi = Speed (1-16 Hz), Lo = Depth (0.0-1.0) |
| `RNG` | Ring Mod | byte | 0-255 → 0.0-1.0 carrier mix (500 Hz carrier) |
| `SAT` | Saturation | byte | 0-255 → gain 1.0-5.0 via `tanh` waveshaping |
| `VMD` | Voice Mod | dual | Hi = Target mix (0=OSC1 … F=100% OSC2), Lo = Slide time (0=instant … F=full gate) |

### 🔊 Dynamics
| CMD | Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `VOL` | Volume | byte | 0-255 → 0.0-1.0 amplitude |
| `CUT` | Note Cut | byte | 0-255 → cut position with 5ms fade-out |
| `PAN` | Pan | byte | 0 = Left, 128 = Center, 255 = Right |
| `RTG` | Retrigger | byte | 0-255 → 1-32 Hz stutter gate rate |

### ⏱ Time
| CMD | Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `ECH` | Echo | dual | Hi = Delay (× 50ms), Lo = Feedback (0.0-0.9). 6-tap max |
| `DLY` | Delay | byte | 0-255 → note start position shift (0%–100% of gate) |

### 🎛 Master Mix (Global Automation)
| CMD | Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `MVL` | Master Volume | byte | Instantly set global song volume (0-255) |
| `CVL` | Crescendo Volume | byte | Slide master volume to target until next command |
| `MPN` | Master Pan | byte | Instantly set global stereo balance (0=L, 128=C, 255=R) |
| `CPN` | Crescendo Pan | byte | Slide master pan to target until next command |

---

## 9. FX STACKING & OVERRIDE SYSTEM

### Stacking
Multiple FX can be chained on a single FX slot using `:` as a separator:
`VIB 68: SAT 40` → applies Vibrato, then Saturation.

Parsed by `_parse_fx_stack()` which splits on `:` and returns a list of `(cmd, param)` tuples.

### Instrument FX Chain
Patches may include an `fx_chain` list. When present, legacy patch-level effects (saturation, bitcrush, tremolo, echo, ring mod from the patch dict) are skipped, and the fx_chain is processed instead.

### Override Prefix
Tracker FX prefixed with `!` override matching instrument FX instead of stacking additively:
- `!VIB 68` → replaces the instrument's VIB with tracker VIB 68.
- `VIB 68` (no prefix) → adds tracker VIB on top of instrument's VIB.

### FX Resolution Order
1. Collect instrument FX from `patch.fx_chain`.
2. Collect tracker FX from `fx1` and `fx2` columns.
3. Remove any instrument FX whose command code matches a `!`-prefixed tracker FX.
4. Concatenate remaining instrument FX + all tracker FX.
5. Apply sequentially.

---

## 10. MASTER AUTOMATION COMMANDS

Master commands (MVL, CVL, MPN, CPN) operate at the song level, not per-track. They are extracted from all tracks before per-track rendering begins and applied to the final stereo master buffer.

### Volume Automation
- `MVL XX` → Set master volume immediately to `XX/255`.
- `CVL XX` → Linear slide to `XX/255` over the duration until the next MVL/CVL command.
- State persists across patterns in song playback (`self.master_vol`).

### Pan Automation
- `MPN XX` → Set master pan immediately. `0=Left, 128=Center, 255=Right`.
- `CPN XX` → Linear slide to target pan.
- State persists across patterns (`self.master_pan`).

---

## 11. CHORD SYSTEM & ARPEGGIATOR

### Notation
- **Single Note**: `C-4`
- **Chord**: `C-4,E-4,G-4` (Comma-separated, no spaces)

### Rendering
`_build_tracks_from_grid()` in `tracker.py` parses comma-separated notation. When "note" is a list, `render_pattern` iterates each tone, generates waves, and normalizes by `√(len(notes))`.

### Chord Arp (`ARP XY`)
When applied to a chord list, the engine cycles frequencies instead of using semitone offsets.
- **X (High)**: Pattern (0=Up, 1=Down, 2=Ping-Pong, 3=Random)
- **Y (Low)**: Subdivision count

### Single-Note Arp (`ARP XY`)
When applied to a single note:
- Divides the note into 3 equal segments.
- Plays root, root+X semitones, root+Y semitones in sequence.

### Context Menu Presets
Auto-detects chord presence:
- **Chord present**: Up/Down/Ping-Pong/Random cycles actual chord notes.
- **No chord**: Cycles by semitone offsets (e.g., Major 3+5, Octave).

### Available Chord Shapes
| Shape | Intervals | Example (C-4 root) |
| :--- | :--- | :--- |
| Major | [0, 4, 7] | `C-4,E-4,G-4` |
| Minor | [0, 3, 7] | `C-4,D#4,G-4` |
| 7th | [0, 4, 7, 10] | `C-4,E-4,G-4,A#4` |
| Maj7 | [0, 4, 7, 11] | `C-4,E-4,G-4,B-4` |
| Sus4 | [0, 5, 7] | `C-4,F-4,G-4` |
| Dim | [0, 3, 6] | `C-4,D#4,F#4` |
| Aug | [0, 4, 8] | `C-4,E-4,G#4` |

---

## 12. CSV FILE FORMAT (V1.1)

The project file is a standard RFC 4180 CSV written via Python's `csv` module. Human-readable and diff-friendly.

**CLASS**: `CsvHandler` (all static methods)

### 12.1 File Structure Overview
A V1.1 project file has exactly 4 sections in order:
1. **Global Header** (exactly 1 row)
2. **Patches** (0..N rows, tag: `PATCH`)
3. **Order List** (marker + `SEQ` rows)
4. **Patterns** (marker + `PATTERN`/`EVENT`)

**Section Markers**:
- `"--- ORDER LIST ---",SeqIndex,PatternID`
- `"--- PATTERNS ---",Type,ID,Length`

---

### 12.2 Global Header
| Field | Type | Description |
| :--- | :--- | :--- |
| `LANTHORN_V1.1` | str | Magic identifier + version tag |
| `TotalTracks` | int | Number of track groups (default 8) |
| `SubColumns` | int | Columns per track (always 7) |
| `BPM` | int | Beats per minute |
| `LPB` | int | Lines (steps) per beat |
| `Key` | str | Musical root: C, C#, D, ... B |
| `Mode` | str | Scale: Chromatic, Major, Minor, etc. |
| `LPM` | int | Lines per measure (default 16) |

---

### 12.3 Section 2: Patches (Embedded Instruments)
**Row format**: `PATCH, InstrumentName, "{JSON}"`

- **Save Behavior**: Only referenced and available instruments are serialized.
- **Load Behavior**: Parsed via `json.loads()` and stored in `bank_data`.

---

### 12.4 Section 3: Order List
**Row format**: `SEQ, Index, PatternID`

- **Index**: 0-based and sequential (for readability).
- **PatternID**: References a pattern defined in Section 4.

---

### 12.5 Section 4: Patterns & Events
#### Pattern Header
`PATTERN, PatternID, StepCount [, BPM, LPB, LPM, Key, Mode, CustomName]`
- Declares a new pattern with ID and total steps.
- Optional fields (positions 3-7) override global header values.
- **Custom Name** (position 8): User-defined display name for the pattern. Falls back to PatternID if absent. Backward compatible — older CSV files without this field load with ID as name.

#### Event Data
`EVENT, Row, Track, Note, Inst, Vel, Gate, FX1, FX2`
Sparse storage is used: only non-empty rows are saved.

---

### 12.6 Pipelines

#### Save Pipeline
1. **Persist** current grid to memory.
2. **Write Header** with global settings.
3. **Scan** for used instruments and write `PATCH` rows.
4. **Enumerate** order list and write `SEQ` rows.
5. **Serialize** patterns and events.

#### Load Pipeline
1. **Validate** version tag.
2. **Parse Header** and apply to UI/state.
3. **State Machine Parser**: Reads Patches → Order List → Patterns.
4. **Grid Initialization**: Fills grid with placeholder defaults based on column types.
5. **Event Mapping**: Overwrites placeholders with sparse event data.
6. **Apply** loaded state to the tracker widget.

---

### 12.7 Edge Cases & Validation
- **Missing Header Fields**: Reverts to 120/4/C/Chromatic.
- **Out of Bounds**: Row/Track indices exceeding limits are skipped.
- **Corruption**: Invalid JSON results in a warning; the load continues.

---

### 12.8 Raw CSV Example
```csv
LANTHORN_V1.1,8,7,120,4,C,Minor
PATCH,Lead,"{""name"": ""Lead"", ""wave_type"": ""sawtooth"", ...}"
PATCH,Bass,"{""name"": ""Bass"", ""wave_type"": ""square"", ...}"
--- ORDER LIST ---,SeqIndex,PatternID
SEQ,0,A
SEQ,1,B
SEQ,2,A
--- PATTERNS ---,Type,ID,Length
PATTERN,A,16
EVENT,0,0,C-4,Lead,100,04,VIB 36,
EVENT,0,1,C-3,Bass,127,08,,
EVENT,12,0,C-4,E-4,G-4,Lead,100,04,ARP 4,
PATTERN,B,16
EVENT,0,0,D-4,Lead,96,04,,
```

---

## 13. PATTERN SYSTEM & ORDER LIST

### Pattern IDs
- **Format**: Single letter (A-Z) or double letter (AA-ZZ).
- **Capacity**: 702 unique patterns.
- **Generation**: `_next_pattern_id()` finds the first available ID.

### Pattern Length
- Independent step count per pattern (1-256 steps, default 64).

### Custom Pattern Names
- Each pattern has a `pattern_names` entry mapping ID → display name.
- Default: Name equals ID (e.g., `"A"` → `"A"`).
- Cloned patterns get `" (copy)"` suffix.
- Stored in CSV at position 8 of the `PATTERN` row.
- **Backward compatible**: Old CSV files without this field load cleanly — ID is used as name.
- Displayed in the order list alongside timing info.

### Per-Pattern Settings
Each pattern stores its own override for: BPM, LPB, LPM, Key, Mode.

### Order List
- Defines the song's playback sequence.
- Displayed in a scrollable list with custom pattern names and real-time highlighting during playback.

### Sequence Editor (`SeqEdit`)
- Drag-and-drop dialog for reordering, adding, inserting, and duplicating patterns in the sequence.

---

## 14. TRACK COLUMN LAYOUT
Each track consists of 7 sub-columns:

| Col | Type | Content |
| :--- | :--- | :--- |
| 0 | Note | Note name or chord (e.g., `C-4,E-4,G-4`) |
| 1 | Inst | Instrument name from bank |
| 2 | Vel | Velocity (0-255) |
| 3 | Gate | Gate length in decimal steps |
| 4 | FX1 | FX command slot 1 (supports stacking with `:`) |
| 5 | FX2 | FX command slot 2 (supports stacking with `:`) |
| 6 | Spc | Visual spacer |

- **Multi-Instrument Tracks**: Each event embeds its own patch if specified in the Inst column.

---

## 15. PLAYBACK MODES & LOOP SYSTEM

### Playback Modes
| Mode | Behavior |
| :--- | :--- |
| **Play Song** | Renders all patterns in the order list sequentially |
| **Play Pattern** | Renders only the active pattern |
| **Solo Track** | Renders one track from the active pattern; mutes others |
| **Play from Row** | Renders from the cursor row to the end of the pattern |
| **Stop** | Halts playback and resets visualizers |
| **Pause** | Freezes the playhead without resetting |

### Loop System
The Loop button (🔁) supports **scope-aware looping** via right-click context menu:

| Scope | Button Label | Behavior |
| :--- | :--- | :--- |
| **Project** | 🔁 Loop | Loops the full song order list (uses cached audio for instant restart) |
| **Pattern** | 🔁 Loop Pat | Loops only the active pattern |
| **Track** | 🔁 Loop Trk | Loops the currently selected track (solo) |
| **Selection** | 🔁 Loop Sel | Loops the Ctrl+L selection range |

Selecting a scope auto-enables the Loop toggle and updates the button label.

### Centered Playhead
During playback, the active row is continuously scrolled to the center of the table viewport using `scrollToItem(PositionAtCenter)`. This runs on every viz tick (~55fps), so the playhead stays centered even when the window is resized or maximized mid-playback.

### Visualizer
- Free-floating oscilloscope with dual-layer rendering (glow + bright main curve).
- Uses a raised-cosine edge fade for a "floating" effect.

### Playback Timing
- Viz timer: 18ms timer (~55fps) drives playhead, scroll centering, and oscilloscope.
- Playhead position: `perf_counter` elapsed vs. pre-calculated step timestamps.
- Step lookup: binary search on cached timestamp array for O(log n) per tick.
- Audio is streamed via `sounddevice.play(array, samplerate)`.

### Visualizer Detail
- Free-floating oscilloscope (no background, transparent).
- 400×44px PlotWidget with antialiasing.
- Waveform centered on current playhead position (±1200 samples window).
- Raised-cosine edge fade (25% each side) for floating effect.
- Dual-layer rendering: dim wide glow + thin bright main curve.

---

## 16. STEREO PANNING SYSTEM

The engine renders in full stereo. Each track is mixed mono and then positioned via sample-accurate pan automation.

### 16.1 Pan FX Encoding
`PAN X` (decimal 0-255):
- **0**: Hard Left
- **64**: Mid-Left
- **128**: Center (Default)
- **192**: Mid-Right
- **255**: Hard Right

### 16.2 Pan Extraction Pipeline
PAN is NOT processed as a standard FX. Instead:
1. **Standalone Scan**: Any `PAN` command on a row with no note is extracted as a keyframe.
2. **Event Scan**: `PAN` commands on note events are extracted, then deleted from the event to avoid re-triggering.
3. **Envelope Generation**: Linear interpolation (`np.interp`) builds a sample-accurate array for stereo gain calculation.

### 16.3 Stereo Gain Formula
- `left_gain = clip(1.0 - pan_value, 0.0, 1.0)`
- `right_gain = clip(1.0 + pan_value, 0.0, 1.0)`

---

## 17. SFX CANVAS

The SFX Canvas is a multi-layer piano-roll painter for designing retro sound effects by drawing directly on a grid.

### 17.1 Grid Layout
- **Y-axis**: Musical notes from C2 (MIDI 36) to C7 (MIDI 96) — 61 chromatic rows.
- **X-axis**: 128 time steps mapped to a configurable duration (0.05s – 4.00s).
- Row 0 (top) = C7 (highest), Row 60 (bottom) = C2 (lowest).
- Note labels are drawn at every C and A for orientation.

### 17.2 Paint Layers
Three independent color layers, each with its own waveform, volume, and FX:

| Layer | Color | Default Wave |
| :--- | :--- | :--- |
| Red | `#FF004D` | sine |
| Blue | `#29ADFF` | square |
| Yellow | `#FFEC27` | sawtooth |

Per-layer options:
- **Waveform**: sine, square, triangle, sawtooth, noise.
- **Volume**: 0–100% mix slider.
- **Normalize**: Scales the layer to peak amplitude before mixing.
- **Smooth**: Interpolates frequency between painted notes (glide/portamento mode).

### 17.3 Drawing Tools
| Tool | Behavior |
| :--- | :--- |
| 🖌 Paint | Click or drag to place cells on the active layer |
| 🧹 Erase | Click or drag to remove cells (adjustable size 1–5) |
| 📏 Line | Click start → click end; fills via Bresenham's algorithm |
| 〰 Curve | Click start → click control → click end; quadratic Bézier fill |

Ctrl+scroll to zoom the canvas.

### 17.4 Foley FX (Per-Layer)
Each layer stores its own independent FX parameters. Switching the active layer saves the outgoing FX and loads the incoming set.

| FX | Range | Description |
| :--- | :--- | :--- |
| Attack | 0–100% | Fade-in envelope |
| Release | 0–100% | Fade-out envelope |
| Bit Crush | 4–16 bits | Amplitude quantization |
| Pitch Sweep | −100 to +100 | Logarithmic pitch bend over duration |
| Tremolo | 0–100% depth, 1–30 Hz | Amplitude LFO |
| Vibrato | 0–100% depth, 1–30 Hz | Pitch LFO (sample-shift) |
| Echo | 0–80% feedback, 20–500 ms | Multi-tap delay (6 taps max) |
| Ring Mod | 0–100% mix, 50–2000 Hz | Carrier sine multiplication |
| Saturation | 0–100% | Soft clip via `tanh` overdrive |
| Detune | 0–100 cents | Pitch shift via resampling |
| Delay Start | 0–100% | Shifts audio later in the buffer |

### 17.5 Rendering Modes
**Normal mode** (default): Each unique painted note generates its own oscillator. Multiple notes at the same step produce chords, normalized by `√(voices)`. Notes are gated per-step with 1ms edge ramps.

**Smooth mode** (per-layer checkbox): Builds a continuous frequency envelope by interpolating between painted note positions. The waveform follows the envelope for glide/portamento effects while still gated to painted regions.

### 17.6 Duration & Auto-Trim
- **Duration slider**: Sets the total canvas timespan (0.05s – 4.00s).
- **Auto-trim**: When enabled, only the painted region (first painted step to last) is rendered, proportionally scaling the duration. Disabled = full 128-step span.

### 17.7 Mix Pipeline
1. Render each layer independently (Normal or Smooth mode).
2. Apply that layer's Foley FX chain.
3. Scale by layer volume.
4. Sum all active layers, normalize by `√(active_count)`.
5. Brick-wall clip to ±0.98.
6. Output: mono float32 array at 44100 Hz.

---

## 18. FX EDITOR

The FX Editor is a popup dialog for composing FX commands with visual controls.

### Opening
- Right-click an FX column cell → open FX Editor from context menu.
- The editor reads the existing cell value and pre-populates controls.

### Cell Detection & Pre-Population
When opened on a cell containing existing FX data (e.g., `VIB 35`):
1. Parses the FX string and adds each command to the FX stack list.
2. Pre-selects the matching effect in the dropdown (e.g., "Vibrato").
3. Sets parameter sliders to match encoded values (byte, dual hi/lo, or ADSR).
4. Updates the waveform preview to show the existing effect shape.
5. Stacked FX strings (`:` separated) are all added to the stack; the first effect is pre-selected.

### Parameter Types
| Type | Controls | Encoding |
| :--- | :--- | :--- |
| `byte` | Single slider (0-255) | Full byte value |
| `dual` | Two sliders (0-15 each) | `(hi << 4) | lo` → decimal |
| `adsr` | Four sliders (A, D, S, R) | Dot-separated: `A.D.S.R` |

### FX Stack
The editor supports composing stacked FX by adding multiple effects to a list. The final output joins them with `:` separators.

---

## 19. KEYBOARD SHORTCUTS

| Shortcut | Action |
| :--- | :--- |
| **Ctrl+N** | New Project |
| **Ctrl+O** | Open Project (.csv) |
| **Ctrl+S** | Quick Save |
| **Ctrl+Q** | Quit |
| **Ctrl+Z / Ctrl+Y** | Undo / Redo (limited to 300 actions) |
| **Ctrl+L** | Loop Selection (clone block N times) |
| **Enter** (on FX) | FX Interpolation Sweep (select range first) |
| **Space** | Play / Pause (toggle) |
| **Shift+Space** | Play from Cursor (selected row) |
| **Arrow Keys** | Move cursor in grid |
| **Shift+↑** | Shift selected note up within the current scale/key |
| **Shift+↓** | Shift selected note down within the current scale/key |
| **Shift+Click** | Range select |
| **Delete / Backspace** | Clear selected cells |
| **F1** | Help Dialog (contextual per tab) |

### Scale-Constrained Note Shifting (Shift+Up/Down)
Shifts the selected cell's note to the next valid note in the pattern's key and scale:
1. Reads the current note string from the cell.
2. Converts to MIDI via `Theory.string_to_midi()`.
3. Walks the scale intervals up/down to find the next valid degree.
4. Converts back via `Theory.midi_to_string()` and writes to the cell.
5. Plays a debounced audio preview (50ms `QTimer`) of the new note(s).

Holding the hotkey rapidly shifts through scale degrees with CPU-safe debounced playback. Only the active row's notes are previewed (no cross-track chord preview).

---

## 20. CONTEXT MENUS (Right-Click)
The menu is column-aware (e.g., click a Note column for Chords, or a Patch column for the Instrument Browser).

- **Common**: Play Song/Pattern/Solo, Copy/Paste, Fill Pattern.
- **Note**: Insert OFF, Octaves, Chord Builder (Maj, Min, 7th, Maj7, Sus4, Dim, Aug).
- **Instrument**: Patch browser organized by folder (📁 bass, drums, keys...).
- **Velocity**: Presets (pp, p, mf, f, ff, Max).
- **Gate**: Presets (1, 2, 4, 8, 16 steps).
- **FX**: Open FX Editor (loads existing cell data), Quick FX presets.
- **Loop Button**: Right-click to set loop scope (Project, Pattern, Track, Selection).

---

## 21. SMART EDIT TOOLS
Smart Edit provides batch-editing capabilities scoped to the current track and pattern.

- **Edit Similar**: Batch-set Velocity, Gate, or FX for every row using the same instrument.
- **Select Similar**: Highlights all rows using the same patch for manual editing.
- **Fill Pattern**: Repeats a rhythmic selection forward through the rest of the track.
- **Repeat Selection**: Detects selection rhythm (e.g., every 4th row) and extends it to the end.

---

## 22. THREAD SAFETY & UNDO

### Render Thread Safety
All playback render methods (`play_sequence`, `play_current_pattern`, `play_solo_track`) run audio rendering in background `threading.Thread` instances. Safety measures:

1. **Stop Before Play**: Every play method calls `stop_sequence()` first to kill any in-flight render.
2. **Generation Counter** (`_render_gen`): Incremented before each render. Stale threads check `gen != self._render_gen` before invoking GUI methods and abort silently if outdated.
3. **RuntimeError Guard**: `QMetaObject.invokeMethod()` calls are wrapped in `try/except RuntimeError` to gracefully handle widget destruction during rendering.
4. **GUI State Extraction**: GUI-dependent data (BPM, grid, bank, etc.) is extracted in the main thread *before* spawning the background thread, preventing cross-thread PyQt access violations.

### Undo System
- Uses `QUndoStack` with a **300-action limit** (`setUndoLimit(300)`).
- Prevents unbounded memory growth during long editing sessions.
- Covers cell edits, Shift+Up/Down note shifts, and paste operations.
- Guard flag (`_undo_block`) prevents recursive `itemChanged` signals during undo/redo replay.

### Audio Preview Debouncing
The Shift+Up/Down note preview uses a 50ms `QTimer` (single-shot) to debounce rapid key-repeat. Only the final note in a burst is rendered and played, preventing CPU overload from rapid hotkey presses.

---
**END OF SPECIFICATION — Sections 1-22**

---

## 23. FILE PATHS & DIRECTORY STRUCTURE

### Central Path Module (`engine/paths.py`)
All user-facing directories are managed through `engine/paths.py`, which provides OneDrive-aware resolution on Windows.

### Directory Tree
```
Documents/Lanthorn-PSG/
├── Projects/           Tracker .csv files  (Save/Load Project default)
├── SFX/                SFX .sfx.csv files   (Save/Load SFX Canvas default)
└── Exports/
    ├── Tracks/         Tracker audio exports (WAV/OGG/MP3)
    └── SFX/            SFX audio exports
```

### OneDrive Resolution (Windows)
1. Check `%USERPROFILE%/OneDrive/Documents` — if it exists, use it.
2. Fall back to `%USERPROFILE%/Documents`.
3. Last resort: `os.path.expanduser("~/Documents")`.

### Path Functions
| Function | Returns |
| :--- | :--- |
| `get_documents_dir()` | Resolved Documents folder |
| `get_lanthorn_root()` | `Documents/Lanthorn-PSG/` |
| `get_projects_dir()` | `.../Projects/` |
| `get_sfx_dir()` | `.../SFX/` |
| `get_export_tracks_dir()` | `.../Exports/Tracks/` |
| `get_export_sfx_dir()` | `.../Exports/SFX/` |
| `ensure_all_dirs()` | Creates entire tree (called at startup) |

### Export Dialog
The `ExportDialog` accepts an `export_type` parameter (`"tracks"` or `"sfx"`) to select the correct default export directory.

---

## 24. RETRO VISUALIZER

The Retro Visualizer is a standalone "Project Player" that renders a scrolling DOS-style tracker display with synchronized audio playback.

### 24.1 Launch & Integration
- Accessed via **RetroVisualizer** menu in the main menu bar.
- Opens a launch dialog with **Project**, **Theme**, and **Display Mode** selectors.
- Auto-saves the current project before launching.
- Runs in a frameless window, driven entirely by hotkeys.

### 24.2 Themes (7 Profiles)
| Theme | Style |
| :--- | :--- |
| **MS-DOS** | Black bg, green/yellow/cyan text, double-line box drawing |
| **Commodore 64** | Purple bg, pastel text, half-block borders |
| **ZX Spectrum** | Black bg, bright primary colors, thin-line borders |
| **Amiga** | Blue bg, gold/orange notes, single-line borders |
| **Apple II** | Black bg, green phosphor monochrome |
| **Atari ST** | White bg, black text, green header bar |
| **VT100** | Black bg, amber phosphor monochrome, double-line borders |

Themes are cycled at runtime with **←/→** arrow keys.

### 24.3 Display Modes
| Mode | Resolution | Layout |
| :--- | :--- | :--- |
| Maximized (16:9) | Native | All tracks side-by-side |
| 1280×800 (16:10) | Windowed | All tracks side-by-side |
| 960×600 (16:10) | Windowed | All tracks side-by-side |
| 1024×768 (4:3) | Windowed | Hamburger split: T1-4 top, T5-8 bottom |
| Fullscreen | Native | All tracks side-by-side |

**4:3 Hamburger Split**: The screen divides horizontally — top half shows oscilloscopes + tracker for tracks 1-4, a separator line, then bottom half shows oscilloscopes + tracker for tracks 5-8.

### 24.4 Audio Playback
- Renders the full song audio in a background thread using the `Sequencer` engine.
- Per-track audio is also rendered individually for per-track oscilloscopes.
- Playback synchronized to `time.perf_counter()` with a timestamp array for row mapping.
- Audio output via `sounddevice`.

### 24.5 Per-Track ASCII Oscilloscopes
Each visible track gets its own ASCII waveform display, reading from individually-rendered per-track audio buffers.

- **Window**: ±8000 samples (~363ms visible) for a slow, retro feel.
- **Characters**: Directional (`╱ \ ═ ─ ╲`) for waveform shape, density blocks (`█ ▓ ▒ ░ ·`) for amplitude intensity.
- **Flat line** (`─`) when paused or before playback starts.
- **Edge fading** for smooth visual boundaries.

### 24.6 Tracker Display
- **Columns**: All data truncated to 3 characters — clean hard cut, no suffix.
  - Layout: `Nte Ins Vel Gt FX1 FX2` (3+3+3+2+3+3 = 17 data, 5 gaps = 22 chars/track)
- **Track dividers**: Solid `║` between tracks.
- **Centered playhead**: Current row stays centered with upcoming rows visible.
- **Pattern transitions**: `═══ PAT: [Name] ═══` separator markers.
- **Beat/Measure markers**: Beat rows (every LPB) get brighter row numbers; measure rows (every LPM) get a subtle background tint.
- **Status bar**: KEY, BPM, LPB, LPM, PAT, ROW, Theme, Display Mode, Play/Pause state.

### 24.7 V1.1 CSV Parsing
The `VisualizerDataParser` reads Lanthorn V1.1 CSV files independently from the main tracker:
- Parses header, patches, order list, and patterns.
- Handles per-pattern overrides (BPM, LPB, LPM, Key, Mode).
- Builds track data suitable for the `Sequencer` from parsed events.
- Reads custom pattern names (position 8 of PATTERN rows).

### 24.8 Hotkeys
| Key | Action |
| :--- | :--- |
| **Space** | Play / Pause |
| **Enter** | Reset to beginning |
| **Alt+Enter** / **F11** | Toggle fullscreen |
| **W** | Cycle display mode |
| **← / →** | Cycle theme |
| **ESC** | Pause + Close |

---
**END OF SPECIFICATION**
