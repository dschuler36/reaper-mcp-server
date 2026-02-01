import pytest
import numpy as np
import soundfile as sf
import tempfile
import os

from reaper_mcp_server.audio_analyzer import AudioAnalyzer


@pytest.fixture
def test_mono_wav():
    """Create a test mono WAV file with clean audio."""
    # Create 1 second of mono sine wave at 440Hz, -12dB
    sr = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration))
    frequency = 440
    amplitude = 0.25  # Approximately -12 dBFS
    audio = amplitude * np.sin(2 * np.pi * frequency * t)

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        sf.write(f.name, audio, sr)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def test_stereo_wav():
    """Create a test stereo WAV file."""
    sr = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration))

    # Left channel: 440Hz
    left = 0.25 * np.sin(2 * np.pi * 440 * t)
    # Right channel: 550Hz (slightly different for stereo effect)
    right = 0.25 * np.sin(2 * np.pi * 550 * t)

    audio = np.column_stack((left, right))

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        sf.write(f.name, audio, sr)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def test_clipping_wav():
    """Create a WAV file with clipping."""
    sr = 44100
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration))

    # Create audio that clips (exceeds ±1.0)
    audio = 1.5 * np.sin(2 * np.pi * 440 * t)
    # Clip to ±1.0
    audio = np.clip(audio, -1.0, 1.0)

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        sf.write(f.name, audio, sr)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def test_phase_issue_wav():
    """Create a stereo WAV file with phase issues."""
    sr = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration))

    # Same frequency on both channels
    signal = 0.25 * np.sin(2 * np.pi * 440 * t)

    # Left channel normal, right channel inverted (180° out of phase)
    audio = np.column_stack((signal, -signal))

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        sf.write(f.name, audio, sr)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


def test_analyze_mono_audio(test_mono_wav):
    """Test analysis of mono audio file."""
    analyzer = AudioAnalyzer(test_mono_wav)
    result = analyzer.analyze()

    assert result.error is None
    assert result.sample_rate == 44100
    assert result.channels == 1
    assert result.duration_seconds == pytest.approx(1.0, rel=0.01)

    # Stereo analysis should indicate mono
    assert result.stereo.is_stereo is False
    assert result.stereo.stereo_width == 0.0
    assert result.stereo.mono_compatible is True


def test_analyze_stereo_audio(test_stereo_wav):
    """Test analysis of stereo audio file."""
    analyzer = AudioAnalyzer(test_stereo_wav)
    result = analyzer.analyze()

    assert result.error is None
    assert result.channels == 2

    # Stereo analysis
    assert result.stereo.is_stereo is True
    # Stereo width should be > 0 (different frequencies on L/R)
    assert result.stereo.stereo_width > 0.0


def test_clipping_detection(test_clipping_wav):
    """Test that clipping is detected."""
    analyzer = AudioAnalyzer(test_clipping_wav)
    result = analyzer.analyze()

    assert result.error is None
    assert result.level.clipping_detected is True
    assert result.level.clipped_samples_count > 0

    # Should have a warning about clipping
    assert any('clipping' in w.lower() for w in result.warnings)


def test_phase_issue_detection(test_phase_issue_wav):
    """Test detection of phase issues."""
    analyzer = AudioAnalyzer(test_phase_issue_wav)
    result = analyzer.analyze()

    assert result.error is None

    # Phase coherence should be very negative (inverted signal)
    assert result.stereo.phase_coherence < 0.0

    # Should not be mono compatible
    assert result.stereo.mono_compatible is False

    # Should have phase warning
    assert any('phase' in w.lower() for w in result.warnings)


def test_file_not_found():
    """Test handling of missing file."""
    analyzer = AudioAnalyzer("/nonexistent/path/file.wav")
    result = analyzer.analyze()

    assert result.error is not None
    assert "not found" in result.error.lower()


def test_peak_and_rms_calculation(test_mono_wav):
    """Test peak and RMS level calculations."""
    analyzer = AudioAnalyzer(test_mono_wav)
    result = analyzer.analyze()

    # Peak should be around -12 dBFS (amplitude 0.25)
    expected_peak_db = 20 * np.log10(0.25)
    assert result.level.peak_db == pytest.approx(expected_peak_db, abs=0.5)

    # RMS should be close to peak for sine wave (within a few dB)
    assert result.level.rms_db == pytest.approx(expected_peak_db, abs=5.0)


def test_frequency_analysis(test_mono_wav):
    """Test frequency analysis calculations."""
    analyzer = AudioAnalyzer(test_mono_wav)
    result = analyzer.analyze()

    # Spectral centroid should be near the test frequency (440 Hz for pure sine)
    # Allow wider range since we're analyzing a windowed signal
    assert 200 < result.frequency.spectral_centroid_hz < 2000


def test_hot_level_warning():
    """Test warning for levels that are too hot."""
    # Create very hot audio (-0.1 dBFS)
    sr = 44100
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration))
    amplitude = 0.99  # Very hot: -0.09 dBFS
    audio = amplitude * np.sin(2 * np.pi * 440 * t)

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        sf.write(f.name, audio, sr)
        temp_path = f.name

    try:
        analyzer = AudioAnalyzer(temp_path)
        result = analyzer.analyze()

        # Should have warning about hot level
        assert any('hot' in w.lower() or 'peak' in w.lower() for w in result.warnings)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_crest_factor_calculation(test_mono_wav):
    """Test crest factor (dynamic range) calculation."""
    analyzer = AudioAnalyzer(test_mono_wav)
    result = analyzer.analyze()

    # Crest factor for sine wave should be around 3 dB
    # (peak is sqrt(2) times RMS for sine wave)
    assert result.dynamics.crest_factor_db == pytest.approx(3.0, abs=1.0)
