# engine/playback.py
import numpy as np
import sounddevice as sd
from .oscillator import Oscillator
from .modifiers import Modifiers
from .theory import Theory
from .preset_manager import PresetManager

class Sequencer:
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.osc = Oscillator(sample_rate)
        self.mod = Modifiers(sample_rate)
        self.presets = PresetManager()
        self.master_vol = 1.0
        self.master_pan = 0.0

    def calculate_step_time(self, bpm, lines_per_beat=4):
        """Calculates the duration of a single tracker step in seconds."""
        return (60.0 / bpm) / lines_per_beat

    @staticmethod
    def _parse_fx(fx_str):
        """
        Parses a single FX command like 'VIB 64' into (command, param_str).
        Returns (None, None) if invalid.
        """
        if not fx_str or fx_str in ["--", "---", ""]:
            return None, None
        parts = fx_str.strip().split()
        if len(parts) >= 2:
            return parts[0].upper(), parts[1].upper()
        elif len(parts) == 1:
            return parts[0].upper(), "00"
        return None, None

    @staticmethod
    def _parse_fx_stack(fx_str):
        """
        Parses a potentially stacked FX string like 'VIB 68: SAT 40'
        into a list of (command, param_str) tuples.
        Falls back to single-FX parsing for backward compatibility.
        """
        if not fx_str or fx_str in ["--", "---", ""]:
            return []
        results = []
        # Split on colon for stacked FX
        segments = fx_str.split(":")
        for seg in segments:
            seg = seg.strip()
            if not seg or seg in ["--", "---"]:
                continue
            parts = seg.split()
            if len(parts) >= 2:
                results.append((parts[0].upper(), parts[1].upper()))
            elif len(parts) == 1:
                results.append((parts[0].upper(), "00"))
        return results

    def _apply_automation(self, audio_array, keyframes, step_duration):
        """Linearly interpolates volume levels across a series of step-based keyframes."""
        if not keyframes or len(audio_array) == 0:
            return audio_array
            
        total_samples = len(audio_array)
        samples_per_step = int(step_duration * self.sample_rate)
        sorted_kf = sorted(keyframes, key=lambda k: k["step"])
        xp = [kf["step"] * samples_per_step for kf in sorted_kf]
        fp = [kf["level"] for kf in sorted_kf]
        
        if xp[0] > 0:
            xp.insert(0, 0)
            fp.insert(0, fp[0])
        if xp[-1] < total_samples:
            xp.append(total_samples)
            fp.append(fp[-1])
            
        x = np.arange(total_samples)
        vol_envelope = np.interp(x, xp, fp)
        return audio_array * vol_envelope

    def _generate_pan_envelope(self, total_samples, keyframes, step_duration):
        """Creates a sample-accurate array of panning values (-1.0 to 1.0)."""
        if not keyframes:
            return np.zeros(total_samples)
            
        samples_per_step = int(step_duration * self.sample_rate)
        sorted_kf = sorted(keyframes, key=lambda k: k["step"])
        
        xp = [kf["step"] * samples_per_step for kf in sorted_kf]
        fp = [kf["value"] for kf in sorted_kf]
        
        if xp[0] > 0:
            xp.insert(0, 0)
            fp.insert(0, fp[0])
        if xp[-1] < total_samples:
            xp.append(total_samples)
            fp.append(fp[-1])
            
        x = np.arange(total_samples)
        pan_envelope = np.interp(x, xp, fp)
        return pan_envelope

    def _apply_fx_to_event(self, combined_wave, event, patch, note_duration, target_freq, prev_freq):
        """
        Applies FX commands from the instrument's fx_chain and the tracker's
        fx1/fx2 columns.  Tracker FX prefixed with '!' override (replace)
        matching instrument FX; un-prefixed tracker FX stack additively.
        """
        # 1. Collect instrument FX from patch.fx_chain
        inst_fx = []
        for fx_item in patch.get("fx_chain", []):
            parsed = self._parse_fx_stack(fx_item)
            inst_fx.extend(parsed)

        # 2. Collect tracker FX from fx1/fx2
        tracker_fx = []        # (cmd, param)  — additive
        override_codes = set() # codes that the tracker overrides
        for fx_key in ["fx1", "fx2"]:
            fx_str = event.get(fx_key, "")
            for seg in fx_str.split(":") if fx_str else []:
                seg = seg.strip()
                if not seg or seg in ["--", "---"]:
                    continue
                is_override = seg.startswith("!")
                if is_override:
                    seg = seg[1:]  # strip the '!'
                parts = seg.split()
                if len(parts) >= 2:
                    cmd, param = parts[0].upper(), parts[1].upper()
                elif len(parts) == 1:
                    cmd, param = parts[0].upper(), "00"
                else:
                    continue
                if is_override:
                    override_codes.add(cmd)
                tracker_fx.append((cmd, param))

        # 3. Build final FX list: instrument FX (minus overridden) + tracker FX
        final_fx = [(c, p) for c, p in inst_fx if c not in override_codes]
        final_fx.extend(tracker_fx)

        # 4. Apply each FX command
        for cmd, param in final_fx:
                if cmd is None:
                    continue
                    
                try:
                    # Parse decimal parameter
                    p_full = int(param)
                    p1 = (p_full >> 4) & 0xF  # high parameter for dual-param FX
                    p2 = p_full & 0xF          # low parameter for dual-param FX
                except ValueError:
                    continue

                if cmd == "VOL":
                    combined_wave *= (p_full / 255.0)

                elif cmd == "VIB":
                    speed = 1.0 + p1
                    depth = p2 / 15.0
                    freq_profile = self.mod.generate_vibrato_profile(
                        target_freq, note_duration, speed, depth)
                    lfo_wave = np.sin(2 * np.pi * speed * 
                        np.linspace(0, note_duration, len(combined_wave), endpoint=False))
                    combined_wave *= (1.0 + depth * 0.1 * lfo_wave)

                elif cmd == "TRM":
                    speed = 1.0 + p1
                    depth = p2 / 15.0
                    combined_wave = self.mod.apply_tremolo(combined_wave, speed, depth)

                elif cmd == "ECH":
                    delay_time = max(0.01, p1 * 0.05)
                    feedback = min(0.9, p2 / 15.0)
                    combined_wave = self.mod.apply_echo(combined_wave, delay_time, feedback)

                elif cmd == "RNG":
                    mix = p_full / 255.0
                    combined_wave = self.mod.apply_ring_mod(combined_wave, 500.0, mix)

                elif cmd == "RTG":
                    rate_hz = 1.0 + (p_full / 255.0) * 31.0
                    combined_wave = self.mod.apply_retrigger(combined_wave, rate_hz)

                elif cmd == "ARP":
                    raw_notes = event.get("note")
                    is_chord = isinstance(raw_notes, list) and len(raw_notes) > 1

                    if is_chord:
                        pattern = p1
                        divisions = max(2, p2 if p2 > 0 else len(raw_notes) * 2)
                        chord_freqs = [Theory.note_to_freq(n) for n in raw_notes]

                        if pattern == 1:
                            seq = list(reversed(chord_freqs))
                        elif pattern == 2:
                            seq = chord_freqs + list(reversed(chord_freqs[1:-1])) if len(chord_freqs) > 2 else chord_freqs + list(reversed(chord_freqs))
                        elif pattern == 3:
                            import random
                            rng = random.Random(sum(raw_notes))
                            seq = list(chord_freqs)
                            rng.shuffle(seq)
                        else:
                            seq = list(chord_freqs)

                        total_len = len(combined_wave)
                        seg_len = total_len // divisions
                        segments = []
                        wave_type = patch.get("wave_type", "square")
                        for i in range(divisions):
                            freq = seq[i % len(seq)]
                            s_len = seg_len if i < divisions - 1 else (total_len - seg_len * (divisions - 1))
                            seg = self.osc.generate(wave_type, freq, s_len / self.sample_rate)
                            segments.append(seg[:s_len])
                        combined_wave = np.concatenate(segments)[:total_len]

                    else:
                        if p1 > 0 or p2 > 0:
                            third = len(combined_wave) // 3
                            freq_0 = target_freq
                            freq_1 = target_freq * (2.0 ** (p1 / 12.0))
                            freq_2 = target_freq * (2.0 ** (p2 / 12.0))
                            
                            w0 = self.osc.generate(patch.get("wave_type", "square"), freq_0, third / self.sample_rate)
                            w1 = self.osc.generate(patch.get("wave_type", "square"), freq_1, third / self.sample_rate)
                            w2 = self.osc.generate(patch.get("wave_type", "square"), freq_2, 
                                (len(combined_wave) - 2 * third) / self.sample_rate)
                            arp_wave = np.concatenate([w0, w1, w2])
                            combined_wave = arp_wave[:len(combined_wave)]

                elif cmd == "CUT":
                    cut_point = int(p_full / 255.0 * len(combined_wave))
                    if 0 < cut_point < len(combined_wave):
                        fade_samples = min(int(0.005 * self.sample_rate), len(combined_wave) - cut_point)
                        if fade_samples > 0:
                            fade = np.linspace(1.0, 0.0, fade_samples)
                            combined_wave[cut_point:cut_point+fade_samples] *= fade
                        combined_wave[cut_point+fade_samples:] = 0.0

                elif cmd == "DTN":
                    cents = (p_full / 255.0) * 50.0
                    ratio = 2.0 ** (cents / 1200.0)
                    original_len = len(combined_wave)
                    indices = np.arange(original_len) * ratio
                    indices = indices[indices < original_len].astype(int)
                    detuned = combined_wave[indices]
                    if len(detuned) < original_len:
                        combined_wave = np.pad(detuned, (0, original_len - len(detuned)))
                    else:
                        combined_wave = detuned[:original_len]

                elif cmd == "DLY":
                    delay_fraction = p_full / 255.0
                    delay_samples = int(delay_fraction * len(combined_wave) * 0.5)
                    if 0 < delay_samples < len(combined_wave):
                        shifted = np.zeros_like(combined_wave)
                        remaining = len(combined_wave) - delay_samples
                        shifted[delay_samples:] = combined_wave[:remaining]
                        combined_wave = shifted

                elif cmd == "SAT":
                    gain = 1.0 + (p_full / 255.0) * 4.0
                    combined_wave = self.mod.apply_saturation(combined_wave, gain)

                elif cmd == "VMD":
                    # Voice Mod: time-based crossfade from OSC1 to OSC2
                    # p1 = target mix (0=pure OSC1, F=100% OSC2)
                    # p2 = slide time as fraction of gate (0=instant, F=full gate)
                    target_mix = p1 / 15.0
                    slide_frac = max(0.01, p2 / 15.0)  # at least 1% to avoid div/0
                    
                    wave2_type = patch.get("wave_type_2")
                    if not wave2_type or wave2_type == "off":
                        wave2_type = "triangle"
                    w2 = self.osc.generate(wave2_type, target_freq, note_duration)
                    if len(w2) >= len(combined_wave):
                        w2 = w2[:len(combined_wave)]
                    else:
                        w2 = np.pad(w2, (0, len(combined_wave) - len(w2)))
                    
                    # Build per-sample mix envelope: ramp from 0 → target_mix
                    total_samples = len(combined_wave)
                    slide_samples = max(1, int(total_samples * slide_frac))
                    mix_env = np.zeros(total_samples)
                    mix_env[:slide_samples] = np.linspace(0, target_mix, slide_samples)
                    mix_env[slide_samples:] = target_mix
                    
                    combined_wave = (1.0 - mix_env) * combined_wave + mix_env * w2

        return combined_wave

    def render_pattern(self, num_steps, bpm, tracks, master_volume=None, apply_limiter=True):
        """
        Renders a multi-channel pattern into a 2D Stereo master audio buffer.
        Supports NOTE OFF, FX commands, portamento, polyphony, spatial panning,
        and global macro automation (MVL, CVL, MPN, CPN).
        """
        step_duration = self.calculate_step_time(bpm)
        total_samples = int(num_steps * step_duration * self.sample_rate)
        
        master_mix = np.zeros((total_samples, 2))

        # 1. Collect Macro FX (MVL, CVL, MPN, CPN) from all tracks
        macro_cmds = {} # step -> [(cmd, value)]
        for track in tracks:
            for event in track.get("sequence", []):
                step = event["step"]
                for fx_key in ["fx1", "fx2"]:
                    cmd, param = self._parse_fx(event.get(fx_key, ""))
                    if cmd in ["MVL", "CVL", "MPN", "CPN"]:
                        if step not in macro_cmds:
                            macro_cmds[step] = []
                        macro_cmds[step].append((cmd, param))

        for track in tracks:
            track_mix = np.zeros(total_samples)
            
            patch = track.get("patch", self.presets.get_default_patch())
            sequence = track.get("sequence", [])

            prev_freq = None  # Track previous note frequency for portamento
            prev_end_sample = 0  # Track where previous note ends

            for i, event in enumerate(sequence):
                step = event["step"]
                notes = event.get("note")

                # --- NOTE OFF handling ---
                if notes == "OFF" or notes == -1:
                    off_sample = int(step * step_duration * self.sample_rate)
                    if off_sample < total_samples and prev_end_sample > off_sample:
                        # Apply 5ms fade-out at OFF point
                        fade_len = min(int(0.005 * self.sample_rate), prev_end_sample - off_sample)
                        if fade_len > 0:
                            fade = np.linspace(1.0, 0.0, fade_len)
                            end_fade = min(off_sample + fade_len, total_samples)
                            track_mix[off_sample:end_fade] *= fade[:end_fade - off_sample]
                        # Silence everything after the fade
                        track_mix[min(off_sample + fade_len, total_samples):prev_end_sample] = 0.0
                    continue

                if notes is None:
                    continue

                if not isinstance(notes, list):
                    notes = [notes]

                # --- Per-event instrument (multi-instrument support) ---
                evt_patch = event.get("patch", patch)

                env_params = evt_patch.get("envelope", {})
                lfo_params = evt_patch.get("lfo", {})
                port_params = evt_patch.get("portamento", {})
                wave_1_type = evt_patch.get("wave_type", "sine")
                wave_2_type = evt_patch.get("wave_type_2")
                mix_ratio = evt_patch.get("mix", 0.0)
                sat_gain = evt_patch.get("saturation", 1.0)
                bit_depth = evt_patch.get("bit_depth", 16)
                duty_cycle = evt_patch.get("duty_cycle", 0.5)
                echo_params = evt_patch.get("echo", {})
                ring_params = evt_patch.get("ring_mod", {})

                gate_steps = event.get("gate", 1)
                velocity = event.get("velocity", 1.0)
                
                start_sample = int(step * step_duration * self.sample_rate)
                note_duration = gate_steps * step_duration
                note_samples = int(note_duration * self.sample_rate)
                
                combined_wave = np.zeros(note_samples)

                for note in notes:
                    target_freq = Theory.note_to_freq(note)
                    
                    # Check for portamento (PRT FX command or patch setting)
                    use_portamento = False
                    custom_freq_profile = None  # Set by SUP/SDN
                    slide_time = port_params.get("slide_time", 0.0)
                    
                    for fx_key in ["fx1", "fx2"]:
                        fx_cmd, fx_param = self._parse_fx(event.get(fx_key, ""))
                        if fx_cmd == "PRT" and fx_param:
                            try:
                                slide_time = max(0.01, int(fx_param) / 255.0 * 0.5)
                            except ValueError:
                                pass
                            use_portamento = True
                        elif fx_cmd == "SUP" and fx_param:
                            try:
                                bend = int(fx_param) / 255.0 * 12.0
                                target_freq_bent = target_freq * (2.0 ** (bend / 12.0))
                                custom_freq_profile = self.mod.generate_slide_profile(
                                    target_freq, target_freq_bent, note_duration, note_duration * 0.8)
                            except ValueError:
                                pass
                        elif fx_cmd == "SDN" and fx_param:
                            try:
                                bend = int(fx_param) / 255.0 * 12.0
                                target_freq_bent = target_freq / (2.0 ** (bend / 12.0))
                                custom_freq_profile = self.mod.generate_slide_profile(
                                    target_freq, target_freq_bent, note_duration, note_duration * 0.8)
                            except ValueError:
                                pass
                    
                    if custom_freq_profile is not None:
                        # SUP/SDN already generated a profile
                        freq_profile = custom_freq_profile
                    elif use_portamento and prev_freq and prev_freq != target_freq and slide_time > 0:
                        freq_profile = self.mod.generate_slide_profile(
                            prev_freq, target_freq, note_duration, slide_time)
                    else:
                        freq_profile = self.mod.generate_vibrato_profile(
                            target_freq, note_duration, 
                            lfo_params.get("vibrato_speed", 0.0), 
                            lfo_params.get("vibrato_depth", 0.0)
                        )

                    w1 = self.osc.generate(wave_1_type, freq_profile, note_duration, duty_cycle)
                    
                    if wave_2_type:
                        w2 = self.osc.generate(wave_2_type, freq_profile, note_duration, duty_cycle)
                        w1 = ((1.0 - mix_ratio) * w1) + (mix_ratio * w2)
                    
                    combined_wave += w1
                    prev_freq = target_freq

                if len(notes) > 1:
                    combined_wave /= np.sqrt(len(notes))

                # --- Legacy patch-level effects (skip if fx_chain present) ---
                has_fx_chain = bool(evt_patch.get("fx_chain"))

                if not has_fx_chain:
                    if sat_gain > 1.0:
                        combined_wave = self.mod.apply_saturation(combined_wave, sat_gain)
                    if bit_depth < 16:
                        combined_wave = self.mod.apply_bitcrush(combined_wave, bit_depth)
                    trem_speed = lfo_params.get("tremolo_speed", 0.0)
                    trem_depth = lfo_params.get("tremolo_depth", 0.0)
                    if trem_speed > 0 and trem_depth > 0:
                        combined_wave = self.mod.apply_tremolo(
                            combined_wave, trem_speed, trem_depth
                        )
                    if echo_params:
                        combined_wave = self.mod.apply_echo(
                            combined_wave,
                            echo_params.get("delay_time", 0.15),
                            echo_params.get("feedback", 0.4)
                        )
                    if ring_params:
                        combined_wave = self.mod.apply_ring_mod(
                            combined_wave,
                            ring_params.get("carrier_freq", 500.0),
                            ring_params.get("mix", 0.5)
                        )

                combined_wave = self.mod.apply_adsr(
                    combined_wave,
                    attack=env_params.get("attack", 0.05),
                    decay=env_params.get("decay", 0.1),
                    sustain_level=env_params.get("sustain_level", 0.5),
                    release=env_params.get("release", 0.2)
                )

                # Apply FX commands
                combined_wave = self._apply_fx_to_event(
                    combined_wave, event, evt_patch, note_duration, target_freq, prev_freq)

                combined_wave *= velocity

                end_sample = start_sample + note_samples
                prev_end_sample = min(end_sample, total_samples)
                if start_sample < total_samples:
                    actual_end = min(end_sample, total_samples)
                    # Guard against off-by-one from float→int rounding
                    copy_len = min(len(combined_wave), actual_end - start_sample)
                    track_mix[start_sample:start_sample + copy_len] += combined_wave[:copy_len]

            # Apply Track Volume Automation
            track_mix = self._apply_automation(track_mix, track.get("track_volume"), step_duration)
            
            # Pan Automation
            pan_automation = track.get("pan_automation")
            if not pan_automation:
                static_pan = track.get("pan", 0.0)
                pan_automation = [{"step": 0, "value": static_pan}]
                
            pan_env = self._generate_pan_envelope(total_samples, pan_automation, step_duration)
            pan_env = np.clip(pan_env, -1.0, 1.0)
            
            left_gains = np.clip(1.0 - pan_env, 0.0, 1.0)
            right_gains = np.clip(1.0 + pan_env, 0.0, 1.0)
            
            master_mix[:, 0] += track_mix * left_gains
            master_mix[:, 1] += track_mix * right_gains
            
        # --- Apply Master Envelopes ---
        def build_env(events, initial_val, max_steps):
            env = np.full(total_samples, initial_val)
            if not events:
                return env, initial_val
            if events[0][0] > 0:
                events.insert(0, (0, "SET", initial_val))
            current_val = initial_val
            for i in range(len(events)):
                step, evt_type, val = events[i]
                start_samp = int(step * step_duration * self.sample_rate)
                end_step = events[i+1][0] if i + 1 < len(events) else max_steps
                end_samp = int(end_step * step_duration * self.sample_rate)
                if evt_type == "SET":
                    current_val = val
                    env[start_samp:end_samp] = current_val
                elif evt_type == "SLIDE":
                    target_val = val
                    length = end_samp - start_samp
                    if length > 0:
                        slide_array = np.linspace(current_val, target_val, length, endpoint=False)
                        env[start_samp:end_samp] = slide_array
                        current_val = target_val
            return env, current_val

        vol_events = []
        pan_events = []
        for step in sorted(macro_cmds.keys()):
            for cmd, param in macro_cmds[step]:
                try: pval = int(param)
                except ValueError: continue
                if cmd == "MVL": vol_events.append((step, "SET", pval / 255.0))
                elif cmd == "CVL": vol_events.append((step, "SLIDE", pval / 255.0))
                elif cmd == "MPN": pan_events.append((step, "SET", (pval - 128) / 127.0))
                elif cmd == "CPN": pan_events.append((step, "SLIDE", (pval - 128) / 127.0))
                
        if vol_events and vol_events[-1][1] == "SLIDE":
            vol_events.append((num_steps, "SET", vol_events[-1][2]))
        if pan_events and pan_events[-1][1] == "SLIDE":
            pan_events.append((num_steps, "SET", pan_events[-1][2]))

        vol_env, self.master_vol = build_env(vol_events, self.master_vol, num_steps)
        pan_env, self.master_pan = build_env(pan_events, self.master_pan, num_steps)
        pan_env = np.clip(pan_env, -1.0, 1.0)

        master_mix *= vol_env.reshape(-1, 1)
        l_env = np.minimum(1.0, 1.0 - pan_env)
        r_env = np.minimum(1.0, 1.0 + pan_env)
        master_mix[:, 0] *= l_env
        master_mix[:, 1] *= r_env

        if master_volume is not None:
            master_mix *= master_volume

        # Final Limiter (can be skipped for project-wide normalization)
        if apply_limiter:
            max_val = np.max(np.abs(master_mix))
            if max_val > 0.98:
                master_mix *= (0.98 / max_val)

        return master_mix

    def stream_audio(self, audio_array):
        """Streams the provided 2D audio array to the default output device."""
        sd.play(audio_array, samplerate=self.sample_rate)
        sd.wait()
