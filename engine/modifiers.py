# engine/modifiers.py
import numpy as np
from functools import lru_cache

class Modifiers:
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate

    # --- Cached time-axis helper ---

    @staticmethod
    @lru_cache(maxsize=16)
    def _time_axis(n_samples, sample_rate):
        """Returns a reusable time-axis array for the given buffer length."""
        return np.linspace(0, n_samples / sample_rate, n_samples, endpoint=False)

    # --- 1. AMPLITUDE SHAPING ---
    
    def apply_adsr(self, wave, attack=0.1, decay=0.1, sustain_level=0.7, release=0.2):
        """Shapes the amplitude of the raw mathematical wave over time."""
        # Early exit: flat envelope is a no-op
        if attack <= 0 and decay <= 0 and release <= 0 and sustain_level >= 1.0:
            return wave

        total_samples = len(wave)
        a_samples = int(attack * self.sample_rate)
        d_samples = int(decay * self.sample_rate)
        r_samples = int(release * self.sample_rate)
        s_samples = max(0, total_samples - a_samples - d_samples - r_samples)
            
        a_env = np.linspace(0.0, 1.0, a_samples) if a_samples > 0 else np.empty(0)
        d_env = np.linspace(1.0, sustain_level, d_samples) if d_samples > 0 else np.empty(0)
        s_env = np.full(s_samples, sustain_level) if s_samples > 0 else np.empty(0)
        r_env = np.linspace(sustain_level, 0.0, r_samples) if r_samples > 0 else np.empty(0)
        
        envelope = np.concatenate([a_env, d_env, s_env, r_env])
        
        if len(envelope) < total_samples:
            envelope = np.pad(envelope, (0, total_samples - len(envelope)), 'constant')
        else:
            envelope = envelope[:total_samples]
            
        return wave * envelope

    def apply_tremolo(self, wave, speed_hz=5.0, depth=0.5):
        """Amplitude Modulation (Volume pulsing)."""
        if depth <= 0.0 or speed_hz <= 0.0:
            return wave
            
        t = self._time_axis(len(wave), self.sample_rate)
        lfo = 1.0 - depth * (0.5 * (1.0 + np.sin(2 * np.pi * speed_hz * t)))
        
        return wave * lfo

    # --- 2. PITCH & TIMING MODULATION ---

    def generate_vibrato_profile(self, base_freq, duration, speed_hz=5.0, depth_semitones=0.5):
        """Generates a dynamic frequency array for Pitch Modulation."""
        n_samples = int(self.sample_rate * duration)
        if depth_semitones <= 0.0 or speed_hz <= 0.0:
            return np.full(n_samples, base_freq)
            
        t = self._time_axis(n_samples, self.sample_rate)
        lfo = np.sin(2 * np.pi * speed_hz * t)
        
        freq_array = base_freq * (2.0 ** ((lfo * depth_semitones) / 12.0))
        return freq_array

    def generate_slide_profile(self, start_freq, end_freq, duration, slide_time=0.1):
        """Linear interpolation between two frequencies (Portamento)."""
        total_samples = int(self.sample_rate * duration)
        slide_samples = int(self.sample_rate * slide_time)
        slide_samples = min(slide_samples, total_samples)
        
        if slide_samples <= 0:
            return np.full(total_samples, end_freq)
            
        slide_array = np.linspace(start_freq, end_freq, slide_samples)
        sustain_array = np.full(total_samples - slide_samples, end_freq)
        
        return np.concatenate([slide_array, sustain_array])

    def generate_pitch_sweep(self, start_freq, end_freq, duration):
        """
        Logarithmic frequency sweep. Essential for SFX (Lasers, Jumps, Drops).
        Unlike portamento (which is linear and musical), this bends geometrically.
        """
        total_samples = int(self.sample_rate * duration)
        # Prevent log(0) errors by flooring frequencies at 1Hz
        start_freq = max(1.0, start_freq)
        end_freq = max(1.0, end_freq)
        return np.geomspace(start_freq, end_freq, total_samples)

    # --- 3. TIMBRAL EFFECTS (TEXTURE & FOLEY) ---

    def apply_saturation(self, wave, gain=1.2):
        """Adds harmonic texture by 'rounding' the waveform using tanh."""
        if gain <= 1.0: 
            return wave
        return np.tanh(wave * gain)

    def apply_bitcrush(self, wave, bits=8):
        """Reduces the vertical resolution of the wave for a 'crunchy' texture."""
        if bits >= 16: 
            return wave
        q_levels = 2**bits
        wave_normalized = (wave + 1) / 2
        crushed = np.round(wave_normalized * q_levels) / q_levels
        return (crushed * 2) - 1

    def generate_pwm_profile(self, duration, lfo_speed=0.5, depth=0.4, base_width=0.5):
        """Generates a moving duty-cycle array for the Square/Pulse wave."""
        n_samples = int(self.sample_rate * duration)
        t = self._time_axis(n_samples, self.sample_rate)
        return base_width + (depth * 0.5 * np.sin(2 * np.pi * lfo_speed * t))

    def apply_ring_mod(self, wave, carrier_freq=500.0, mix=1.0):
        """
        Multiplies the wave by a high-frequency sine wave. 
        Creates metallic, bell-like, or robotic dissonance.
        """
        if mix <= 0.0:
            return wave
        t = self._time_axis(len(wave), self.sample_rate)
        carrier = np.sin(2 * np.pi * carrier_freq * t)
        rm_wave = wave * carrier
        return (wave * (1.0 - mix)) + (rm_wave * mix)

    def apply_retrigger(self, wave, rate_hz=16.0):
        """
        Chops the audio into rapid bursts. 
        Great for helicopter rotors, machine guns, or retro glitches.
        """
        if rate_hz <= 0.0:
            return wave
        t = self._time_axis(len(wave), self.sample_rate)
        # Creates a square wave LFO (0 or 1) to act as a noise gate
        stutter_gate = (np.sign(np.sin(2 * np.pi * rate_hz * t)) + 1) / 2
        return wave * stutter_gate

    def apply_echo(self, wave, delay_time=0.15, feedback=0.4, num_taps=6):
        """
        Vectorized multi-tap echo using array slicing.
        Each tap applies exponentially decaying feedback.
        """
        if feedback <= 0.0 or delay_time <= 0.0:
            return wave
            
        delay_samples = int(delay_time * self.sample_rate)
        if delay_samples >= len(wave) or delay_samples <= 0:
            return wave
            
        out_wave = np.copy(wave)
        # Multi-tap vectorized echo: each pass adds a delayed copy with decaying gain
        gain = feedback
        for tap in range(num_taps):
            offset = delay_samples * (tap + 1)
            if offset >= len(wave):
                break
            out_wave[offset:] += wave[:len(wave) - offset] * gain
            gain *= feedback  # exponential decay
        return out_wave
