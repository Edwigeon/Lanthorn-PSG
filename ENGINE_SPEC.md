================================================================================
  LANTHORN PSG — ENGINE SPECIFICATION V1.1 (In-Depth Reference)
  Dual-Bake Tracker + SFX Painter
================================================================================

TABLE OF CONTENTS
  1.  Architecture Overview
  2.  Constants & Tuning
  3.  Oscillator (oscillator.py)
  4.  Modifiers — Signal Processing Chain (modifiers.py)
  5.  Music Theory Engine (theory.py)
  6.  Preset Manager (preset_manager.py)
  7.  Sequencer & Render Pipeline (playback.py)
  8.  FX Command Reference
  9.  Chord System & Arpeggiator
  10. CSV File Format (V1.1)
  11. Pattern System & Order List
  12. Track Column Layout
  13. Playback Modes
  14. Stereo Panning System
  15. SFX Canvas
  16. Keyboard Shortcuts
  17. Context Menus (Right-Click)
  18. Smart Edit Tools
  19. Building & Distribution

================================================================================
  1. ARCHITECTURE OVERVIEW
================================================================================

Lanthorn PSG is a software-rendered programmable sound generator built around
a tracker interface. Audio is pre-computed into numpy arrays before playback
via sounddevice. The engine is modular:

  ┌────────────────────────────────────────────────────────────────┐
  │                        GUI (PyQt6)                            │
  │   Tracker Grid ──► _build_tracks_from_grid() ──► Sequencer   │
  │   Workbench (Sound Design) ──► Bank (patch dictionaries)     │
  │   SFX Canvas (3-layer piano roll)                            │
  └──────────────────────────┬─────────────────────────────────────┘
                             │
  ┌──────────────────────────▼─────────────────────────────────────┐
  │                     ENGINE LAYER                               │
  │                                                                │
  │   Oscillator ─── Generates raw waveforms from freq profiles    │
  │       │                                                        │
  │   Modifiers ─── ADSR, Tremolo, Vibrato, Saturation, Bitcrush, │
  │       │         Echo, Ring Mod, Retrigger, PWM, Portamento     │
  │       │                                                        │
  │   Theory ────── MIDI↔Freq conversion, scale quantization       │
  │       │                                                        │
  │   Sequencer ─── Per-event rendering, FX chain, stereo mix,     │
  │       │         pan automation, volume automation, limiter      │
  │       │                                                        │
  │   PresetManager ── JSON instrument save/load                   │
  │   CsvHandler ───── V1.1 project serialization                  │
  └────────────────────────────────────────────────────────────────┘
                             │
                    sounddevice.play() → Speakers

================================================================================
  2. CONSTANTS & TUNING (constants.py)
================================================================================

  ┌─────────────────────┬──────────────────────────────────────────┐
  │ Constant            │ Value        │ Purpose                   │
  ├─────────────────────┼──────────────┼───────────────────────────┤
  │ HIFI_SAMPLE_RATE    │ 44100 Hz     │ CD-quality rendering      │
  │ HIFI_BIT_DEPTH      │ 24-bit       │ Hi-fi export depth        │
  │ LOFI_SAMPLE_RATE    │ 11025 Hz     │ Lo-fi / retro rendering   │
  │ LOFI_BIT_DEPTH      │ 8-bit        │ Lo-fi export depth        │
  │ ROOT_A4_FREQ        │ 440.0 Hz     │ A4 concert pitch standard │
  │ DEFAULT_BPM         │ 120          │ Initial project tempo      │
  │ CHANNELS            │ 8            │ Default track count        │
  │ STEPS_PER_PATTERN   │ 16           │ Legacy default (now 64)   │
  └─────────────────────┴──────────────┴───────────────────────────┘

  Frequency Formula (Equal Temperament):
    freq(midi) = 440.0 × 2^((midi - 69) / 12)

================================================================================
  3. OSCILLATOR (oscillator.py)
================================================================================

The Oscillator generates raw mathematical waveforms. It accepts either a
static frequency (int/float) or a dynamic frequency array (numpy) for
real-time modulation effects like vibrato and portamento.

  CLASS: Oscillator(sample_rate=44100)

  METHOD: generate(wave_type, frequency, duration, duty_cycle=0.5)
    Returns: numpy float64 array of audio samples

  PHASE INTEGRATION:
    Instead of using instantaneous frequency, the oscillator integrates
    frequency over time to compute continuous phase:
      phase[n] = Σ(freq[0..n]) / sample_rate
    This prevents phase discontinuities during pitch modulation.

  SUPPORTED WAVEFORMS:
  ┌──────────┬──────────────────────────────────────────────────────┐
  │ Type     │ Description                                         │
  ├──────────┼──────────────────────────────────────────────────────┤
  │ sine     │ sin(2π × phase) — Pure tone, no harmonics           │
  │ square   │ PWM via duty_cycle: +1 if (phase%1 < duty), else -1 │
  │ sawtooth │ 2×(phase%1) - 1 — All harmonics, bright/buzzy       │
  │ triangle │ abs(sawtooth)×2 - 1 — Odd harmonics, mellow         │
  │ noise    │ Uniform random [-1, +1] — Frequency-independent     │
  └──────────┴──────────────────────────────────────────────────────┘

  DUAL OSCILLATOR:
    Patches can define wave_type + wave_type_2 with a configurable mix ratio.
    The render pipeline generates both waveforms and blends them:
      output = (1 - mix) × wave1 + mix × wave2

================================================================================
  4. MODIFIERS — SIGNAL PROCESSING CHAIN (modifiers.py)
================================================================================

  CLASS: Modifiers(sample_rate=44100)

  ── AMPLITUDE SHAPING ──

  apply_adsr(wave, attack, decay, sustain_level, release)
    Generates an ADSR envelope and multiplies it with the waveform.
    All times in seconds. Sustain level is 0.0-1.0.
    Envelope phases: Attack→Decay→Sustain→Release
    If total envelope < wave length, remaining samples are zero-padded.

  apply_tremolo(wave, speed_hz, depth)
    Amplitude modulation via sine LFO.
    LFO formula: 1.0 - depth × 0.5 × (1 + sin(2π × speed × t))
    Depth 0.0 = no effect, 1.0 = full volume pulsing.

  ── PITCH & TIMING MODULATION ──

  generate_vibrato_profile(base_freq, duration, speed_hz, depth_semitones)
    Returns a frequency array (not audio) for the Oscillator.
    Modulates pitch via: freq × 2^((sin(LFO) × depth) / 12)
    Speed in Hz, depth in semitones (0.5 = half-semitone wobble).

  generate_slide_profile(start_freq, end_freq, duration, slide_time)
    Linear frequency interpolation from start to end over slide_time.
    Remaining duration holds at end_freq. Used for Portamento (PRT).

  generate_pitch_sweep(start_freq, end_freq, duration)
    Logarithmic (geometric) frequency sweep. Unlike linear portamento,
    this bends exponentially — essential for SFX like lasers and drops.
    Uses np.geomspace for perceptually even sweeping.

  ── TIMBRAL EFFECTS ──

  apply_saturation(wave, gain)
    Soft clipping via tanh(wave × gain).
    gain ≤ 1.0 = bypass. Higher gain = more harmonic distortion.
    Produces warm overdrive without hard digital clipping.

  apply_bitcrush(wave, bits)
    Reduces amplitude resolution to simulate vintage hardware.
    bits ≥ 16 = bypass. 8 = NES-like crunch, 4 = extreme lo-fi.
    Quantizes to 2^bits levels.

  generate_pwm_profile(duration, lfo_speed, depth, base_width)
    Generates a time-varying duty cycle array for pulse wave modulation.
    Output: base_width + depth × 0.5 × sin(2π × speed × t)

  apply_ring_mod(wave, carrier_freq, mix)
    Multiplies wave by a sine carrier to create inharmonic sidebands.
    Mix 0.0 = dry, 1.0 = fully ring-modulated.
    Produces metallic, bell-like, or robotic timbres.

  apply_retrigger(wave, rate_hz)
    Chops audio into rapid bursts using a square wave gate (0 or 1).
    Used for stutter effects, helicopter rotors, machine gun FX.

  apply_echo(wave, delay_time, feedback)
    Single-tap delay line: output[n+delay] += input[n] × feedback.
    Delay time in seconds. Feedback 0.0-0.9 (capped to prevent blow-up).

================================================================================
  5. MUSIC THEORY ENGINE (theory.py)
================================================================================

  CLASS: Theory (static methods)

  string_to_midi(note_str)
    Converts tracker notation to MIDI integer (0-127).
    Formats: "C-4" (natural), "D#5" (sharp), "OFF" → -1, "---" → -1
    Returns -1 for invalid/empty strings.

  note_to_freq(midi_note)
    Standard equal temperament: 440 × 2^((midi - 69) / 12)
    Returns 0.0 for None or negative values.

  quantize_to_scale(note, root_note, mode_name)
    Snaps a MIDI note to the nearest valid scale degree.
    Finds closest interval in the mode array via min(abs(n - interval)).

  SUPPORTED MODES:
  ┌────────────────┬────────────────────────────────────┐
  │ Mode           │ Intervals (semitones from root)    │
  ├────────────────┼────────────────────────────────────┤
  │ Chromatic      │ 0 1 2 3 4 5 6 7 8 9 10 11         │
  │ Major (Ionian) │ 0 2 4 5 7 9 11                     │
  │ Minor (Aeolian)│ 0 2 3 5 7 8 10                     │
  │ Harmonic Minor │ 0 2 3 5 7 8 11                     │
  │ Dorian         │ 0 2 3 5 7 9 10                     │
  │ Phrygian       │ 0 1 3 5 7 8 10                     │
  └────────────────┴────────────────────────────────────┘

================================================================================
  6. PRESET MANAGER (preset_manager.py)
================================================================================

  CLASS: PresetManager(preset_dir="presets")

  Creates the presets/ directory on init if it doesn't exist.

  DEFAULT PATCH:
  ┌──────────────────┬──────────┐
  │ Parameter        │ Default  │
  ├──────────────────┼──────────┤
  │ name             │ Init Patch │
  │ wave_type        │ square   │
  │ duty_cycle       │ 0.5      │
  │ attack           │ 0.05s    │
  │ decay            │ 0.20s    │
  │ sustain_level    │ 0.5      │
  │ release          │ 0.30s    │
  │ vibrato_speed    │ 0.0      │
  │ vibrato_depth    │ 0.0      │
  │ tremolo_speed    │ 0.0      │
  │ tremolo_depth    │ 0.0      │
  └──────────────────┴──────────┘

  FULL PATCH SCHEMA (all optional fields beyond defaults):
  {
    "name":        string,       // Display name
    "wave_type":   string,       // Primary oscillator: sine|square|sawtooth|triangle|noise
    "wave_type_2": string|null,  // Secondary oscillator (optional)
    "mix":         float,        // Osc blend ratio (0.0 = all wave1, 1.0 = all wave2)
    "duty_cycle":  float,        // Pulse width for square/pulse (0.0-1.0)
    "envelope": {
      "attack":        float,    // seconds
      "decay":         float,    // seconds
      "sustain_level": float,    // 0.0-1.0
      "release":       float     // seconds
    },
    "lfo": {
      "vibrato_speed":  float,   // Hz
      "vibrato_depth":  float,   // semitones
      "tremolo_speed":  float,   // Hz
      "tremolo_depth":  float    // 0.0-1.0
    },
    "portamento": {
      "slide_time":    float     // seconds
    },
    "saturation":  float,        // gain ≥1.0 (1.0 = clean)
    "bit_depth":   int,          // 4-16 (16 = clean)
    "echo": {
      "delay_time":    float,    // seconds
      "feedback":      float     // 0.0-0.9
    },
    "ring_mod": {
      "carrier_freq":  float,    // Hz
      "mix":           float     // 0.0-1.0
    }
  }

  save_instrument(name, parameters)
    Writes to presets/<sanitized_name>.json.

  load_instrument(name)
    Reads from presets/<name>.json, falls back to default patch if missing.

================================================================================
  7. SEQUENCER & RENDER PIPELINE (playback.py)
================================================================================

  CLASS: Sequencer(sample_rate=44100)
    Internal instances: Oscillator, Modifiers, PresetManager

  calculate_step_time(bpm, lines_per_beat=4)
    Returns seconds per step: (60 / bpm) / lpb
    Example: 120 BPM, 4 LPB → 0.125s per step (125ms)

  ── RENDER PIPELINE (render_pattern) ──

  For each track in the pattern:
    1. Initialize per-track mono mix buffer (float64)
    2. Get track-level patch (default or from bank)
    3. For each event in the sequence:

       a. NOTE OFF handling:
          - 5ms fade-out at OFF sample position
          - Silence remaining samples to prev_end_sample

       b. Per-event patch extraction:
          - Each event can override the track patch via its "patch" key
          - Extracts: envelope, LFO, portamento, wave types, mix,
            saturation, bit_depth, duty_cycle, echo, ring_mod params

       c. For each note in the event (supports chords as lists):

          i.   Convert MIDI → frequency via Theory.note_to_freq()
          ii.  Check FX for pitch modifiers:
               - PRT: Generate portamento slide from prev_freq
               - SUP: Pitch bend up via slide profile
               - SDN: Pitch bend down via slide profile
               - Default: Vibrato profile from LFO params
          iii. Generate primary waveform via Oscillator
          iv.  If dual oscillator: generate + blend wave_type_2
          v.   Accumulate into combined_wave

       d. Chord normalization: divide by √(num_notes) to prevent clipping

       e. Signal chain (in order):
          1. Saturation (soft clipping)
          2. Bitcrushing (resolution reduction)
          3. Tremolo (amplitude LFO)
          4. Patch-level Echo (delay line)
          5. Patch-level Ring Mod (carrier multiplication)
          6. ADSR Envelope (amplitude shaping)
          7. Per-step FX commands (_apply_fx_to_event)
          8. Velocity scaling

       f. Mix into track buffer with sample-accurate placement
          - Guard: copy_len = min(wave_len, buffer_remaining)

    4. Apply track volume automation (linear keyframe interpolation)
    5. Apply pan automation:
       - Generate pan envelope (-1.0 to +1.0)
       - Left gain  = clip(1.0 - pan, 0, 1)
       - Right gain = clip(1.0 + pan, 0, 1)
    6. Mix into stereo master buffer

  Master processing:
    - Apply master volume automation to both channels
    - Final brick-wall limiter: if max > 0.98, scale to 0.98
      - Per-pattern: used by Play Pattern / Solo Track
      - Project-wide: Play Song and Export render all patterns
        with apply_limiter=False, concatenate, then apply ONE
        global limiter pass. This preserves dynamics across sections.

  Output: float64 numpy array, shape (total_samples, 2)

================================================================================
  8. FX COMMAND REFERENCE
================================================================================

  FX commands are stored as strings in FX1/FX2 columns: "CMD XX"
  XX is a decimal byte (0-255). Some commands split into high/low nibbles.

  ┌─────┬──────────────┬──────────────────────────────────────────────────┐
  │ CMD │ Name         │ Parameters                                      │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ VIB │ Vibrato      │ Hi nibble = speed (0-15 → 1-16 Hz)             │
  │     │              │ Lo nibble = depth (0-15 → 0-1 semitone)         │
  │     │              │ Applied as amplitude modulation on the wave      │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ TRM │ Tremolo      │ Hi nibble = speed, Lo nibble = depth            │
  │     │              │ Calls Modifiers.apply_tremolo()                  │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ ECH │ Echo         │ Hi nibble = delay (× 50ms, range 0-750ms)       │
  │     │              │ Lo nibble = feedback (0-15 → 0.0-0.9)           │
  │     │              │ Calls Modifiers.apply_echo()                     │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ VOL │ Volume       │ Full byte 0-255 → 0.0-1.0 amplitude scale       │
  │     │              │ Directly multiplies the waveform                 │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ RNG │ Ring Mod     │ Full byte 0-255 → 0.0-1.0 carrier mix           │
  │     │              │ Fixed carrier at 500 Hz                          │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ CUT │ Note Cut     │ Full byte 0-255 → position in wave (0.0-1.0)    │
  │     │              │ 5ms fade-out at cut point, then silence          │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ ARP │ Arpeggio     │ SINGLE-NOTE MODE:                               │
  │     │              │   Hi = +X semitones, Lo = +Y semitones           │
  │     │              │   Cycles root → +X → +Y each 1/3 of note        │
  │     │              │ CHORD MODE (when note is a list):                │
  │     │              │   Hi = pattern (0=Up,1=Down,2=PingPong,3=Random) │
  │     │              │   Lo = subdivision count (2-16 divisions)        │
  │     │              │   Cycles through actual chord frequencies        │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ SUP │ Slide Up     │ Full byte 0-255 → 0-12 semitone bend up         │
  │     │              │ Pre-render: generates slide profile in freq loop │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ SDN │ Slide Down   │ Full byte 0-255 → 0-12 semitone bend down       │
  │     │              │ Pre-render: generates slide profile in freq loop │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ PRT │ Portamento   │ Full byte 0-255 → slide time 0.01-0.5s          │
  │     │              │ Pre-render: linear glide from prev_freq          │
  │     │              │ Requires a preceding note to have effect         │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ PAN │ Pan          │ 0 = hard left, 128 = center, 255 = hard right   │
  │     │              │ Extracted into pan_automation keyframes by       │
  │     │              │ _build_tracks_from_grid before render.           │
  │     │              │ Works on note rows AND empty rows (sweeps).      │
  │     │              │ See Section 14: Stereo Panning System.           │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ DTN │ Detune       │ Full byte 0-255 → detune amount in cents         │
  │     │              │ Resamples to shift pitch by 0-50 cents           │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ DLY │ Delay        │ Full byte 0-255 → delay note start position      │
  │     │              │ Shifts waveform start within the step            │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ SAT │ Saturation   │ Full byte 0-255 → gain 1.0-5.0                  │
  │     │              │ Global soft clipping via tanh                   │
  ├─────┼──────────────┼──────────────────────────────────────────────────┤
  │ RTG │ Retrigger    │ Full byte 0-255 → 1-32 Hz stutter rate          │
  │     │              │ Post-render: chops audio via square wave gate   │
  └─────┴──────────────┴──────────────────────────────────────────────────┘

  FX PROCESSING ORDER:
    SUP/SDN/PRT are processed BEFORE waveform generation (in the freq loop).
    All other FX are applied AFTER waveform generation via _apply_fx_to_event.
    Two FX commands can be active simultaneously (FX1 + FX2).

================================================================================
  9. CHORD SYSTEM & ARPEGGIATOR
================================================================================

  NOTATION:
    Single note:  C-4          → MIDI integer
    Chord:        C-4,E-4,G-4  → List of MIDI integers [60, 64, 67]
    Commas separate notes, no spaces.

  RENDERING:
    _build_tracks_from_grid() in tracker.py parses comma-separated notation.
    When "note" is a list, render_pattern iterates each tone:
      for note in notes:
          wave += osc.generate(freq(note), duration)
    Chord normalization: combined /= √(len(notes)) to maintain headroom.

  CHORD ARP (when ARP FX is applied to a chord event):
    The engine detects isinstance(notes, list) and switches ARP behavior.
    Instead of semitone offsets, it cycles through the chord's own frequencies.

    Encoding: ARP XY
      X (high nibble) = Pattern:
        0 = Up         (low to high: C → E → G → C → E → G ...)
        1 = Down       (high to low: G → E → C → G → E → C ...)
        2 = Ping-Pong  (up then down: C → E → G → E → C → E ...)
        3 = Random     (deterministic shuffle seeded by note sum)
      Y (low nibble) = Subdivision count (0 defaults to len(chord) × 2)

    Each subdivision generates a fresh oscillator segment at that frequency,
    concatenated into the final waveform to replace the static chord.

  RIGHT-CLICK PRESETS (context menu auto-detects chord):
    Chord present:
      ↑ Up (fast)     ARP 04    ↑ Up (slow)       ARP 08
      ↓ Down (fast)   ARP 14    ↓ Down (slow)     ARP 18
      ↕ Ping-Pong     ARP 24    ↕ Ping-Pong (slow) ARP 28
      🎲 Random       ARP 34    🎲 Random (slow)   ARP 38

    No chord (semitone mode):
      Minor 3+5       ARP 55    Major 3+5          ARP 71
      Octave          ARP 12    Power 5+Oct        ARP 124

  AVAILABLE CHORD SHAPES (via Chords submenu):
  ┌─────────┬────────────────┬────────────────────────┐
  │ Shape   │ Intervals      │ Example (C-4 root)     │
  ├─────────┼────────────────┼────────────────────────┤
  │ Major   │ [0, 4, 7]      │ C-4, E-4, G-4         │
  │ Minor   │ [0, 3, 7]      │ C-4, D#4, G-4         │
  │ 7th     │ [0, 4, 7, 10]  │ C-4, E-4, G-4, A#4    │
  │ Min7    │ [0, 3, 7, 10]  │ C-4, D#4, G-4, A#4    │
  │ Maj7    │ [0, 4, 7, 11]  │ C-4, E-4, G-4, B-4    │
  │ Sus4    │ [0, 5, 7]      │ C-4, F-4, G-4         │
  │ Sus2    │ [0, 2, 7]      │ C-4, D-4, G-4         │
  │ Dim     │ [0, 3, 6]      │ C-4, D#4, F#4         │
  │ Aug     │ [0, 4, 8]      │ C-4, E-4, G#4         │
  └─────────┴────────────────┴────────────────────────┘

  Each chord shape in the context menu offers:
    - 🎵 Full (all notes)
    - ⚡ Root+Last (power voicing)
    - 🔗 Root+2nd (dyad)
    - Individual notes labeled by interval (R, 3, ♭3, 5, ♭5, etc.)

  FX CONFLICT NOTES:
    - ARP + Chord: Fully supported — cycles chord notes (see above)
    - PRT + Chord: Warning shown — each note glides independently (can sound
      muddy, but artistically usable). Not blocked.

================================================================================
  10. CSV FILE FORMAT (V1.1) — CsvHandler (csv_handler.py)
================================================================================

  The project file is a standard RFC 4180 CSV written via Python's csv module.
  Extension: .csv (tracker projects) or .sfx.csv (SFX canvas).
  All values are strings. No binary data. Human-readable and diff-friendly.

  CLASS: CsvHandler (all static methods)

  ══════════════════════════════════════════════════════════════════
  10.1  FILE STRUCTURE OVERVIEW
  ══════════════════════════════════════════════════════════════════

  A V1.1 project file has exactly 4 sections, always in this order:

    ┌──────────────────────────────────────────────────────────────┐
    │  Section 1: GLOBAL HEADER        (exactly 1 row)            │
    │  Section 2: PATCHES              (0..N rows, tag: PATCH)    │
    │  Section 3: ORDER LIST           (marker + SEQ rows)        │
    │  Section 4: PATTERNS             (marker + PATTERN/EVENT)   │
    └──────────────────────────────────────────────────────────────┘

  Section markers are full CSV rows used as delimiters:
    "--- ORDER LIST ---",SeqIndex,PatternID
    "--- PATTERNS ---",Type,ID,Length

  ══════════════════════════════════════════════════════════════════
  10.2  SECTION 1: GLOBAL HEADER
  ══════════════════════════════════════════════════════════════════

  Row 0 (always the first row in the file):

    LANTHORN_V1.1, TotalTracks, SubColumns, BPM, LPB, Key, Mode, LPM

  ┌──────────────┬──────┬────────────────────────────────────────────┐
  │ Field        │ Type │ Description                                │
  ├──────────────┼──────┼────────────────────────────────────────────┤
  │ LANTHORN_V1.1│ str  │ Magic identifier + version tag             │
  │ TotalTracks  │ int  │ Number of track groups (default 8)          │
  │ SubColumns   │ int  │ Columns per track (always 7)                │
  │ BPM          │ int  │ Beats per minute                            │
  │ LPB          │ int  │ Lines (steps) per beat                      │
  │ Key          │ str  │ Musical root: C, C#, D, ... B               │
  │ Mode         │ str  │ Scale: Chromatic, Major, Minor, etc.        │
  │ LPM          │ int  │ Lines per measure (default 16). Determines  │
  │              │      │ beat highlighting: 12 = 3/4 time, 16 = 4/4 │
  └──────────────┴──────┴────────────────────────────────────────────┘

  Example:  LANTHORN_V1.1,8,7,140,4,D,Minor,16    (4/4 time)
            LANTHORN_V1.1,4,7,120,4,C,Major,12    (3/4 time)

  On load, the header values are applied to:
    - tracker_widget.current_tracks, tracker_widget.sub_cols
    - main_window.spin_bpm, main_window.spin_lpb, main_window.spin_lpm
    - tracker_widget.theory_engine.combo_root / combo_mode
    - LPM defaults to 16 if missing (backward compatible with pre-LPM files)

  ══════════════════════════════════════════════════════════════════
  10.3  SECTION 2: PATCHES (Embedded Instruments)
  ══════════════════════════════════════════════════════════════════

  Row format:  PATCH, InstrumentName, "{JSON}"

  SAVE BEHAVIOR — Instrument Scanning:
    Before writing, save_project scans ALL patterns across ALL rows
    to collect every unique instrument name referenced in Inst columns:
      for each pattern → for each row → for each track:
        inst = row_data[col_base + 1]
        if inst is not "---" or empty → add to used_instruments set

    Only instruments found in the set AND present in bank_data are written.
    This keeps files lean — unused instruments are not serialized.

  JSON CONTENT — Full patch dictionary as a single JSON string.
    The JSON is written as one CSV field (quoted by csv.writer).
    Contains all parameters from the patch schema (see Section 6).

  Example row:
    PATCH,BassLead,"{""name"": ""BassLead"", ""wave_type"": ""sawtooth"",
    ""duty_cycle"": 0.5, ""attack"": 0.02, ""decay"": 0.15, ...}"

  LOAD BEHAVIOR:
    - Parsed via json.loads(row_data[2])
    - Stored directly into bank_data[inst_name]
    - On parse failure: prints warning, skips patch (no crash)

  ══════════════════════════════════════════════════════════════════
  10.4  SECTION 3: ORDER LIST
  ══════════════════════════════════════════════════════════════════

  Section marker:   --- ORDER LIST ---,SeqIndex,PatternID
  Data rows:        SEQ, Index, PatternID

  ┌──────┬──────┬────────────────────────────────────────────────────┐
  │ Tag  │ Idx  │ PatternID                                          │
  ├──────┼──────┼────────────────────────────────────────────────────┤
  │ SEQ  │ 0    │ A                                                  │
  │ SEQ  │ 1    │ B                                                  │
  │ SEQ  │ 2    │ A                                                  │
  │ SEQ  │ 3    │ C                                                  │
  └──────┴──────┴────────────────────────────────────────────────────┘

  - Index is 0-based and sequential (written for readability, not used on load)
  - PatternID references a pattern defined in Section 4
  - Patterns CAN repeat (verse-chorus-verse structures)
  - On load: each SEQ row appends row_data[2] to order_list[]

  ══════════════════════════════════════════════════════════════════
  10.5  SECTION 4: PATTERNS & EVENTS
  ══════════════════════════════════════════════════════════════════

  Section marker:   --- PATTERNS ---,Type,ID,Length

  PATTERN HEADER:   PATTERN, PatternID, StepCount [, BPM, LPB, LPM, Key, Mode]
    - Declares a new pattern with its ID and total number of steps
    - Optional BPM/LPB/LPM/Key/Mode fields override the global header values
    - If omitted, the pattern inherits the global (toolbar) values
    - On load: initializes an empty grid; stores overrides in pattern_meta
    - Example: PATTERN,B,60,100,4,20,D,Phrygian

  EVENT DATA:       EVENT, Row, Track, Note, Inst, Vel, Gate, FX1, FX2

  ┌───────┬──────┬────────────────────────────────────────────────────┐
  │ Field │ Idx  │ Description                                        │
  ├───────┼──────┼────────────────────────────────────────────────────┤
  │ EVENT │  0   │ Row tag (literal "EVENT")                           │
  │ Row   │  1   │ 0-indexed step number within the pattern            │
  │ Track │  2   │ 0-indexed track number                              │
  │ Note  │  3   │ "C-4", "G#5", "OFF", "C-4,E-4,G-4", or ""         │
  │ Inst  │  4   │ Instrument name from bank, or ""                    │
  │ Vel   │  5   │ Decimal velocity "0"-"127", or "" for default       │
  │ Gate  │  6   │ Decimal gate length in steps, or ""                  │
  │ FX1   │  7   │ FX command string "VIB 68", or ""                   │
  │ FX2   │  8   │ FX command string, or ""                            │
  └───────┴──────┴────────────────────────────────────────────────────┘

  SPARSE STORAGE:
    Events are only written when at least one field in the track row is
    non-empty (not "---", "--", or ""). This dramatically reduces file size
    for patterns with many empty steps.

    Check logic:
      any(v and v not in ["---", "--", ""] for v in [note, inst, vel, gate, fx1, fx2])

    A 64-step, 8-track pattern with 12 events produces ~12 EVENT rows
    instead of 512 (64 × 8).

  ══════════════════════════════════════════════════════════════════
  10.6  SAVE PIPELINE (save_project)
  ══════════════════════════════════════════════════════════════════

  Called from: MainWindow → File → Save / Ctrl+S
  Signature: CsvHandler.save_project(filepath, tracker_widget, bank_data,
                                      bpm, lpb, key, mode, lpm)
  Returns: (bool success, str message)

  Per-pattern timing:
    If pattern_meta[pat_id] contains BPM/LPB/LPM overrides, they are
    appended to the PATTERN row: PATTERN,A,48,140,4,12
    Patterns without overrides write only: PATTERN,A,48

  Step-by-step:

  1. PERSIST CURRENT GRID
     tracker_widget.save_grid_to_pattern()
     Flushes the visible QTableWidget cells into the in-memory
     patterns[active_pattern] grid before serializing.

  2. WRITE HEADER
     csv.writer writes 1 row: version tag + global settings.

  3. SCAN & WRITE PATCHES
     Iterate ALL patterns → ALL rows → ALL tracks.
     For each cell at col_base+1 (Inst column):
       if non-empty and non-placeholder → add to used_instruments set.
     For each used instrument found in bank_data:
       write PATCH row with json.dumps(patch_dict).

  4. WRITE ORDER LIST
     Write section marker row.
     Enumerate tracker_widget.order_list → write SEQ rows.

  5. WRITE PATTERNS
     Write section marker row.
     For each pattern ID (sorted alphabetically):
       a. Write PATTERN header: [PATTERN, pid, step_count]
       b. Get grid data from tracker_widget.patterns[pid]
       c. For each row (up to step_count):
          For each track:
            Extract 6 cell values (Note, Inst, Vel, Gate, FX1, FX2)
            If any cell has real data → write EVENT row

  6. RETURN (True, "Project saved successfully.")
     On exception → return (False, error_message)

  ══════════════════════════════════════════════════════════════════
  10.7  LOAD PIPELINE (load_project)
  ══════════════════════════════════════════════════════════════════

  Called from: MainWindow → File → Open / Ctrl+O
  Signature: CsvHandler.load_project(filepath, tracker_widget, bank_data)
  Returns: (bool success, str message)

  Step-by-step:

  1. VALIDATE FILE
     Check existence, read all rows, verify row[0][0] == "LANTHORN_V1.1".

  2. PARSE HEADER (row 0)
     Extract: current_tracks, sub_cols, bpm, lpb, key, mode.
     Apply to MainWindow spinners and Theory engine combos.
     Set tracker_widget.current_tracks and sub_cols.

  3. STATE MACHINE PARSER
     Initial state: "PATCHES"

     ┌─────────────┐    "--- ORDER LIST ---"    ┌────────┐
     │   PATCHES   │ ──────────────────────────► │ ORDER  │
     └─────────────┘                             └────┬───┘
                                                      │
                       "--- PATTERNS ---"              │
                    ┌──────────────────────────────────┘
                    ▼
              ┌──────────┐
              │ PATTERNS │
              └──────────┘

     For each row after the header:
       - If tag is a section marker → update state
       - If tag == "PATCH":
           Parse JSON, store in bank_data[name]
       - If state == "ORDER" and tag == "SEQ":
           Append pattern ID to order_list
       - If state == "PATTERNS" and tag == "PATTERN":
           Record active_pattern_id and step count
           Initialize empty grid (placeholder values)
       - If state == "PATTERNS" and tag == "EVENT":
           Validate row/track indices against bounds
           Write cell values into grid[row][col_base + offset]

  4. GRID INITIALIZATION (on PATTERN header)
     Created per-pattern with dimensions: step_count × (tracks × sub_cols)
     Default cell values by column type:
       col % 7 in [0, 1] → "---"  (Note/Inst placeholder)
       col % 7 in [2..5]  → "--"  (Vel/Gate/FX placeholder)
       col % 7 == 6       → ""    (Spacer)

  5. EVENT CELL MAPPING
     EVENT row maps to grid as follows:
       row_idx   = int(row_data[1])
       trk_idx   = int(row_data[2])
       col_base  = trk_idx × sub_cols

       grid[row_idx][col_base + 0] = Note  (row_data[3])
       grid[row_idx][col_base + 1] = Inst  (row_data[4])
       grid[row_idx][col_base + 2] = Vel   (row_data[5])
       grid[row_idx][col_base + 3] = Gate  (row_data[6])
       grid[row_idx][col_base + 4] = FX1   (row_data[7])
       grid[row_idx][col_base + 5] = FX2   (row_data[8])

     Only non-empty strings overwrite the placeholder defaults.

  6. APPLY TO TRACKER
     Set: tracker_widget.patterns, pattern_lengths, order_list, active_pattern
     Rebuild pattern_combo dropdown with all loaded pattern IDs (sorted).
     Load the first pattern in the order list into the visible grid.
     Refresh order display and button states.

  7. RETURN (True, "Project loaded successfully.")
     On exception → return (False, error_message)

  ══════════════════════════════════════════════════════════════════
  10.8  EDGE CASES & VALIDATION
  ══════════════════════════════════════════════════════════════════

  - Missing header fields: BPM/LPB/Key/Mode default to 120/4/C/Chromatic
  - Row out of bounds: EVENT with row ≥ pattern length → skipped silently
  - Track out of bounds: EVENT with track ≥ current_tracks → skipped
  - Bad patch JSON: json.JSONDecodeError → prints warning, continues
  - Empty cells in EVENT: only non-empty strings overwrite defaults
  - File doesn't exist: returns (False, "File does not exist.")
  - Wrong version tag: returns (False, "Invalid or unsupported...")
  - Empty order_list or pattern_lengths after parse: returns error

  ══════════════════════════════════════════════════════════════════
  10.9  RAW CSV EXAMPLE
  ══════════════════════════════════════════════════════════════════

  LANTHORN_V1.1,8,7,120,4,C,Minor
  PATCH,Lead,"{""name"": ""Lead"", ""wave_type"": ""sawtooth"", ""attack"": 0.02, ""decay"": 0.1, ""sustain_level"": 0.6, ""release"": 0.2}"
  PATCH,Bass,"{""name"": ""Bass"", ""wave_type"": ""square"", ""duty_cycle"": 0.3, ""attack"": 0.01, ""decay"": 0.15, ""sustain_level"": 0.7, ""release"": 0.1}"
  --- ORDER LIST ---,SeqIndex,PatternID
  SEQ,0,A
  SEQ,1,B
  SEQ,2,A
  --- PATTERNS ---,Type,ID,Length
  PATTERN,A,16
  EVENT,0,0,C-4,Lead,100,04,VIB 36,
  EVENT,0,1,C-3,Bass,127,08,,
  EVENT,4,0,E-4,Lead,100,04,,
  EVENT,4,1,C-3,Bass,127,08,,
  EVENT,8,0,G-4,Lead,100,04,,ECH 68
  EVENT,8,1,C-3,Bass,127,08,,
  EVENT,12,0,C-4,E-4,G-4,,100,04,ARP 4,
  EVENT,12,1,OFF,,,,
  PATTERN,B,16
  EVENT,0,0,D-4,Lead,96,04,,
  EVENT,4,0,F-4,Lead,96,04,,
  EVENT,8,0,A-4,Lead,96,04,,
  EVENT,12,0,OFF,,,,,

  Note: Row 12, Track 0 in Pattern A shows a chord (C-4,E-4,G-4) with
  chord ARP (ARP 04 = Up pattern, 4 subdivisions).

================================================================================
  11. PATTERN SYSTEM & ORDER LIST
================================================================================

  PATTERN IDs:
    Single letter: A-Z (26)
    Double letter: AA-AZ, BA-BZ, ... ZA-ZZ (26 × 26 = 676)
    Total capacity: 702 patterns

    Generated by _next_pattern_id() which scans existing IDs and returns
    the next unused ID in sequence.

  PATTERN LENGTH:
    Each pattern has an independent step count (1-256 steps, default 64).
    Stored in pattern_lengths[pid] and editable via the Steps spinner.

  ORDER LIST:
    A list of pattern IDs defining the song's playback order.
    Displayed as a horizontal QListWidget with auto-scroll and
    real-time highlighting of the currently playing pattern.

  PATTERN OPERATIONS (toolbar + context):
    - New Pattern: creates empty pattern with next available ID
    - Clone Pattern: deep-copies active pattern to new ID
    - Delete Pattern: removes from patterns dict and order list
    - + Seq / - Seq: append/remove patterns from the order list
    - SeqEdit: opens the Sequence Editor dialog for full control

  SEQUENCE EDITOR (SeqEdit button):
    Opens a drag-and-drop dialog listing all patterns in play order.
    Each entry displays: PatternID, BPM, time signature, key/mode, step count.
    Actions:
      - Drag & drop to reorder
      - ▲ Up / ▼ Down buttons to move entries
      - Add: append a pattern to the end
      - Insert: insert a pattern above the selection
      - Duplicate: copy the selected entry below itself
      - Remove: delete the selected entry (minimum 1 kept)
      - Apply: commit new order to the song
      - Cancel: discard changes
      - Double-click: jump to that pattern in the tracker

================================================================================
  12. TRACK COLUMN LAYOUT
================================================================================

  Each track consists of sub_cols = 7 columns:

  ┌─────┬──────┬────────────────────────────────────────────────────┐
  │ Col │ Type │ Content                                            │
  ├─────┼──────┼────────────────────────────────────────────────────┤
  │  0  │ Note │ Note name or chord: C-4, G#5, OFF, C-4,E-4,G-4   │
  │  1  │ Inst │ Instrument name from bank (overrides track patch)  │
  │  2  │ Vel  │ Velocity in hex: 00-FF (maps to 0.0-1.0)          │
  │  3  │ Gate │ Gate length in hex steps (how long note sustains)  │
  │  4  │ FX1  │ FX command slot 1 (e.g., VIB 3A)                  │
  │  5  │ FX2  │ FX command slot 2 (e.g., ECH 35)                  │
  │  6  │ Spc  │ Visual spacer (1px, non-editable, dark)            │
  └─────┴──────┴────────────────────────────────────────────────────┘

  Default empty values: "---" (Note/Inst), "--" (Vel/Gate/FX), "" (Spacer)

  MULTI-INSTRUMENT TRACKS:
    Each event carries its own patch dictionary via the "patch" key.
    When the Inst column specifies a bank instrument, that patch is embedded
    in the event dict. The render loop extracts per-event patch parameters,
    so different instruments on the same track play correctly.

================================================================================
  13. PLAYBACK MODES
================================================================================

  ┌─────────────────┬────────────────────────────────────────────────┐
  │ Mode            │ Behavior                                       │
  ├─────────────────┼────────────────────────────────────────────────┤
  │ Play Song       │ Renders all patterns in order list sequentially │
  │                 │ Concatenates audio, advances playhead globally  │
  ├─────────────────┼────────────────────────────────────────────────┤
  │ Play Pattern    │ Renders only the active (selected) pattern      │
  │                 │ Playhead wraps within pattern boundaries        │
  ├─────────────────┼────────────────────────────────────────────────┤
  │ Solo Track      │ Renders one track from the active pattern       │
  │                 │ Other tracks are muted                          │
  ├─────────────────┼────────────────────────────────────────────────┤
  │ Stop            │ Halts playback, clears playhead, resets viz     │
  │ Pause           │ Freezes playhead timer without resetting        │
  └─────────────────┴────────────────────────────────────────────────┘

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

================================================================================
  14. STEREO PANNING SYSTEM
================================================================================

  The engine renders in full stereo. Each track is mixed mono, then placed
  into the stereo field via sample-accurate pan automation.

  ══════════════════════════════════════════════════════════════════
  14.1  PAN FX ENCODING
  ══════════════════════════════════════════════════════════════════

  PAN is an FX column command with a single hex byte:

    PAN XX    where XX = 00-FF

    ┌──────┬──────────────┬─────────────────────┐
    │ Hex  │ Float Value  │ Position            │
    ├──────┼──────────────┼─────────────────────┤
    │  00  │  -1.0        │ Hard Left           │
    │  40  │  -0.5        │ Mid-Left            │
    │  80  │   0.0        │ Center (default)    │
    │  C0  │  +0.5        │ Mid-Right           │
    │  FF  │  +1.0        │ Hard Right          │
    └──────┴──────────────┴─────────────────────┘

    Conversion: pan_float = (hex_val / 127.5) - 1.0

  Context menu presets (right-click FX cell → Dynamics → Pan):
    Hard Left, Left, Center, Right, Hard Right, Custom slider.

  ══════════════════════════════════════════════════════════════════
  14.2  PAN EXTRACTION PIPELINE
  ══════════════════════════════════════════════════════════════════

  PAN is NOT processed by _apply_fx_to_event. Instead, it is extracted
  during track building and converted to pan_automation keyframes.

  In _build_tracks_from_grid (tracker.py):

    1. STANDALONE SCAN — Before the note-check skip:
       For each row with NO note, check FX1/FX2 for "PAN XX".
       If found → append {step: row, value: float} to _standalone_pan.
       This enables pan sweeps on rows without retriggering sound.

    2. EVENT SCAN — After building the full event sequence:
       For each event with fx1 or fx2 starting with "PAN ":
         - Extract hex value → convert to float
         - Add to pan_keyframes list
         - DELETE the PAN FX from the event dict
           (prevents engine's _apply_fx_to_event from seeing it)

    3. MERGE — Combine both lists, sort by step:
         all_pan = (pan_keyframes + _standalone_pan).sort(by step)

    4. INJECT — If any keyframes exist:
         track_dict["pan_automation"] = all_pan

  SIGNAL PATH:
    ┌──────────┐     ┌──────────────┐     ┌────────────────┐
    │ FX Cell  │ ──► │ Track Build  │ ──► │ pan_automation  │
    │ "PAN 40" │     │ (extraction) │     │ keyframes list  │
    └──────────┘     └──────────────┘     └───────┬────────┘
                                                  │
                     ┌──────────────┐     ┌───────▼────────┐
                     │ Stereo Mix   │ ◄── │ Pan Envelope   │
                     │ L/R buffers  │     │ (np.interp)    │
                     └──────────────┘     └────────────────┘

  ══════════════════════════════════════════════════════════════════
  14.3  PAN ENVELOPE GENERATION
  ══════════════════════════════════════════════════════════════════

  METHOD: Sequencer._generate_pan_envelope(total_samples, keyframes, step_dur)

  Converts step-based keyframes into a sample-accurate float array.

  Algorithm:
    1. Convert each keyframe: sample_pos = step × step_dur × sample_rate
    2. Build xp (sample positions) and fp (pan values) arrays
    3. Use np.interp(x, xp, fp) for linear interpolation
       - Before first keyframe: holds first value
       - After last keyframe: holds last value
       - Between keyframes: smooth linear transition
    4. Clip result to [-1.0, +1.0]

  Returns: float64 array, shape (total_samples,)

  If no pan_automation exists on a track:
    Falls back to static pan = track.get("pan", 0.0)
    Generates a constant envelope at that value.

  ══════════════════════════════════════════════════════════════════
  14.4  STEREO MIX MATH
  ══════════════════════════════════════════════════════════════════

  After the pan envelope is generated, each track's mono buffer
  is placed into the stereo master via:

    left_gains  = clip(1.0 - pan_env, 0.0, 1.0)
    right_gains = clip(1.0 + pan_env, 0.0, 1.0)

    master_mix[:, 0] += track_mono × left_gains
    master_mix[:, 1] += track_mono × right_gains

  This is a LINEAR PANNING LAW:
    - Pan  0.0 (center): left = 1.0, right = 1.0  (full both)
    - Pan -1.0 (left):   left = 2.0→clip→1.0, right = 0.0
    - Pan +1.0 (right):  left = 0.0, right = 2.0→clip→1.0
    - Pan -0.5 (mid-L):  left = 1.0, right = 0.5

  ══════════════════════════════════════════════════════════════════
  14.5  USAGE PATTERNS
  ══════════════════════════════════════════════════════════════════

  STATIC PAN:
    Place "PAN 00" on row 0, track 2 → track stays hard left.
    No other PAN needed — envelope holds last value.

  PAN SWEEP:
    Row 0:  PAN 00  (start left)
    Row 32: PAN FF  (end right)
    Engine interpolates smoothly across 32 steps.

  PING-PONG RHYTHM:
    Row 0:  PAN 20       (left)
    Row 4:  PAN E0       (right)
    Row 8:  PAN 20       (left)
    Row 12: PAN E0       (right)
    Creates alternating stereo pattern.

  CENTER RESET:
    Place "PAN 80" to return any track to center.

  NO PAN FX:
    Track defaults to center (pan = 0.0). Unchanged from pre-stereo behavior.

  PAN ON EMPTY ROWS:
    PAN commands on rows with no note still work.
    Enables gradual stereo repositioning without retriggering sound.

  CSV PERSISTENCE:
    PAN commands are stored in FX1/FX2 columns like any other FX.
    No special CSV handling needed — "PAN 40" persists and loads normally.

================================================================================
  16. KEYBOARD SHORTCUTS
================================================================================

  ┌─────────────────────┬──────────────────────────────────────────────┐
  │ Shortcut            │ Action                                       │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │                     │  FILE MANAGEMENT                             │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │ Ctrl+N              │ New Project — resets all patterns/tracks     │
  │ Ctrl+O              │ Open Project — loads .csv project file       │
  │ Ctrl+S              │ Quick Save — saves to last used path         │
  │ Ctrl+Q              │ Quit — exit the application                  │
  │ F1                  │ Help — open keyboard shortcut reference      │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │                     │  EDITING                                     │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │ Delete / Backspace  │ Clear selected cells to defaults             │
  │                     │   Note/Inst → "---", Vel/Gate/FX → "--"      │
  │ Ctrl+Z              │ Undo last edit                               │
  │ Ctrl+Y              │ Redo last undone edit                        │
  │ Ctrl+L              │ Loop Selection — clones selected block       │
  │                     │   prompts for repeat count (2-32×)           │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │                     │  FX COLUMNS (Enter key)                      │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │ Enter               │ Opens FX Interpolation Sweep dialog          │
  │                     │   Select a range of FX cells, press Enter,   │
  │                     │   set start/end values → linear sweep fills  │
  │                     │   the selected cells with interpolated FX    │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │                     │  GRID NAVIGATION                             │
  ├─────────────────────┼──────────────────────────────────────────────┤
  │ Arrow Keys          │ Move cursor in grid                          │
  │ Shift+Click         │ Range select (contiguous block)              │
  │ Ctrl+Click          │ Multi-select (non-contiguous cells)          │
  │ Right-Click         │ Context menu (column-aware)                  │
  └─────────────────────┴──────────────────────────────────────────────┘

================================================================================
  17. CONTEXT MENUS (Right-Click)
================================================================================

  The context menu is column-aware — its contents change based on which
  column type you right-click. Some sections appear on every column type.

  ══════════════════════════════════════════════════════════════════
  17.1  COMMON SECTIONS (always visible)
  ══════════════════════════════════════════════════════════════════

  ▶ Play...
    ├── ▶ Play Song (full order list)
    ├── ▶ Play Pattern [current]
    ├── ▶ Solo Track [N]
    └── ⏹ Stop

  📋 Copy Selected Cells
  📌 Paste

  🧠 Smart Edit (see Section 18 for details)
    ├── 🔗 Edit Similar (same patch)
    │     ├── 🔊 Set Velocity on all
    │     ├── ⏱  Set Gate on all
    │     ├── ✨ Set FX1 on all
    │     └── 🗑  Clear FX1 on all
    ├── 🎯 Select all '[patch]' rows
    └── 🔄 Fill Pattern (repeat selection)

  🗑 Clear Selected Cells

  ══════════════════════════════════════════════════════════════════
  17.2  NOTE COLUMN (col_type = 0)
  ══════════════════════════════════════════════════════════════════

  ⏹ Insert OFF — Inserts note-off command

  Octave 2..7 — Submenu of all 12 chromatic notes per octave
    C-4, C#4, D-4, D#4, E-4, F-4, F#4, G-4, G#4, A-4, A#4, B-4

  🎵 Chords — Full chord builder (see Section 9)
    Octave 3..6 → Root Note → Chord Shape
      Full, Wide, Power, Dyad voicings + individual interval notes

  ══════════════════════════════════════════════════════════════════
  17.3  INSTRUMENT COLUMN (col_type = 1)
  ══════════════════════════════════════════════════════════════════

  🎹 Patches — Folder-organized instrument browser
    ├── 📁 bass/
    │     ├── 🎹 Acid Bass
    │     ├── 🎹 Grit Bass
    │     ├── 🎹 Pluck Bass
    │     ├── 🎹 SlapBass
    │     ├── 🎹 Sub Bass
    │     └── 🎹 Wobble Bass
    ├── 📁 drums/
    │     ├── 🎹 BazaarKick
    │     ├── 🎹 BazaarSnare
    │     ├── 🎹 Clap
    │     ├── 🎹 HiHat Closed
    │     └── 🎹 HiHat Open
    ├── 📁 keys/
    │     ├── 🎹 Bell
    │     ├── 🎹 Crystal Keys
    │     ├── 🎹 Organ
    │     ├── 🎹 PanFlute
    │     └── 🎹 Pluck
    ├── 📁 leads/
    │     ├── 🎹 Chip Lead
    │     ├── 🎹 Expressive Lead
    │     ├── 🎹 Saw Lead
    │     └── 🎹 Scream Lead
    ├── 📁 pads/
    │     ├── 🎹 Choir Pad
    │     ├── 🎹 Dark Pad
    │     ├── 🎹 Glass Pad
    │     ├── 🎹 Hollow Wind
    │     ├── 🎹 Spooky Pad
    │     └── 🎹 Warm Pad
    └── 📁 strings/
          ├── 🎹 Pulse String
          └── 🎹 String

  Clicking any patch inserts its name into the selected Inst cells.
  Folders mirror the presets/ directory structure. User-created folders
  and patches appear automatically.

  ══════════════════════════════════════════════════════════════════
  17.4  VELOCITY COLUMN (col_type = 2)
  ══════════════════════════════════════════════════════════════════

  Preset velocity levels:
    🔊 Pianissimo (pp)    → 20
    🔊 Piano (p)          → 40
    🔊 Mezzo-forte (mf)   → 60
    🔊 Forte (f)          → A0
    🔊 Fortissimo (ff)    → CC
    🔊 Maximum            → FF

  ══════════════════════════════════════════════════════════════════
  17.5  GATE COLUMN (col_type = 3)
  ══════════════════════════════════════════════════════════════════

  Preset gate lengths:
    ⏱ 1 step   → 01
    ⏱ 2 steps  → 02
    ⏱ 4 steps  → 04
    ⏱ 8 steps  → 08
    ⏱ 16 steps → 10

  ══════════════════════════════════════════════════════════════════
  17.6  FX COLUMNS (col_type = 4 or 5)
  ══════════════════════════════════════════════════════════════════

  Organized by category with preset values per command:

  🎵 Pitch
    Arpeggio (ARP)  — context-aware presets based on chord detection
    Slide Up (SUP)  — Subtle/Medium/Deep/Full Octave
    Slide Down (SDN)— Subtle/Medium/Deep/Full Octave
    Portamento (PRT)— Fast/Medium/Slow/Very Slow
    Detune (DTN)    — Slight/Warm/Wide/Extreme

  🌊 Modulation
    Vibrato (VIB)   — Light/Medium/Heavy/Wobble
    Tremolo (TRM)   — Soft/Rhythmic/Choppy/Aggressive

  🔊 Dynamics
    Volume (VOL)    — Silent/Quiet/Half/Full
    Echo (ECH)      — Subtle/Medium/Wide/Big
    Note Cut (CUT)  — Quick/Half/Late
    Pan (PAN)       — Hard L/Left/Center/Right/Hard R

  🔧 Timbral
    Ring Mod (RNG)  — Light/Medium/Heavy/Max
    Retrigger (RTG) — Sixteenths/Fast/Medium/Slow

  Each FX also has: 🎛 Custom... → opens dial with real-time preview

  ══════════════════════════════════════════════════════════════════
  17.7  INSTRUMENT BANK CONTEXT MENU (Workbench)
  ══════════════════════════════════════════════════════════════════

  Right-click on the preset tree widget:
    ➕ New Instrument  — saves current knobs as new preset
    📁 New Folder      — creates a category subfolder
    📂 Load to Editor  — recalls preset into knobs
    💾 Store from Editor — overwrites preset with current knobs
    📋 Duplicate       — creates a copy of the selected preset
    🗑 Delete          — removes preset from bank and disk
    💽 Save to Disk    — force-writes preset JSON to disk

================================================================================
  18. SMART EDIT TOOLS (🧠)
================================================================================

  The Smart Edit submenu appears on every right-click when a row with
  a valid instrument is under the cursor. All operations are scoped to
  the current track within the current pattern.

  ══════════════════════════════════════════════════════════════════
  18.1  EDIT SIMILAR (🔗)
  ══════════════════════════════════════════════════════════════════

  PURPOSE:
    Batch-edit a property on every row that uses the same instrument.

  HOW IT WORKS:
    1. Right-click any row that has a patch (e.g., "BazaarKick")
    2. 🧠 Smart Edit → 🔗 Edit Similar (BazaarKick)
    3. Choose what to change:
       - 🔊 Set Velocity on all → pick preset → every kick gets that velocity
       - ⏱  Set Gate on all → pick preset → every kick gets that gate length
       - ✨ Set FX1 on all → pick an FX command → enter hex param → applied
       - 🗑  Clear FX1 on all → clears FX1 on every kick row to "--"

  IMPLEMENTATION:
    Scans table_widget.rowCount() rows. For each row, checks the Inst
    column (track_base + 1). If the text matches the target patch name,
    writes the new value to the specified column with appropriate color.

  EXAMPLE WORKFLOW — "All snares need gate 02":
    1. Right-click any snare row
    2. 🧠 Smart Edit → 🔗 Edit Similar (BazaarSnare) → ⏱ Set Gate → 2 steps
    3. Every snare event in the track now has gate "02"

  ══════════════════════════════════════════════════════════════════
  18.2  SELECT SIMILAR (🎯)
  ══════════════════════════════════════════════════════════════════

  PURPOSE:
    Highlight all rows that use the same patch for manual editing.

  HOW IT WORKS:
    1. Right-click a row with a patch
    2. 🧠 Smart Edit → 🎯 Select all 'BazaarKick' rows
    3. All kick rows become selected (blue highlight) across all
       sub-columns in the track

  After selecting, you can use normal editing tools on all selected cells:
    - Type a new velocity → applies to all selected
    - Delete/Backspace → clears all selected
    - Right-click → choose from context menu presets

  ══════════════════════════════════════════════════════════════════
  18.3  FILL PATTERN (🔄)
  ══════════════════════════════════════════════════════════════════

  PURPOSE:
    Repeat a rhythm pattern throughout the entire track. The tracker
    equivalent of "autocomplete" — program a few bars, fill the rest.

  HOW IT WORKS:
    1. Select a block of rows (e.g., rows 0-7 with a drum pattern)
    2. Right-click → 🧠 Smart Edit → 🔄 Fill Pattern
    3. The selected block is tiled forward through the remaining rows

  DETAILS:
    - Source block: rows [start_row .. end_row], columns [start_col .. end_col]
    - Block length: end_row - start_row + 1
    - Tiling: copies block to start_row+length, start_row+2×length, etc.
    - Stops when the next full block would exceed the pattern length
    - Preserves colors and text from the source block
    - Works across any selection of columns (single column or full track)

  EXAMPLE WORKFLOW — "Kick on every beat":
    1. Place kick on rows 0, 4 (with note, inst, vel, gate filled in)
    2. Select rows 0-7 (one 8-row cycle)
    3. Right-click → 🧠 Smart Edit → 🔄 Fill Pattern
    4. The kick+empty pattern repeats: rows 8-15, 16-23, 24-31, ...
       through the full 64-row pattern

  EXAMPLE WORKFLOW — "Hi-hat every 2 rows":
    1. Place hi-hat on row 0, leave row 1 empty
    2. Select rows 0-1
    3. 🔄 Fill Pattern
    4. Hi-hat appears on rows 0, 2, 4, 6, 8, ... through the pattern

  ══════════════════════════════════════════════════════════════════
  18.4  REPEAT SELECTION (📐)
  ══════════════════════════════════════════════════════════════════

  PURPOSE:
    Extend a row selection pattern through the rest of the track.
    Instead of Ctrl+clicking every cell, select a few to define the
    rhythm spacing and auto-extend the selection. Select first, then
    use the context menu or paste to fill all selected rows at once.

  HOW IT WORKS:
    1. Select 2 or more rows that define your spacing pattern
       (e.g., rows 0, 4, 8 — every 4th row)
    2. Right-click → 🧠 Smart Edit → 📐 Repeat Selection
    3. The tool detects the stride (4) and selects rows 12, 16, 20, 24...
       through the entire pattern

  PATTERN DETECTION:
    - Uniform stride: rows 0, 4, 8 → gaps [4, 4] → cycle = 4
    - Irregular pattern: rows 0, 3, 4 → gaps [3, 1] → cycle = 4
      Extends as: 4, 7, 8, 11, 12, 15, 16...
    - The gap sequence repeats exactly as detected

  DETAILS:
    - Requires ≥ 2 selected rows (need at least 1 gap to detect)
    - Preserves original selection — extends forward only
    - Column range is preserved from the original selection
    - Original selected rows stay selected

  EXAMPLE WORKFLOW — "Select every 4th row for hi-hats":
    1. Click row 0, Ctrl+click row 4
    2. 📐 Repeat Selection
    3. Rows 0, 4, 8, 12, 16, 20... all selected (blue highlight)
    4. Now right-click → set Note, Inst, Vel, Gate — fills all at once

  EXAMPLE WORKFLOW — "Swing pattern (rows 0, 3, 4, 7, 8...)":
    1. Click row 0, Ctrl+click row 3, Ctrl+click row 4
    2. 📐 Repeat Selection
    3. Pattern repeats as: 0, 3, 4, 7, 8, 11, 12, 15, 16...


================================================================================
  19. BUILDING & DISTRIBUTION
================================================================================

  ══════════════════════════════════════════════════════════════════
  19.1  PREREQUISITES
  ══════════════════════════════════════════════════════════════════

  Python 3.10+
  Required packages: numpy, sounddevice, soundfile, PyQt6, pyqtgraph,
                     pydub, pyinstaller

  Install all dependencies:
    pip install numpy sounddevice soundfile PyQt6 pyqtgraph pydub pyinstaller

  ══════════════════════════════════════════════════════════════════
  19.2  BUILDING ON LINUX
  ══════════════════════════════════════════════════════════════════

  From the project root:
    chmod +x build.sh
    ./build.sh

  Output: dist/LanthornPSG (single binary, ~50-80 MB)

  The executable bundles:
    - All Python source and dependencies
    - presets/ directory (all 6 folders, 28 factory patches)
    - ENGINE_SPEC.md (this document)
    - Demo songs (Lanthorn.csv, InstrumentDemo.csv, DrumSolo.csv)

  First Run Behavior:
    Factory presets are copied to ~/.lanthorn_psg/presets/ on first launch.
    User-created presets are saved to this directory (writable).
    Factory presets are only seeded if they don't already exist —
    user edits are never overwritten.

  ══════════════════════════════════════════════════════════════════
  19.3  BUILDING ON WINDOWS
  ══════════════════════════════════════════════════════════════════

  From the project root (Git Bash, PowerShell, or CMD):
    build.bat

  Output: dist\LanthornPSG.exe

  Same bundled content as Linux. Presets are seeded to:
    %USERPROFILE%\.lanthorn_psg\presets\

  ══════════════════════════════════════════════════════════════════
  19.4  SPEC FILE (lanthorn_psg.spec)
  ══════════════════════════════════════════════════════════════════

  PyInstaller spec bundles all data files:
    datas = [
      ('presets', 'presets'),       # All preset subfolders
      ('ENGINE_SPEC.md', '.'),      # This document
      ('*.csv', '.'),               # Demo songs
    ]

  Hidden imports include all engine and GUI modules.
  Console is disabled (GUI-only: console=False).
  The spec uses --onefile mode (single executable).

  ══════════════════════════════════════════════════════════════════
  19.5  PRESET DIRECTORY STRUCTURE
  ══════════════════════════════════════════════════════════════════

  presets/
  ├── bass/         (6 patches)
  │   ├── bass_acid.json
  │   ├── bass_pluck.json
  │   ├── bass_sub.json
  │   ├── bass_wobble.json
  │   ├── grit_bass.json
  │   └── SlapBass.json
  ├── drums/        (5 patches)
  │   ├── clap.json
  │   ├── hihat_closed.json
  │   ├── hihat_open.json
  │   ├── Kick.json
  │   └── Snare.json
  ├── keys/         (5 patches)
  │   ├── bell.json
  │   ├── crystal_keys.json
  │   ├── organ.json
  │   ├── PanFlute.json
  │   └── pluck.json
  ├── leads/        (4 patches)
  │   ├── expressive_lead.json
  │   ├── lead_chip.json
  │   ├── lead_saw.json
  │   └── lead_scream.json
  ├── pads/         (6 patches)
  │   ├── hollow_wind.json
  │   ├── pad_choir.json
  │   ├── pad_dark.json
  │   ├── pad_glass.json
  │   ├── pad_warm.json
  │   └── spooky_pad.json
  └── strings/      (2 patches)
      ├── pulse_string.json
      └── string.json

================================================================================
  END OF SPECIFICATION
================================================================================
