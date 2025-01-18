import pytest
from reaper_mcp_server.rpp_parser import RPPParser
from pathlib import Path
import tempfile

@pytest.fixture
def sample_rpp_content():
    return '''<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019
  TEMPO 121 4 4
  <TRACK {8A4843A5-257E-9F43-98B8-8F734973B793}
    NAME "intro lead"
    PEAKCOL 16576
    VOLPAN 0.91875046047611 0 -1 -1 1
    MUTESOLO 0 0 0
    <FXCHAIN
      WNDRECT 0 428 1059 516
      SHOW 0
      LASTSEL 0
      BYPASS 0 0 0
      <VST "VST3: ValhallaSupermassive (Valhalla DSP, LLC)" ValhallaSupermassive.vst3 0 "" 588216008{565354734D617376616C68616C6C6173} ""
        yHYPI+5e7f4CAAAAAQAAAAAAAAACAAAAAAAAAAIAAAABAAAAAAAAAAIAAAAAAAAALQMAAAEAAAD//xAA
        AAAQAAAA
      >
      FLOATPOS 0 0 0 0
    >
  >
'''

@pytest.fixture
def temp_rpp_file(sample_rpp_content):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.rpp', delete=False) as f:
        f.write(sample_rpp_content)
    yield Path(f.name)
    Path(f.name).unlink()

def test_parse_project_basics(temp_rpp_file):
    parser = RPPParser(str(temp_rpp_file))
    
    assert parser.project.tempo == 121.0
    assert parser.project.time_signature == "4/4"
    assert len(parser.project.tracks) == 1

def test_parse_track_properties(temp_rpp_file):
    parser = RPPParser(str(temp_rpp_file))
    track = parser.project.tracks[0]
    
    assert track.name == "intro lead"
    assert track.volume == 0.91875046047611
    assert not track.mute
    assert not track.solo

def test_parse_fx_chain(temp_rpp_file):
    parser = RPPParser(str(temp_rpp_file))
    track = parser.project.tracks[0]
    
    assert len(track.fx_chain) == 1
    fx = track.fx_chain[0]
    assert fx.name == "VST3: ValhallaSupermassive (Valhalla DSP, LLC)"
    assert not fx.bypassed

def test_empty_project():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.rpp', delete=False) as f:
        f.write('<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n>')
        temp_path = f.name
    
    parser = RPPParser(temp_path)
    assert len(parser.project.tracks) == 0
    Path(temp_path).unlink()

def test_parse_name_with_quotes():
    parser = RPPParser.__new__(RPPParser)  # Create instance without calling __init__
    assert parser._parse_name('NAME "Track Name"') == "Track Name"
    assert parser._parse_name('NAME Track_Name') == "Track_Name"

def test_parse_volpan():
    parser = RPPParser.__new__(RPPParser)
    volume, pan = parser._parse_volpan('VOLPAN 0.5 0.3 -1 -1 1')
    assert volume == 0.5
    assert pan == 0.3

def test_parse_mutesolo():
    parser = RPPParser.__new__(RPPParser)
    mute, solo = parser._parse_mutesolo('MUTESOLO 1 1')
    assert mute == True
    assert solo == True
