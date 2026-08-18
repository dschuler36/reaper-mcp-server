import os
from typing import List, Optional, Tuple

import numpy as np
import soundfile as sf

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

# Below this the spectral numbers are noise, so warnings are suppressed.
MIN_RELIABLE_SECONDS = 0.05

# Band edges in Hz.
LOW_BAND = (20.0, 200.0)
MID_BAND = (200.0, 2000.0)
HIGH_BAND = (2000.0, 20000.0)
MUD_BAND = (200.0, 500.0)
UPPER_MID_BAND = (500.0, 2000.0)

# How much louder 200-500 Hz has to be than 500-2000 Hz before the material
# reads boxy. Calibrated against a full multi-track project so that it flags a
# minority of sources rather than firing on everything, and so that bass parts
# sit mid-pack instead of tripping it by definition.
LOW_MID_TILT_THRESHOLD_DB = 10.0

# Mean sample value above which a region carries a real DC offset.
DC_OFFSET_THRESHOLD = 0.001


class AudioAnalyzer:
    """Analyzes an audio file, or one region of it, for mixing feedback.

    Passing ``start_seconds``/``length_seconds`` measures only that slice, which
    is what a REAPER item actually plays: an item references a region of its
    source file via SOFFS and LENGTH, and analysing the whole file instead
    describes audio that is not in the arrangement.

    Measurements are taken from the file on disk, so they are pre-FX and
    pre-fader.
    """

    def __init__(
        self,
        audio_path: str,
        start_seconds: float = 0.0,
        length_seconds: Optional[float] = None,
    ):
        self.audio_path = audio_path
        self.start_seconds = max(0.0, start_seconds)
        self.length_seconds = length_seconds

    def analyze(self) -> AudioAnalysisResult:
        try:
            if not self.audio_path:
                return self._empty_result(error="No audio source for this item")

            if not os.path.exists(self.audio_path):
                return self._empty_result(error=f"File not found: {self.audio_path}")

            data, sr, region_start, region_length, whole_file = self._read_region()

            if data.shape[0] == 0:
                return self._empty_result(
                    error="Requested region is empty (zero frames)",
                    sample_rate=sr,
                    region_start=region_start,
                    region_length=region_length,
                    whole_file=whole_file,
                )

            duration = data.shape[0] / sr
            channels = data.shape[1]

            level_analysis = self._analyze_levels(data)
            frequency_analysis = self._analyze_frequency(data, sr)
            stereo_analysis = self._analyze_stereo(data)
            dynamics_analysis = self._analyze_dynamics(data, sr)

            if duration >= MIN_RELIABLE_SECONDS:
                warnings = self._generate_warnings(
                    level_analysis, frequency_analysis, stereo_analysis, dynamics_analysis
                )
            else:
                warnings = [
                    f"Region is {duration * 1000:.1f} ms - too short for reliable analysis"
                ]

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
                error=None,
                region_start_seconds=region_start,
                region_length_seconds=duration,
                whole_file=whole_file,
            )

        except sf.LibsndfileError as e:
            return self._empty_result(error=f"Corrupted or invalid audio file: {e}")
        except Exception as e:
            return self._empty_result(error=f"Analysis failed: {e}")

    # -- io ----------------------------------------------------------------

    def _read_region(self) -> Tuple[np.ndarray, int, float, float, bool]:
        """Read the requested slice, clamped to the file's real extent."""
        with sf.SoundFile(self.audio_path) as handle:
            sr = handle.samplerate
            total_frames = len(handle)

            start_frame = min(int(round(self.start_seconds * sr)), total_frames)
            if self.length_seconds is None:
                frame_count = total_frames - start_frame
            else:
                frame_count = int(round(self.length_seconds * sr))
            frame_count = max(0, min(frame_count, total_frames - start_frame))

            whole_file = start_frame == 0 and frame_count == total_frames

            handle.seek(start_frame)
            data = handle.read(frames=frame_count, dtype='float64', always_2d=True)

        return data, sr, start_frame / sr, frame_count / sr, whole_file

    def _empty_result(
        self,
        error: str,
        sample_rate: int = 0,
        region_start: float = 0.0,
        region_length: float = 0.0,
        whole_file: bool = True,
    ) -> AudioAnalysisResult:
        return AudioAnalysisResult(
            file_path=self.audio_path,
            sample_rate=sample_rate,
            duration_seconds=0.0,
            channels=0,
            level=LevelAnalysis(0.0, 0.0, False, 0),
            frequency=FrequencyAnalysis(0.0, 0.0, 0.0, 0.0),
            stereo=StereoAnalysis(False, 0.0, 0.0, False),
            dynamics=DynamicsAnalysis(None, 0.0, 0.0),
            warnings=[],
            error=error,
            region_start_seconds=region_start,
            region_length_seconds=region_length,
            whole_file=whole_file,
        )

    # -- analyses ----------------------------------------------------------

    @staticmethod
    def _to_mono(data: np.ndarray) -> np.ndarray:
        return np.mean(data, axis=1) if data.shape[1] > 1 else data[:, 0]

    def _analyze_levels(self, data: np.ndarray) -> LevelAnalysis:
        mono = self._to_mono(data)

        peak_linear = float(np.max(np.abs(mono)))
        rms_linear = float(np.sqrt(np.mean(mono ** 2)))

        clipping_threshold = 0.9999
        clipped_samples = int(np.sum(np.abs(mono) >= clipping_threshold))

        return LevelAnalysis(
            peak_db=self._linear_to_db(peak_linear),
            rms_db=self._linear_to_db(rms_linear),
            clipping_detected=clipped_samples > 0,
            clipped_samples_count=clipped_samples,
            dc_offset=float(np.mean(mono)),
        )

    def _analyze_frequency(self, data: np.ndarray, sr: int) -> FrequencyAnalysis:
        """Spectral balance, expressed as each band's share of total power.

        The FFT is normalised by length. Without that, magnitudes scale with the
        number of samples and a long file reads ~20 dB hotter than a short one
        of identical material, which makes any absolute dB threshold meaningless.
        Band figures are ratios of total power for the same reason, and the _db
        fields are those ratios in dB (so they are <= 0).
        """
        mono = self._to_mono(data)

        magnitude = np.abs(np.fft.rfft(mono)) / len(mono)
        freqs = np.fft.rfftfreq(len(mono), 1 / sr)
        power = magnitude ** 2

        total_power = float(np.sum(power))
        magnitude_sum = float(np.sum(magnitude))
        centroid = float(np.sum(freqs * magnitude) / magnitude_sum) if magnitude_sum > 0 else 0.0

        def band_ratio(low: float, high: float) -> float:
            if total_power <= 0:
                return 0.0
            mask = (freqs >= low) & (freqs < high)
            return float(np.sum(power[mask]) / total_power)

        low_ratio = band_ratio(*LOW_BAND)
        mid_ratio = band_ratio(*MID_BAND)
        high_ratio = band_ratio(*HIGH_BAND)
        mud_ratio = band_ratio(*MUD_BAND)
        upper_mid_ratio = band_ratio(*UPPER_MID_BAND)

        if mud_ratio > 0 and upper_mid_ratio > 0:
            tilt_db = float(10 * np.log10(mud_ratio / upper_mid_ratio))
        else:
            tilt_db = 0.0

        return FrequencyAnalysis(
            spectral_centroid_hz=centroid,
            low_freq_energy_db=self._ratio_to_db(low_ratio),
            mid_freq_energy_db=self._ratio_to_db(mid_ratio),
            high_freq_energy_db=self._ratio_to_db(high_ratio),
            low_freq_ratio=low_ratio,
            mid_freq_ratio=mid_ratio,
            high_freq_ratio=high_ratio,
            mud_ratio=mud_ratio,
            low_mid_tilt_db=tilt_db,
        )

    @staticmethod
    def _analyze_stereo(data: np.ndarray) -> StereoAnalysis:
        if data.shape[1] != 2:
            return StereoAnalysis(
                is_stereo=False,
                stereo_width=0.0,
                phase_coherence=1.0,
                mono_compatible=True,
            )

        left, right = data[:, 0], data[:, 1]

        # A silent or DC channel has zero variance, which makes correlation
        # undefined; treat it as fully correlated rather than emitting NaN.
        if np.std(left) == 0 or np.std(right) == 0:
            phase_coherence = 1.0
        else:
            phase_coherence = float(np.corrcoef(left, right)[0, 1])

        return StereoAnalysis(
            is_stereo=True,
            stereo_width=1.0 - abs(phase_coherence),
            phase_coherence=phase_coherence,
            mono_compatible=phase_coherence > 0.5,
        )

    def _analyze_dynamics(self, data: np.ndarray, sr: int) -> DynamicsAnalysis:
        mono = self._to_mono(data)

        # pyloudnorm needs at least one 400 ms block. Left as None rather than
        # substituted with a plausible-looking default when it cannot be
        # measured, so callers can tell "quiet" from "unknown".
        lufs_integrated: Optional[float] = None
        if HAS_PYLOUDNORM and data.shape[0] >= sr * 0.4:
            try:
                lufs = pyln.Meter(sr).integrated_loudness(data)
                if np.isfinite(lufs):
                    lufs_integrated = float(lufs)
            except Exception:
                lufs_integrated = None

        peak_linear = float(np.max(np.abs(mono)))
        rms_linear = float(np.sqrt(np.mean(mono ** 2)))

        if rms_linear > 0 and peak_linear > 0:
            crest_factor_db = self._linear_to_db(peak_linear / rms_linear)
        else:
            crest_factor_db = 0.0

        return DynamicsAnalysis(
            lufs_integrated=lufs_integrated,
            true_peak_db=self._linear_to_db(peak_linear),
            crest_factor_db=crest_factor_db,
        )

    @staticmethod
    def _generate_warnings(
        level: LevelAnalysis,
        frequency: FrequencyAnalysis,
        stereo: StereoAnalysis,
        dynamics: DynamicsAnalysis,
    ) -> List[str]:
        warnings = []

        if level.peak_db > -0.3:
            warnings.append(f"Peak level very hot: {level.peak_db:.1f} dBFS (risk of clipping)")

        if level.clipping_detected:
            warnings.append(f"Clipping detected: {level.clipped_samples_count} clipped samples")

        if abs(level.dc_offset) > DC_OFFSET_THRESHOLD:
            warnings.append(f"DC offset detected: {level.dc_offset:+.4f} mean sample value")

        # Mud is the low mids sitting on top of the upper mids, not the presence
        # of bass. Comparing the two bands to each other means a bass part is
        # judged on its own balance rather than flagged for being a bass.
        if frequency.low_mid_tilt_db > LOW_MID_TILT_THRESHOLD_DB:
            warnings.append(
                f"Boxy low mids: 200-500 Hz is {frequency.low_mid_tilt_db:.1f} dB "
                f"above 500-2000 Hz"
            )

        if stereo.is_stereo and not stereo.mono_compatible:
            warnings.append(
                f"Phase issues detected (coherence: {stereo.phase_coherence:.2f}) - may cancel in mono"
            )

        if stereo.is_stereo and stereo.stereo_width < 0.1:
            warnings.append(
                f"Narrow stereo image (width: {stereo.stereo_width:.2f}) - mostly mono"
            )

        if dynamics.lufs_integrated is not None and dynamics.lufs_integrated > -8.0:
            warnings.append(
                f"Very loud for streaming: {dynamics.lufs_integrated:.1f} LUFS "
                f"(target: -14 LUFS for Spotify)"
            )

        if 0.0 < dynamics.crest_factor_db < 6.0:
            warnings.append(
                f"Low crest factor: {dynamics.crest_factor_db:.1f} dB (possibly over-compressed)"
            )

        return warnings

    @staticmethod
    def _linear_to_db(linear_value: float) -> float:
        if linear_value <= 0:
            return float('-inf')
        return float(20 * np.log10(linear_value))

    @staticmethod
    def _ratio_to_db(ratio: float) -> float:
        if ratio <= 0:
            return float('-inf')
        return float(10 * np.log10(ratio))
