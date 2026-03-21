import numpy as np

class Oscillator:
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate

    def generate(self, wave_type, frequency, duration, duty_cycle=0.5):
        """
        Generates a raw audio waveform based on type and frequency profile.
        Supports: sine, square, sawtooth, triangle, and noise.
        """
        total_samples = int(self.sample_rate * duration)
        
        # 1. Handle White Noise (Frequency-independent)
        if wave_type == 'noise':
            # Generates random values between -1.0 and 1.0 
            return np.random.uniform(-1.0, 1.0, total_samples)

        # 2. Handle Static vs. Dynamic Frequency Profiles
        if isinstance(frequency, (int, float)):
            # Direct phase calculation for constant frequency (avoids cumsum over constant array)
            phase = np.arange(total_samples) * (float(frequency) / self.sample_rate)
        else:
            # Use the provided dynamic frequency array (e.g., from Vibrato/Slide)
            # Ensure it matches the requested duration length
            freq_array = frequency[:total_samples]
            # Phase Integration (Crucial for smooth pitch modulation)
            phase = np.cumsum(freq_array) / self.sample_rate

        # 3. Generate Waveform using the integrated phase
        if wave_type == 'sine':
            return np.sin(2 * np.pi * phase)
            
        elif wave_type == 'square':
            # Pulse width modulation based on duty_cycle
            return np.where(phase % 1.0 < duty_cycle, 1.0, -1.0)
            
        elif wave_type == 'sawtooth':
            return 2.0 * (phase % 1.0) - 1.0
            
        elif wave_type == 'triangle':
            saw = 2.0 * (phase % 1.0) - 1.0
            return 2.0 * np.abs(saw) - 1.0
            
        else:
            # Fallback for unknown types to prevent engine crashes
            print(f"⚠️ Warning: Unknown wave_type '{wave_type}'. Defaulting to silence.")
            return np.zeros(total_samples)
