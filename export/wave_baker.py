# export/wave_baker.py
"""
Unified audio export engine supporting WAV, OGG, and MP3 formats
with configurable quality profiles and multi-quality batch export.
"""

import wave
import os
import struct
import numpy as np
from engine.constants import HIFI_SAMPLE_RATE, LOFI_SAMPLE_RATE


# Quality profiles: name → (sample_rate, bit_depth, description)
QUALITY_PROFILES = {
    "HQ":    (44100, 16, "44.1kHz / 16-bit"),
    "MidFi": (22050, 16, "22.05kHz / 16-bit"),
    "Retro": (11025, 8,  "11kHz / 8-bit"),
}


class WaveBaker:
    def __init__(self, export_dir=None):
        self.export_dir = export_dir or os.path.expanduser("~/Documents/Lanthorn Exports")
        if not os.path.exists(self.export_dir):
            os.makedirs(self.export_dir, exist_ok=True)

    def _pack_audio(self, audio_array, bit_depth):
        """Converts floating-point [-1.0, 1.0] into binary audio data."""
        audio_array = np.nan_to_num(audio_array, nan=0.0, posinf=1.0, neginf=-1.0)
        
        max_amp = np.max(np.abs(audio_array))
        if max_amp > 0.0:
            audio_array = (audio_array / max_amp) * 0.95
            
        audio_array = np.clip(audio_array, -1.0, 1.0)
        
        if bit_depth == 8:
            quantized = np.round((audio_array + 1.0) * 127.5).astype('<u1')
            return quantized.tobytes()
        elif bit_depth == 16:
            quantized = np.round(audio_array * 32767.0).astype('<i2')
            return quantized.tobytes()
        else:
            raise ValueError(f"Bit depth {bit_depth} not supported.")

    def _resample(self, audio_array, orig_rate, target_rate):
        """Downsample with a simple anti-aliasing lowpass filter."""
        if orig_rate == target_rate:
            return audio_array
        ratio = orig_rate / target_rate
        target_len = int(len(audio_array) / ratio)
        if target_len < 1:
            target_len = 1

        # Apply simple moving-average lowpass before decimation
        kernel_size = max(2, int(ratio))
        kernel = np.ones(kernel_size) / kernel_size

        if audio_array.ndim == 2:
            filtered = np.column_stack([
                np.convolve(audio_array[:, ch], kernel, mode='same')
                for ch in range(audio_array.shape[1])
            ])
            x_old = np.linspace(0, 1, len(filtered))
            x_new = np.linspace(0, 1, target_len)
            return np.column_stack([
                np.interp(x_new, x_old, filtered[:, ch])
                for ch in range(filtered.shape[1])
            ])
        else:
            filtered = np.convolve(audio_array, kernel, mode='same')
            x_old = np.linspace(0, 1, len(filtered))
            x_new = np.linspace(0, 1, target_len)
            return np.interp(x_new, x_old, filtered)

    def export_wav(self, filepath, audio_array, sample_rate=44100, bit_depth=16):
        """Exports audio as WAV file."""
        n_channels = 2 if audio_array.ndim == 2 and audio_array.shape[1] == 2 else 1
        
        resampled = self._resample(audio_array, HIFI_SAMPLE_RATE, sample_rate)
        
        if n_channels == 2:
            interleaved = resampled.flatten()
        else:
            interleaved = resampled
        
        sample_width = 1 if bit_depth == 8 else 2
        
        with wave.open(filepath, 'w') as wf:
            wf.setnchannels(n_channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(self._pack_audio(interleaved, bit_depth))
        
        return filepath

    def export_ogg(self, filepath, audio_array, sample_rate=44100):
        """Exports audio as OGG Vorbis via soundfile (if available) or WAV fallback."""
        try:
            import soundfile as sf
            resampled = self._resample(audio_array, HIFI_SAMPLE_RATE, sample_rate)
            # Normalize
            max_amp = np.max(np.abs(resampled))
            if max_amp > 0:
                resampled = (resampled / max_amp) * 0.95
            sf.write(filepath, resampled, sample_rate, format='OGG', subtype='VORBIS')
            return filepath
        except ImportError:
            # Fallback: write as WAV with .ogg extension warning
            fallback = filepath.replace('.ogg', '.wav')
            print(f"⚠ soundfile not installed. Exporting as WAV instead: {fallback}")
            return self.export_wav(fallback, audio_array, sample_rate)

    def export_mp3(self, filepath, audio_array, sample_rate=44100):
        """Exports audio as MP3 via pydub (if available) or WAV fallback."""
        try:
            from pydub import AudioSegment
            import io
            
            resampled = self._resample(audio_array, HIFI_SAMPLE_RATE, sample_rate)
            max_amp = np.max(np.abs(resampled))
            if max_amp > 0:
                resampled = (resampled / max_amp) * 0.95
            
            n_channels = 2 if resampled.ndim == 2 and resampled.shape[1] == 2 else 1
            if n_channels == 2:
                int_data = (resampled.flatten() * 32767).astype('<i2')
            else:
                int_data = (resampled * 32767).astype('<i2')
            
            segment = AudioSegment(
                int_data.tobytes(),
                frame_rate=sample_rate,
                sample_width=2,
                channels=n_channels
            )
            segment.export(filepath, format="mp3")
            return filepath
        except ImportError:
            fallback = filepath.replace('.mp3', '.wav')
            print(f"⚠ pydub not installed. Exporting as WAV instead: {fallback}")
            return self.export_wav(fallback, audio_array, sample_rate)

    def export_audio(self, filename, audio_array, fmt="wav", quality="HQ"):
        """
        Unified export entry point.
        
        Args:
            filename: Base name for the file (no extension)
            audio_array: numpy audio data (shape: (samples,2) for stereo)
            fmt: "wav", "ogg", or "mp3"
            quality: key from QUALITY_PROFILES
        
        Returns: filepath of exported file
        """
        profile = QUALITY_PROFILES.get(quality, QUALITY_PROFILES["HQ"])
        sample_rate, bit_depth, _ = profile
        
        ext = fmt.lower()
        filepath = os.path.join(self.export_dir, f"{filename}_{quality}.{ext}")
        
        if ext == "wav":
            return self.export_wav(filepath, audio_array, sample_rate, bit_depth)
        elif ext == "ogg":
            return self.export_ogg(filepath, audio_array, sample_rate)
        elif ext == "mp3":
            return self.export_mp3(filepath, audio_array, sample_rate)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    def multi_export(self, filename, audio_array, fmt="wav", qualities=None):
        """
        Export at multiple quality levels.
        
        Returns: list of exported filepaths
        """
        if qualities is None:
            qualities = ["HQ"]
        
        exported = []
        for q in qualities:
            path = self.export_audio(filename, audio_array, fmt, q)
            exported.append(path)
            print(f"💾 Exported: {path}")
        
        return exported

    # Legacy compatibility
    def dual_bake(self, filename, audio_array):
        """Legacy method — renders both HQ and Retro WAV."""
        return self.multi_export(filename, audio_array, "wav", ["HQ", "Retro"])

    def bake_hq(self, filename, audio_array):
        return self.export_audio(filename, audio_array, "wav", "HQ")

    def bake_retro(self, filename, audio_array):
        return self.export_audio(filename, audio_array, "wav", "Retro")
