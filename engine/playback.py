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

    def calculate_step_time(self, bpm, lines_per_beat=4):
        """Calculates the duration of a single tracker step in seconds."""
        return (60.0 / bpm) / lines_per_beat

    @staticmethod
    def _parse_fx(fx_str):
        """
        Parses a string FX command like 'VIB 64' into (command, param_str).
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
        Applies FX commands from fx1/fx2 to the generated waveform.
        Returns the modified wave.
        """
        for fx_key in ["fx1", "fx2"]:
            fx_str = event.get(fx_key, "")
            cmd, param = self._parse_fx(fx_str)
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
                # Volume override (0-255 → 0.0-1.0)
                combined_wave *= (p_full / 255.0)

            elif cmd == "VIB":
                # Vibrato override: p1=speed (0-15→1-16Hz), p2=depth (0-15→0-1 semitone)
                speed = 1.0 + p1
                depth = p2 / 15.0
                freq_profile = self.mod.generate_vibrato_profile(
                    target_freq, note_duration, speed, depth)
                lfo_wave = np.sin(2 * np.pi * speed * 
                    np.linspace(0, note_duration, len(combined_wave), endpoint=False))
                combined_wave *= (1.0 + depth * 0.1 * lfo_wave)

            elif cmd == "TRM":
                # Tremolo: p1=speed, p2=depth
                speed = 1.0 + p1
                depth = p2 / 15.0
                combined_wave = self.mod.apply_tremolo(combined_wave, speed, depth)

            elif cmd == "ECH":
                # Echo: p1=delay (×0.05s), p2=feedback (0-15→0-0.9)
                delay_time = max(0.01, p1 * 0.05)
                feedback = min(0.9, p2 / 15.0)
                combined_wave = self.mod.apply_echo(combined_wave, delay_time, feedback)

            elif cmd == "RNG":
                # Ring mod: p_full = mix (0-255 → 0.0-1.0)
                mix = p_full / 255.0
                combined_wave = self.mod.apply_ring_mod(combined_wave, 500.0, mix)

            elif cmd == "RTG":
                # Retrigger: full byte 0-255 > 1-32 Hz stutter rate
                rate_hz = 1.0 + (p_full / 255.0) * 31.0
                combined_wave = self.mod.apply_retrigger(combined_wave, rate_hz)

            elif cmd == "ARP":
                # Check if this is a chord event (note is a list)
                raw_notes = event.get("note")
                is_chord = isinstance(raw_notes, list) and len(raw_notes) > 1

                if is_chord:
                    # Chord ARP: high parameter = pattern, low parameter = cycle subdivisions
                    # Patterns: 0=Up, 1=Down, 2=Up-Down, 3=Random
                    pattern = p1  # 0-3
                    divisions = max(2, p2 if p2 > 0 else len(raw_notes) * 2)

                    # Get frequencies for each chord note
                    chord_freqs = [Theory.note_to_freq(n) for n in raw_notes]

                    # Build note sequence based on pattern
                    if pattern == 1:  # Down
                        seq = list(reversed(chord_freqs))
                    elif pattern == 2:  # Up-Down (ping-pong)
                        seq = chord_freqs + list(reversed(chord_freqs[1:-1])) if len(chord_freqs) > 2 else chord_freqs + list(reversed(chord_freqs))
                    elif pattern == 3:  # Random (deterministic shuffle via note sum)
                        import random
                        rng = random.Random(sum(raw_notes))
                        seq = list(chord_freqs)
                        rng.shuffle(seq)
                    else:  # 0 = Up
                        seq = list(chord_freqs)

                    # Generate each segment of the arp cycle
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
                    # Standard ARP: p1=+X semitones, p2=+Y semitones, cycle each 1/3
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
                # Delayed note cut at p_full samples offset (scaled)
                cut_point = int(p_full / 255.0 * len(combined_wave))
                if 0 < cut_point < len(combined_wave):
                    # Apply fast fade at cut point
                    fade_samples = min(int(0.005 * self.sample_rate), len(combined_wave) - cut_point)
                    if fade_samples > 0:
                        fade = np.linspace(1.0, 0.0, fade_samples)
                        combined_wave[cut_point:cut_point+fade_samples] *= fade
                    combined_wave[cut_point+fade_samples:] = 0.0

            elif cmd == "DTN":
                # Detune: p_full 0-255 → 0-50 cents sharp
                cents = (p_full / 255.0) * 50.0
                # Shift pitch by resampling — multiply frequency
                ratio = 2.0 ** (cents / 1200.0)
                original_len = len(combined_wave)
                indices = np.arange(original_len) * ratio
                indices = indices[indices < original_len].astype(int)
                detuned = combined_wave[indices]
                # Pad or trim to original length
                if len(detuned) < original_len:
                    combined_wave = np.pad(detuned, (0, original_len - len(detuned)))
                else:
                    combined_wave = detuned[:original_len]

            elif cmd == "DLY":
                # Delay note start: p_full 0-255 → 0.0-1.0 of note duration
                delay_fraction = p_full / 255.0
                delay_samples = int(delay_fraction * len(combined_wave))
                if delay_samples > 0 and delay_samples < len(combined_wave):
                    shifted = np.zeros_like(combined_wave)
                    shifted[delay_samples:] = combined_wave[:-delay_samples]
                    combined_wave = shifted

            elif cmd == "SAT":
                # Saturation: p_full 0-255 → gain 1.0-5.0
                gain = 1.0 + (p_full / 255.0) * 4.0
                combined_wave = self.mod.apply_saturation(combined_wave, gain)

        return combined_wave

    def render_pattern(self, num_steps, bpm, tracks, master_volume=None, apply_limiter=True):
        """
        Renders a multi-channel pattern into a 2D Stereo master audio buffer.
        Supports NOTE OFF, FX commands, portamento, polyphony, and spatial panning.
        """
        step_duration = self.calculate_step_time(bpm)
        total_samples = int(num_steps * step_duration * self.sample_rate)
        
        master_mix = np.zeros((total_samples, 2))

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

                # Signal Chain Processing — skip identity effects
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
                
                # Apply patch-level echo if present
                if echo_params:
                    combined_wave = self.mod.apply_echo(
                        combined_wave,
                        echo_params.get("delay_time", 0.15),
                        echo_params.get("feedback", 0.4)
                    )
                
                # Apply patch-level ring mod if present
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

        # Master Volume Automation
        master_mix[:, 0] = self._apply_automation(master_mix[:, 0], master_volume, step_duration)
        master_mix[:, 1] = self._apply_automation(master_mix[:, 1], master_volume, step_duration)

        # Final Limiter (can be skipped for project-wide normalization)
        if apply_limiter:
            max_val = np.max(np.abs(master_mix))
            if max_val > 0.98:
                master_mix /= (max_val / 0.98)

        return master_mix

    def play(self, audio_array):
        """Streams the provided 2D audio array to the default output device."""
        sd.play(audio_array, samplerate=self.sample_rate)
        sd.wait()
