# LANTHORN PSG — ENGINE SPECIFICATION V0.3.2
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
9. [Chord System & Arpeggiator]
10. [CSV File Format (V1.1)]
11. [Pattern System & Order List]
12. [Track Column Layout]
13. [Playback Modes]
14. [Stereo Panning System]
15. [SFX Canvas]
16. [Keyboard Shortcuts]
17. [Context Menus (Right-Click)]
18. [Smart Edit Tools]
---

## 1. ARCHITECTURE OVERVIEW

Lanthorn PSG is a software-rendered programmable sound generator built around a tracker interface. Audio is pre-computed into numpy arrays before playback via `sounddevice`.

### GUI Layer (PyQt6)
- **Tracker Grid** → `_build_tracks_from_grid()` → Sequencer
- **Workbench** (Sound Design) → Bank (patch dictionaries)
- **SFX Canvas** (3-layer piano roll)

### Engine Layer
- **Oscillator**: Generates raw waveforms from frequency profiles.
- **Modifiers**: ADSR, Tremolo, Vibrato, Saturation, Bitcrush, Echo, Ring Mod, Retrigger, PWM, Portamento.
- **Theory**: MIDI ↔ Frequency conversion, scale quantization.
- **Sequencer**: Per-event rendering, FX chain, stereo mix, pan automation, volume automation, limiter.
- **PresetManager**: JSON instrument save/load.
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

### Amplitude Shaping
- `apply_adsr(wave, attack, decay, sustain_level, release)`
  Generates an ADSR envelope and multiplies it with the waveform. Times in seconds. Sustain level 0.0-1.0.
- `apply_tremolo(wave, speed_hz, depth)`
  Amplitude modulation via sine LFO: `1.0 - depth × 0.5 × (1 + sin(2π × speed × t))`

### Pitch & Timing Modulation
- `generate_vibrato_profile(base_freq, duration, speed_hz, depth_semitones)`
  Returns a frequency array: `freq × 2^((sin(LFO) × depth) / 12)`
- `generate_slide_profile(start_freq, end_freq, duration, slide_time)`
  Linear frequency interpolation.
- `generate_pitch_sweep(start_freq, end_freq, duration)`
  Logarithmic (geometric) frequency sweep via `np.geomspace`.

### Timbral Effects
- `apply_saturation(wave, gain)`
  Soft clipping via `tanh(wave × gain)`.
- `apply_bitcrush(wave, bits)`
  Reduces amplitude resolution to 2^bits levels.
- `generate_pwm_profile(duration, lfo_speed, depth, base_width)`
  Time-varying duty cycle array.
- `apply_ring_mod(wave, carrier_freq, mix)`
  Carrier multiplication for inharmonic sidebands.
- `apply_retrigger(wave, rate_hz)`
  Chops audio into bursts via square wave gate.
- `apply_echo(wave, delay_time, feedback)`
  Single-tap delay line.

---

## 5. MUSIC THEORY ENGINE (theory.py)

**CLASS**: `Theory` (static methods)

- `string_to_midi(note_str)`: Converts tracker notation (e.g., "C-4") to MIDI integer.
- `note_to_freq(midi_note)`: `440 × 2^((midi - 69) / 12)`
- `quantize_to_scale(note, root_note, mode_name)`: Snaps note to nearest scale degree.

### Supported Modes
| Mode | Intervals (semitones from root) |
| :--- | :--- |
| Chromatic | 0 1 2 3 4 5 6 7 8 9 10 11 |
| Major (Ionian) | 0 2 4 5 7 9 11 |
| Minor (Aeolian) | 0 2 3 5 7 8 10 |
| Harmonic Minor | 0 2 3 5 7 8 11 |
| Dorian | 0 2 3 5 7 9 10 |
| Phrygian | 0 1 3 5 7 8 10 |

## 6. PRESET MANAGER (preset_manager.py)

**CLASS**: `PresetManager(preset_dir="presets")`

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
  }
}
```

---

## 7. SEQUENCER & RENDER PIPELINE (playback.py)

**CLASS**: `Sequencer(sample_rate=44100)`
- Internal instances: `Oscillator`, `Modifiers`, `PresetManager`

### Step Timing
`step_time = (60 / bpm) / lines_per_beat`
Example: 120 BPM, 4 LPB → 0.125s (125ms) per step.

### Render Pipeline (`render_pattern`)
1. **Initialize** per-track mono mix buffer.
2. **Retrieve** track-level patch.
3. **For each event**:
   - **NOTE OFF**: 5ms fade-out at sample position.
   - **Patch Override**: Extract per-event parameters.
   - **Generation**:
     - Convert MIDI to frequency.
     - Apply pitch modifiers (PRT, SUP, SDN).
     - Generate waveforms (dual oscillator blending).
   - **Normalization**: Divide chord sum by `√(num_notes)`.
   - **Signal Chain**: Saturation → Bitcrushing → Tremolo → Echo → Ring Mod → ADSR → FX Commands → Velocity Scaling.
   - **Mix** into track buffer.
4. **Post-Processing**:
   - Volume & Pan automation keyframe interpolation.
   - Mix into stereo master buffer.
5. **Mastering**: Apply global volume automation and brick-wall limiter (max 0.98).

---

## 8. FX COMMAND REFERENCE

FX commands use the format: `CMD XX` (decimal 0-255). Dual-parameter commands split the byte: `High = XX >> 4`, `Low = XX & 0xF`.

| CMD | Name | Description |
| :--- | :--- | :--- |
| `VIB` | Vibrato | Hi = Speed (1-16 Hz), Lo = Depth (0-1 semitone) |
| `TRM` | Tremolo | Hi = Speed, Lo = Depth |
| `ECH` | Echo | Hi = Delay (n × 50ms), Lo = Feedback (0.0-0.9) |
| `VOL` | Volume | Full byte (0-255) → 0.0-1.0 amplitude |
| `RNG` | Ring Mod | Full byte (0-255) → 0.0-1.0 carrier mix (500 Hz) |
| `CUT` | Note Cut | Full byte (0-255) → Cut position (0.0-1.0) |
| `ARP` | Arpeggio | Single: Hi/Lo = Semitones. Chord: Hi = Pattern, Lo = Subdivisions. |
| `SUP` | Slide Up | Full byte (0-255) → 0-12 semitone bend up |
| `SDN` | Slide Down | Full byte (0-255) → 0-12 semitone bend down |
| `PRT` | Portamento | Full byte (0-255) → Slide time 0.01-0.5s |
| `PAN` | Pan | 0 = Left, 128 = Center, 255 = Right |
| `DTN` | Detune | Full byte (0-255) → Detune 0-50 cents |
| `DLY` | Delay | Full byte (0-255) → Note start position shift |
| `SAT` | Saturation | Full byte (0-255) → Gain 1.0-5.0 |
| `RTG` | Retrigger | Full byte (0-255) → 1-32 Hz strobe rate |


---

## 9. CHORD SYSTEM & ARPEGGIATOR

### Notation
- **Single Note**: `C-4`
- **Chord**: `C-4,E-4,G-4` (Comma-separated, no spaces)

### Rendering
`_build_tracks_from_grid()` in `tracker.py` parses comma-separated notation. When "note" is a list, `render_pattern` iterates each tone, generates waves, and normalizes by `√(len(notes))`.

### Chord Arp (`ARP XY`)
When applied to a chord list, the engine cycles frequencies instead of using semitone offsets.
- **X (High)**: Pattern (0=Up, 1=Down, 2=Ping-Pong, 3=Random)
- **Y (Low)**: Subdivision count

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


---

## 10. CSV FILE FORMAT (V1.1)

The project file is a standard RFC 4180 CSV written via Python's `csv` module. Human-readable and diff-friendly.

**CLASS**: `CsvHandler` (all static methods)

### 10.1 File Structure Overview
A V1.1 project file has exactly 4 sections in order:
1. **Global Header** (exactly 1 row)
2. **Patches** (0..N rows, tag: `PATCH`)
3. **Order List** (marker + `SEQ` rows)
4. **Patterns** (marker + `PATTERN`/`EVENT`)

**Section Markers**:
- `"--- ORDER LIST ---",SeqIndex,PatternID`
- `"--- PATTERNS ---",Type,ID,Length`

---

### 10.2 Global Header
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

### 10.3 Section 2: Patches (Embedded Instruments)
**Row format**: `PATCH, InstrumentName, "{JSON}"`

- **Save Behavior**: Only referenced and available instruments are serialized.
- **Load Behavior**: Parsed via `json.loads()` and stored in `bank_data`.

---

### 10.4 Section 3: Order List
**Row format**: `SEQ, Index, PatternID`

- **Index**: 0-based and sequential (for readability).
- **PatternID**: References a pattern defined in Section 4.

---

### 10.5 Section 4: Patterns & Events
#### Pattern Header
`PATTERN, PatternID, StepCount [, BPM, LPB, LPM, Key, Mode]`
- Declares a new pattern with ID and total steps.
- Optional fields override global header values.

#### Event Data
`EVENT, Row, Track, Note, Inst, Vel, Gate, FX1, FX2`
Sparse storage is used: only non-empty rows are saved.

---

### 10.6 Pipelines

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

### 10.7 Edge Cases & Validation
- **Missing Header Fields**: Reverts to 120/4/C/Chromatic.
- **Out of Bounds**: Row/Track indices exceeding limits are skipped.
- **Corruption**: Invalid JSON results in a warning; the load continues.

---

### 10.8 Raw CSV Example
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

## 11. PATTERN SYSTEM & ORDER LIST

### Pattern IDs
- **Format**: Single letter (A-Z) or double letter (AA-ZZ).
- **Capacity**: 702 unique patterns.
- **Generation**: `_next_pattern_id()` finds the first available ID.

### Pattern Length
- Independent step count per pattern (1-256 steps, default 64).

### Order List
- Defines the song's playback sequence.
- Displayed in a scrollable list with real-time highlighting.

### Sequence Editor (`SeqEdit`)
- Drag-and-drop dialog for reordering, adding, inserting, and duplicating patterns in the sequence.

---

## 12. TRACK COLUMN LAYOUT
Each track consists of 7 sub-columns:

| Col | Type | Content |
| :--- | :--- | :--- |
| 0 | Note | Note name or chord (e.g., `C-4,E-4,G-4`) |
| 1 | Inst | Instrument name from bank |
| 2 | Vel | Velocity (0-255) |
| 3 | Gate | Gate length in decimal steps |
| 4 | FX1 | FX command slot 1 |
| 5 | FX2 | FX command slot 2 |
| 6 | Spc | Visual spacer |

- **Multi-Instrument Tracks**: Each event embeds its own patch if specified in the Inst column.

---

## 13. PLAYBACK MODES

| Mode | Behavior |
| :--- | :--- |
| **Play Song** | Renders all patterns in the order list sequentially. |
| **Play Pattern**| Renders only the active pattern; wraps playback. |
| **Solo Track** | Renders one track from the active pattern; mutes others. |
| **Stop** | Halts playback and resets visualizers. |
| **Pause** | Freezes the playhead without resetting. |

### Visualizer
- Free-floating oscilloscope with dual-layer rendering (glow + bright main curve).
- Uses a raised-cosine edge fade for a "floating" effect.

---

  PLAYBACK TIMING:
    - Playhead timer: fires at step_duration_ms intervals
    - Viz timer: separate 18ms timer (~55fps) for smooth oscilloscope display
    - Audio is streamed via sounddevice.play(array, samplerate)

  VISUALIZER:
    Free-floating oscilloscope (no background, transparent).
    400×44px PlotWidget with antialiasing.
    Waveform centered on current playhead position (±1200 samples window).
    Raised-cosine edge fade (25% each side) for floating effect.
    Dual-layer rendering: dim wide glow + thin bright main curve.


---

## 14. STEREO PANNING SYSTEM

The engine renders in full stereo. Each track is mixed mono and سپس positioned via sample-accurate pan automation.

### 14.1 Pan FX Encoding
`PAN X` (decimal 0-255):
- **0**: Hard Left
- **64**: Mid-Left
- **128**: Center (Default)
- **192**: Mid-Right
- **255**: Hard Right

### 14.2 Pan extraction Pipeline
PAN is NOT processed as a standard FX. Instead:
1. **Standalone Scan**: Any `PAN` command on a row with no note is extracted as a keyframe.
2. **Event Scan**: `PAN` commands on note events are extracted, then deleted from the event to avoid re-triggering.
3. **Envelope Generation**: Linear interpolation (`np.interp`) builds a sample-accurate array for stereo gain calculation.

---

## 15. SFX CANVAS

The SFX Canvas is a multi-layer piano-roll painter for designing retro sound effects by drawing directly on a grid.

### 15.1 Grid Layout
- **Y-axis**: Musical notes from C2 (MIDI 36) to C7 (MIDI 96) — 61 chromatic rows.
- **X-axis**: 128 time steps mapped to a configurable duration (0.05s – 4.00s).
- Row 0 (top) = C7 (highest), Row 60 (bottom) = C2 (lowest).
- Note labels are drawn at every C and A for orientation.

### 15.2 Paint Layers
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

### 15.3 Drawing Tools
| Tool | Behavior |
| :--- | :--- |
| 🖌 Paint | Click or drag to place cells on the active layer. |
| 🧹 Erase | Click or drag to remove cells (adjustable size 1–5). |
| 📏 Line | Click start → click end; fills via Bresenham's algorithm. |
| 〰 Curve | Click start → click control → click end; quadratic Bézier fill. |

Ctrl+scroll to zoom the canvas.

### 15.4 Foley FX (Per-Layer)
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

### 15.5 Rendering Modes
**Normal mode** (default): Each unique painted note generates its own oscillator. Multiple notes at the same step produce chords, normalized by `√(voices)`. Notes are gated per-step with 1ms edge ramps.

**Smooth mode** (per-layer checkbox): Builds a continuous frequency envelope by interpolating between painted note positions. The waveform follows the envelope for glide/portamento effects while still gated to painted regions.

### 15.6 Duration & Auto-Trim
- **Duration slider**: Sets the total canvas timespan (0.05s – 4.00s).
- **Auto-trim**: When enabled, only the painted region (first painted step to last) is rendered, proportionally scaling the duration. Disabled = full 128-step span.

### 15.7 Mix Pipeline
1. Render each layer independently (Normal or Smooth mode).
2. Apply that layer's Foley FX chain.
3. Scale by layer volume.
4. Sum all active layers, normalize by `√(active_count)`.
5. Brick-wall clip to ±0.98.
6. Output: mono float32 array at 44100 Hz.

---

## 16. KEYBOARD SHORTCUTS

| Shortcut | Action |
| :--- | :--- |
| **Ctrl+N** | New Project |
| **Ctrl+O** | Open Project |
| **Ctrl+S** | Quick Save |
| **Ctrl+Z / Y** | Undo / Redo |
| **Ctrl+L** | Loop Selection (Clones block N times) |
| **Enter** | FX Interpolation Sweep (Select range first) |
| **Arrow Keys** | Move cursor in grid |
| **Shift+Click**| Range select |
| **Delete** | Clear selected cells |

---

## 17. CONTEXT MENUS (Right-Click)
The menu is column-aware (e.g., click a Note column for Chords, or a Patch column for the Instrument Browser).

- **Common**: Play Song/Pattern/Solo, Copy/Paste, Fill Pattern.
- **Note**: Insert OFF, Octaves, Chord Builder.
- **Instrument**: Patch browser (organized by folder).
- **FX**: Interpolation sweeps, common command presets (Vibrato, Echo, Pan).

---

## 18. SMART EDIT TOOLS
Smart Edit provides batch-editing capabilities scoped to the current track and pattern.

- **Edit Similar**: Batch-set Velocity, Gate, or FX for every row using the same instrument.
- **Select Similar**: Highlights all rows using the same patch for manual editing.
- **Fill Pattern**: Repeats a rhythmic selection forward through the rest of the track.
- **Repeat Selection**: Detects selection rhythm (e.g., every 4th row) and extends it to the end.

---
**END OF SPECIFICATION**

