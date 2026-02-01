import pytest
import tempfile
import os
from pathlib import Path

from reaper_mcp_server.rpp_parser import RPPParser


@pytest.fixture
def sample_rpp_with_items():
    """Sample RPP content with ITEM blocks."""
    return '''<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019
  TEMPO 120 4 4
  <TRACK {12345678-1234-1234-1234-123456789ABC}
    NAME "Test Track"
    VOLPAN 1.0 0.0 -1 -1 1
    MUTESOLO 0 0
    <ITEM
      POSITION 0.0
      LENGTH 5.5
      <SOURCE WAVE
        FILE "test_audio.wav"
      >
    >
    <ITEM
      POSITION 6.0
      LENGTH 3.2
      <SOURCE WAVE
        FILE "test_audio2.wav"
      >
    >
  >
>
'''


@pytest.fixture
def sample_rpp_with_absolute_path():
    """Sample RPP content with absolute path."""
    return '''<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019
  TEMPO 120 4 4
  <TRACK {12345678-1234-1234-1234-123456789ABC}
    NAME "Absolute Path Track"
    <ITEM
      POSITION 0.0
      LENGTH 2.0
      <SOURCE WAVE
        FILE "/absolute/path/to/audio.wav"
      >
    >
  >
>
'''


@pytest.fixture
def temp_rpp_file(sample_rpp_with_items):
    """Create a temporary RPP file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.RPP', delete=False) as f:
        f.write(sample_rpp_with_items)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_rpp_file_absolute(sample_rpp_with_absolute_path):
    """Create a temporary RPP file with absolute path."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.RPP', delete=False) as f:
        f.write(sample_rpp_with_absolute_path)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


def test_parse_item_block(temp_rpp_file):
    """Test that ITEM blocks are parsed correctly."""
    parser = RPPParser(str(temp_rpp_file))

    assert len(parser.project.tracks) == 1
    track = parser.project.tracks[0]

    # Check that items were parsed
    assert len(track.items) == 2

    # Check first item
    item1 = track.items[0]
    assert item1.position == 0.0
    assert item1.length == 5.5
    assert 'test_audio.wav' in item1.audio_filepath

    # Check second item
    item2 = track.items[1]
    assert item2.position == 6.0
    assert item2.length == 3.2
    assert 'test_audio2.wav' in item2.audio_filepath


def test_parse_source_wave_file(temp_rpp_file):
    """Test that SOURCE WAVE FILE paths are extracted."""
    parser = RPPParser(str(temp_rpp_file))

    track = parser.project.tracks[0]
    item = track.items[0]

    # File path should be resolved relative to RPP file location
    assert item.audio_filepath.endswith('test_audio.wav')
    assert os.path.isabs(item.audio_filepath)


def test_relative_path_resolution(temp_rpp_file):
    """Test that relative paths are resolved correctly."""
    parser = RPPParser(str(temp_rpp_file))

    track = parser.project.tracks[0]
    item = track.items[0]

    # Path should be absolute (resolved from RPP file location)
    assert os.path.isabs(item.audio_filepath)

    # Should be resolved relative to the RPP file's directory
    rpp_dir = os.path.dirname(temp_rpp_file)
    expected_path = os.path.abspath(os.path.join(rpp_dir, 'test_audio.wav'))
    assert item.audio_filepath == expected_path


def test_absolute_path_unchanged(temp_rpp_file_absolute):
    """Test that absolute paths remain absolute."""
    parser = RPPParser(str(temp_rpp_file_absolute))

    track = parser.project.tracks[0]
    item = track.items[0]

    # Absolute path should remain as-is
    assert item.audio_filepath == "/absolute/path/to/audio.wav"


def test_track_with_items_and_fx():
    """Test parsing track with both items and FX chain."""
    content = '''<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019
  <TRACK {12345678-1234-1234-1234-123456789ABC}
    NAME "Complex Track"
    <FXCHAIN
      <VST "VST3: TestPlugin" TestPlugin.vst3
      >
      BYPASS 0 0
    >
    <ITEM
      POSITION 1.0
      LENGTH 2.0
      <SOURCE WAVE
        FILE "test.wav"
      >
    >
  >
>
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.RPP', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        parser = RPPParser(str(temp_path))
        track = parser.project.tracks[0]

        # Both FX and items should be parsed
        assert len(track.fx_chain) == 1
        assert track.fx_chain[0].name == "VST3: TestPlugin"

        assert len(track.items) == 1
        assert track.items[0].position == 1.0
        assert track.items[0].length == 2.0
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_empty_track_has_empty_items():
    """Test that tracks without items have empty items list."""
    content = '''<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019
  <TRACK {12345678-1234-1234-1234-123456789ABC}
    NAME "Empty Track"
    VOLPAN 1.0 0.0 -1 -1 1
  >
>
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.RPP', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        parser = RPPParser(str(temp_path))
        track = parser.project.tracks[0]

        # Items list should be empty but not None
        assert track.items == []
        assert isinstance(track.items, list)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
