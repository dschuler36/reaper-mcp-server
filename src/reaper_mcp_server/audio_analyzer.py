import os
import numpy as np
import soundfile as sf
from scipy import signal
from typing import List

try:
    import pyloudnorm as pyln
    HAS_PYLOUDNORM = True
except ImportError:
    HAS_PYLOUDNORM = False

from .reaper_dataclasses import (
    AudioAnalysisResult,
    LevelAnalysis,
    FrequencyAnalysis,
    StereoAnalysis,
    DynamicsAnalysis
)


class AudioAnalyzer:
    """Analyzes audio files for mixing feedback."""

    def __init__(self, audio_path: str):
        self.audio_path = audio_path

    def analyze(self) -> AudioAnalysisResult:
        """Perform comprehensive audio analysis."""
        warnings: List[str] = []

        try:
            # Check if file exists
            if not os.path.exists(self.audio_path):
                return AudioAnalysisResult(
                    file_path=self.audio_path,
                    sample_rate=0,
                    duration_seconds=0.0,
                    channels=0,
                    level=LevelAnalysis(0.0, 0.0, False, 0),
                    frequency=FrequencyAnalysis(0.0, 0.0, 0.0, 0.0),
                    stereo=StereoAnalysis(False, 0.0, 0.0, False),
                    dynamics=DynamicsAnalysis(0.0, 0.0, 0.0),
                    warnings=[],
                    error=f"File not found: {self.audio_path}"
                )

            # Load audio file
            data, sr = sf.read(self.audio_path, always_2d=True)

            # Get basic info
            duration = len(data) / sr
            channels = data.shape[1]

            # Perform analyses
            level_analysis = self._analyze_levels(data, sr)
            frequency_analysis = self._analyze_frequency(data, sr)
            stereo_analysis = self._analyze_stereo(data, sr)
            dynamics_analysis = self._analyze_dynamics(data, sr)

            # Generate warnings
            warnings = self._generate_warnings(
                level_analysis, frequency_analysis, stereo_analysis, dynamics_analysis
            )

            return AudioAnalysisResult(
                file_path=self.audio_path,
                sample_rate=sr,
                duration_seconds=duration,
                channels=channels,
                level=level_analysis,
                frequency=frequency_analysis,
                stereo=stereo_analysis,
                dynamics=dynamics_analysis,
                warnings=warnings,
                error=None
            )

        except sf.LibsndfileError as e:
            return AudioAnalysisResult(
                file_path=self.audio_path,
                sample_rate=0,
                duration_seconds=0.0,
                channels=0,
                level=LevelAnalysis(0.0, 0.0, False, 0),
                frequency=FrequencyAnalysis(0.0, 0.0, 0.0, 0.0),
                stereo=StereoAnalysis(False, 0.0, 0.0, False),
                dynamics=DynamicsAnalysis(0.0, 0.0, 0.0),
                warnings=[],
                error=f"Corrupted or invalid audio file: {str(e)}"
            )
        except Exception as e:
            return AudioAnalysisResult(
                file_path=self.audio_path,
                sample_rate=0,
                duration_seconds=0.0,
                channels=0,
                level=LevelAnalysis(0.0, 0.0, False, 0),
                frequency=FrequencyAnalysis(0.0, 0.0, 0.0, 0.0),
                stereo=StereoAnalysis(False, 0.0, 0.0, False),
                dynamics=DynamicsAnalysis(0.0, 0.0, 0.0),
                warnings=[],
                error=f"Analysis failed: {str(e)}"
            )

    def _analyze_levels(self, data: np.ndarray, sr: int) -> LevelAnalysis:
        """Analyze peak and RMS levels, detect clipping."""
        # Convert to mono for overall level analysis
        if data.shape[1] > 1:
            mono = np.mean(data, axis=1)
        else:
            mono = data[:, 0]

        # Peak analysis
        peak_linear = np.max(np.abs(mono))
        peak_db = self._linear_to_db(peak_linear) if peak_linear > 0 else -np.inf

        # RMS analysis
        rms_linear = np.sqrt(np.mean(mono ** 2))
        rms_db = self._linear_to_db(rms_linear) if rms_linear > 0 else -np.inf

        # Clipping detection (samples at or very close to ±1.0)
        clipping_threshold = 0.9999
        clipped_samples = np.sum(np.abs(mono) >= clipping_threshold)
        clipping_detected = clipped_samples > 0

        return LevelAnalysis(
            peak_db=float(peak_db),
            rms_db=float(rms_db),
            clipping_detected=bool(clipping_detected),
            clipped_samples_count=int(clipped_samples)
        )

    def _analyze_frequency(self, data: np.ndarray, sr: int) -> FrequencyAnalysis:
        """Analyze frequency content and spectral characteristics."""
        # Convert to mono
        if data.shape[1] > 1:
            mono = np.mean(data, axis=1)
        else:
            mono = data[:, 0]

        # Compute FFT
        fft = np.fft.rfft(mono)
        freqs = np.fft.rfftfreq(len(mono), 1/sr)
        magnitude = np.abs(fft)

        # Avoid log of zero
        magnitude = np.maximum(magnitude, 1e-10)

        # Spectral centroid (center of mass of spectrum)
        spectral_centroid = np.sum(freqs * magnitude) / np.sum(magnitude)

        # Spectral rolloff (frequency below which 85% of energy exists)
        cumsum = np.cumsum(magnitude)
        rolloff_threshold = 0.85 * cumsum[-1]
        rolloff_idx = np.where(cumsum >= rolloff_threshold)[0]
        spectral_rolloff = freqs[rolloff_idx[0]] if len(rolloff_idx) > 0 else sr / 2

        # Energy in frequency bands
        def band_energy(low_freq, high_freq):
            mask = (freqs >= low_freq) & (freqs <= high_freq)
            band_mag = magnitude[mask]
            if len(band_mag) == 0:
                return -np.inf
            energy = np.mean(band_mag ** 2)
            return self._linear_to_db(energy) if energy > 0 else -np.inf

        low_freq_energy = band_energy(20, 200)  # Bass/rumble
        mid_freq_energy = band_energy(200, 2000)  # Fundamentals
        high_freq_energy = band_energy(2000, 20000)  # Presence/air

        return FrequencyAnalysis(
            spectral_centroid_hz=float(spectral_centroid),
            low_freq_energy_db=float(low_freq_energy),
            mid_freq_energy_db=float(mid_freq_energy),
            high_freq_energy_db=float(high_freq_energy)
        )

    def _analyze_stereo(self, data: np.ndarray, sr: int) -> StereoAnalysis:
        """Analyze stereo width and phase characteristics."""
        is_stereo = data.shape[1] == 2

        if not is_stereo:
            # Mono file
            return StereoAnalysis(
                is_stereo=False,
                stereo_width=0.0,
                phase_coherence=1.0,
                mono_compatible=True
            )

        # Extract left and right channels
        left = data[:, 0]
        right = data[:, 1]

        # Phase coherence (correlation between L and R)
        if len(left) > 0 and len(right) > 0:
            phase_coherence = np.corrcoef(left, right)[0, 1]
        else:
            phase_coherence = 1.0

        # Stereo width (based on decorrelation)
        # 0.0 = mono (perfect correlation), 1.0 = wide stereo (no correlation)
        stereo_width = 1.0 - abs(phase_coherence)

        # Mono compatibility (good if phase coherence > 0.5)
        mono_compatible = phase_coherence > 0.5

        return StereoAnalysis(
            is_stereo=True,
            stereo_width=float(stereo_width),
            phase_coherence=float(phase_coherence),
            mono_compatible=bool(mono_compatible)
        )

    def _analyze_dynamics(self, data: np.ndarray, sr: int) -> DynamicsAnalysis:
        """Analyze loudness and dynamic range."""
        # Convert to mono
        if data.shape[1] > 1:
            mono = np.mean(data, axis=1)
        else:
            mono = data[:, 0]

        # LUFS calculation (if pyloudnorm is available)
        if HAS_PYLOUDNORM and len(mono) > 0:
            try:
                # Reshape for pyloudnorm (expects 2D array with samples x channels)
                if data.shape[1] == 1:
                    audio_for_lufs = data
                else:
                    audio_for_lufs = data

                meter = pyln.Meter(sr)
                lufs_integrated = meter.integrated_loudness(audio_for_lufs)
            except Exception:
                # Fallback if LUFS calculation fails
                lufs_integrated = -23.0
        else:
            # Rough approximation if pyloudnorm not available
            lufs_integrated = -23.0

        # True peak
        peak_linear = np.max(np.abs(mono))
        true_peak_db = self._linear_to_db(peak_linear) if peak_linear > 0 else -np.inf

        # Crest factor (peak-to-RMS ratio)
        rms_linear = np.sqrt(np.mean(mono ** 2))
        if rms_linear > 0:
            crest_factor_linear = peak_linear / rms_linear
            crest_factor_db = self._linear_to_db(crest_factor_linear)
        else:
            crest_factor_db = 0.0

        return DynamicsAnalysis(
            lufs_integrated=float(lufs_integrated),
            true_peak_db=float(true_peak_db),
            crest_factor_db=float(crest_factor_db)
        )

    def _generate_warnings(
        self,
        level: LevelAnalysis,
        frequency: FrequencyAnalysis,
        stereo: StereoAnalysis,
        dynamics: DynamicsAnalysis
    ) -> List[str]:
        """Generate mixing warnings based on analysis results."""
        warnings = []

        # Level warnings
        if level.peak_db > -0.3:
            warnings.append(f"Peak level very hot: {level.peak_db:.1f} dBFS (risk of clipping)")

        if level.clipping_detected:
            total_samples = level.clipped_samples_count
            warnings.append(f"Clipping detected: {total_samples} clipped samples")

        # Frequency warnings
        if frequency.low_freq_energy_db > -6.0:
            warnings.append(f"Excessive low frequency energy: {frequency.low_freq_energy_db:.1f} dB (muddy mix)")

        if frequency.spectral_centroid_hz < 500:
            warnings.append(f"Spectral centroid very low: {frequency.spectral_centroid_hz:.0f} Hz (dark mix)")

        # Stereo warnings
        if stereo.is_stereo and not stereo.mono_compatible:
            warnings.append(f"Phase issues detected (coherence: {stereo.phase_coherence:.2f}) - may cancel in mono")

        if stereo.is_stereo and stereo.stereo_width < 0.1:
            warnings.append(f"Narrow stereo image (width: {stereo.stereo_width:.2f}) - mostly mono")

        # Dynamics warnings
        if dynamics.lufs_integrated > -8.0:
            warnings.append(f"Very loud for streaming: {dynamics.lufs_integrated:.1f} LUFS (target: -14 LUFS for Spotify)")

        if dynamics.crest_factor_db < 6.0:
            warnings.append(f"Low crest factor: {dynamics.crest_factor_db:.1f} dB (possibly over-compressed)")

        return warnings

    @staticmethod
    def _linear_to_db(linear_value: float) -> float:
        """Convert linear amplitude to decibels."""
        if linear_value <= 0:
            return -np.inf
        return 20 * np.log10(linear_value)
