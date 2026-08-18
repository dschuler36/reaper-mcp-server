"""Regression tests for the analysis failures found against a real project."""

import os
import tempfile

import numpy as np
import pytest
import soundfile as sf

from reaper_mcp_server.audio_analyzer import AudioAnalyzer

SR = 44100


@pytest.fixture
def write_wav():
    created = []

    def _write(data: np.ndarray, samplerate: int = SR) -> str:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            path = f.name
        sf.write(path, data, samplerate)
        created.append(path)
        return path

    yield _write

    for path in created:
        if os.path.exists(path):
            os.unlink(path)


def tone(freq: float, seconds: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return amplitude * np.sin(2 * np.pi * freq * t)


def harmonic_series(fundamental: float, seconds: float, count: int = 24) -> np.ndarray:
    """A bass-like source: strong fundamental with 1/n harmonic rolloff."""
    t = np.arange(int(seconds * SR)) / SR
    signal = np.zeros_like(t)
    for n in range(1, count + 1):
        if fundamental * n >= SR / 2:
            break
        signal += np.sin(2 * np.pi * fundamental * n * t) / n
    return 0.4 * signal / np.max(np.abs(signal))


def test_analysis_honours_the_item_region(write_wav):
    """An item plays a slice of its source; the slice is what gets measured.

    Analysing the whole file made a one-sample item report the same numbers as
    a sixteen-second one.
    """
    quiet = tone(440, 2.0, amplitude=0.01)
    loud = tone(440, 2.0, amplitude=0.9)
    path = write_wav(np.concatenate([quiet, loud]))

    whole = AudioAnalyzer(path).analyze()
    first_half = AudioAnalyzer(path, start_seconds=0.0, length_seconds=2.0).analyze()
    second_half = AudioAnalyzer(path, start_seconds=2.0, length_seconds=2.0).analyze()

    assert whole.whole_file is True
    assert first_half.whole_file is False
    assert first_half.region_start_seconds == 0.0
    assert second_half.region_start_seconds == pytest.approx(2.0)

    assert first_half.duration_seconds == pytest.approx(2.0, abs=0.01)
    assert second_half.duration_seconds == pytest.approx(2.0, abs=0.01)

    # The two halves must not report identical levels.
    assert second_half.level.peak_db > first_half.level.peak_db + 20


def test_region_is_clamped_to_the_file(write_wav):
    """An item longer than its source must not error or read past the end."""
    path = write_wav(tone(440, 1.0))

    result = AudioAnalyzer(path, start_seconds=0.5, length_seconds=10.0).analyze()

    assert result.error is None
    assert result.duration_seconds == pytest.approx(0.5, abs=0.01)


def test_zero_length_region_reports_honestly(write_wav):
    """The real project has an item of length 1e-05."""
    path = write_wav(tone(440, 1.0))

    result = AudioAnalyzer(path, start_seconds=0.0, length_seconds=0.0).analyze()

    assert result.error is not None
    assert 'empty' in result.error.lower()


def test_very_short_region_suppresses_warnings(write_wav):
    path = write_wav(tone(440, 1.0, amplitude=0.99))

    result = AudioAnalyzer(path, start_seconds=0.0, length_seconds=0.001).analyze()

    assert result.error is None
    assert len(result.warnings) == 1
    assert 'too short' in result.warnings[0]


def test_band_ratios_do_not_depend_on_duration(write_wav):
    """The core of the 100%-fire-rate bug.

    The FFT was unnormalised, so band energy scaled with sample count and a
    long file read tens of dB hotter than a short one of identical material.
    Any absolute threshold then fired on whatever happened to be longest.
    """
    def two_band(seconds: float) -> np.ndarray:
        return tone(100, seconds, 0.4) + tone(800, seconds, 0.2)

    short = AudioAnalyzer(write_wav(two_band(1.0))).analyze()
    long = AudioAnalyzer(write_wav(two_band(20.0))).analyze()

    assert long.duration_seconds > short.duration_seconds * 15

    for band in ('low_freq_ratio', 'mid_freq_ratio'):
        assert getattr(short.frequency, band) == pytest.approx(
            getattr(long.frequency, band), abs=0.01
        )
        assert getattr(short.frequency, band) > 0.05

    assert short.frequency.low_freq_energy_db == pytest.approx(
        long.frequency.low_freq_energy_db, abs=1.0
    )


def test_bass_material_is_not_called_muddy(write_wav):
    """A bass being bass is not a finding."""
    path = write_wav(harmonic_series(55.0, 3.0))

    result = AudioAnalyzer(path).analyze()

    assert result.frequency.low_freq_ratio > 0.5
    assert not any('boxy' in w.lower() or 'muddy' in w.lower() for w in result.warnings)
    # The old absolute "dark mix" warning fired on every bass track.
    assert not any('dark' in w.lower() for w in result.warnings)


def test_genuinely_boxy_material_is_flagged(write_wav):
    """Energy piled into 200-500 Hz relative to 500-2000 Hz still warns."""
    boxy = tone(300, 3.0, amplitude=0.5) + tone(380, 3.0, amplitude=0.4)
    boxy += tone(1200, 3.0, amplitude=0.005)
    path = write_wav(boxy)

    result = AudioAnalyzer(path).analyze()

    assert result.frequency.low_mid_tilt_db > 10.0
    assert any('boxy' in w.lower() for w in result.warnings)


def test_missing_source_is_not_reported_as_a_missing_file():
    """MIDI items have no audio path; 'File not found: ' looked like a bug."""
    result = AudioAnalyzer('').analyze()

    assert result.error == 'No audio source for this item'


def test_dc_offset_is_detected(write_wav):
    path = write_wav(tone(440, 1.0, amplitude=0.3) + 0.05)

    result = AudioAnalyzer(path).analyze()

    assert result.level.dc_offset == pytest.approx(0.05, abs=0.005)
    assert any('dc offset' in w.lower() for w in result.warnings)


def test_unmeasurable_loudness_is_none_not_a_default(write_wav):
    """-23.0 LUFS was indistinguishable from a real measurement."""
    path = write_wav(tone(440, 1.0))

    short = AudioAnalyzer(path, start_seconds=0.0, length_seconds=0.1).analyze()
    full = AudioAnalyzer(path).analyze()

    assert short.dynamics.lufs_integrated is None
    assert full.dynamics.lufs_integrated is not None


def test_results_are_labelled_pre_fx(write_wav):
    path = write_wav(tone(440, 1.0))

    assert 'pre-fx' in AudioAnalyzer(path).analyze().signal_stage


def test_silence_does_not_produce_nan_correlation(write_wav):
    """A silent stereo region has undefined correlation."""
    path = write_wav(np.zeros((SR, 2)))

    result = AudioAnalyzer(path).analyze()

    assert result.error is None
    assert not np.isnan(result.stereo.phase_coherence)
