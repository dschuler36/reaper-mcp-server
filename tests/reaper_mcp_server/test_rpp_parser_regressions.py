"""Regression tests for the parser failures found in a real 68-track project.

The pre-existing fixtures were hand-written minimal RPPs that happened to omit
every construct that broke the parser -- no item NAME, no item VOLPAN, no MIDI
source, no envelope blocks. These fixtures use the shapes REAPER actually
writes.
"""

import json
import os
import tempfile
from dataclasses import asdict

import pytest

from reaper_mcp_server.rpp_chunks import split_tokens, tokenize
from reaper_mcp_server.rpp_parser import RPPParser
from reaper_mcp_server.utils import remove_empty_strings, truncate_encoded_params


@pytest.fixture
def write_rpp():
    created = []

    def _write(content: str) -> str:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.RPP', delete=False) as f:
            f.write(content)
            created.append(f.name)
        return f.name

    yield _write

    for path in created:
        if os.path.exists(path):
            os.unlink(path)


MIDI_ITEM = '''    <ITEM
      POSITION {position}
      LENGTH 4.0
      MUTE 0 0
      NAME "{name}"
      VOLPAN 1 0 1 -1
      SOFFS 0
      PLAYRATE 1 1 0 -1 0 0.0025
      <SOURCE MIDI
        HASDATA 1 960 QN
        CCINTERP 32
        E 0 90 3b 6d
        E 120 80 3b 00
      >
    >
'''


def test_midi_source_does_not_truncate_the_track(write_rpp):
    """A <SOURCE MIDI> block must not be mistaken for the end of the track.

    This is what dropped four of five drum items from the real project: only
    <SOURCE WAVE was recognised, so the MIDI block's closing '>' was read as the
    item's, and the item's own '>' then closed the track.
    """
    items = ''.join(
        MIDI_ITEM.format(position=p, name='02-SSDSampler5-MIDI-glued')
        for p in (0.0, 8.0, 16.0, 24.0, 32.0)
    )
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  TEMPO 119 4 4\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-000000000001}\n'
        '    NAME SSDSampler5\n'
        f'{items}'
        '  >\n'
        '>\n'
    )

    track = RPPParser(path).project.tracks[0]

    assert len(track.items) == 5
    assert [item.position for item in track.items] == [0.0, 8.0, 16.0, 24.0, 32.0]
    assert all(item.source_type == 'MIDI' for item in track.items)


def test_envelope_block_does_not_truncate_the_track(write_rpp):
    """A track automation envelope sits before the items and must be skipped."""
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-000000000002}\n'
        '    NAME "automated track"\n'
        '    <VOLENV2\n'
        '      EGUID {BBBBBBBB-0000-0000-0000-000000000001}\n'
        '      ACT 1 -1\n'
        '      PT 0 1.13347181 0\n'
        '      PT 42.35294118 2 0\n'
        '    >\n'
        '    <ITEM\n'
        '      POSITION 1.0\n'
        '      LENGTH 2.0\n'
        '      <SOURCE WAVE\n'
        '        FILE "a.wav"\n'
        '      >\n'
        '    >\n'
        '    <ITEM\n'
        '      POSITION 5.0\n'
        '      LENGTH 2.0\n'
        '      <SOURCE WAVE\n'
        '        FILE "b.wav"\n'
        '      >\n'
        '    >\n'
        '  >\n'
        '>\n'
    )

    track = RPPParser(path).project.tracks[0]

    assert track.name == 'automated track'
    assert len(track.items) == 2


def test_item_fields_do_not_overwrite_track_fields(write_rpp):
    """An ITEM carries its own NAME and VOLPAN; neither belongs to the track.

    Reading these off a flat line stream made every track report its first
    item's name, and flattened every track's volume and pan to the item
    defaults of 1.0 and 0.0.
    """
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-000000000003}\n'
        '    NAME "MiniFreak V"\n'
        '    VOLPAN 0.41349675607783 -0.688 -1 -1 1\n'
        '    MUTESOLO 0 0 0\n'
        '    <ITEM\n'
        '      POSITION 0.0\n'
        '      LENGTH 4.0\n'
        '      NAME "08-MiniFreak V-MIDI-glued"\n'
        '      VOLPAN 1 0 1 -1\n'
        '      <SOURCE WAVE\n'
        '        FILE "x.wav"\n'
        '      >\n'
        '    >\n'
        '  >\n'
        '>\n'
    )

    track = RPPParser(path).project.tracks[0]

    assert track.name == 'MiniFreak V'
    assert track.volume == pytest.approx(0.41349675607783)
    assert track.pan == pytest.approx(-0.688)
    assert track.items[0].name == '08-MiniFreak V-MIDI-glued'


def test_large_fx_blob_does_not_hide_later_items(write_rpp):
    """A track with a >500 KB FX payload still returns every item after it."""
    blob = '\n'.join(['A' * 120 + '=='] * 5000)
    assert len(blob) > 500 * 1024

    items = ''.join(
        '    <ITEM\n'
        f'      POSITION {position}\n'
        '      LENGTH 1.0\n'
        '      <SOURCE WAVE\n'
        '        FILE "x.wav"\n'
        '      >\n'
        '    >\n'
        for position in (1.0, 2.0, 3.0)
    )
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-000000000004}\n'
        '    NAME "big fx"\n'
        '    <FXCHAIN\n'
        '      BYPASS 0 0 0\n'
        '      <VST "VST3i: SSDSampler5 (Steven Slate) (48 out)" SSDSampler5.vst3 0 "" 1 ""\n'
        f'{blob}\n'
        '      >\n'
        '      WAK 0 0\n'
        '    >\n'
        f'{items}'
        '  >\n'
        '>\n'
    )

    track = RPPParser(path).project.tracks[0]

    assert len(track.items) == 3
    assert [item.position for item in track.items] == [1.0, 2.0, 3.0]


def test_base64_payload_lines_are_kept_verbatim(write_rpp):
    """Payload lines containing '+', '/' or '=' must survive.

    Filtering payload lines on isalnum() dropped every ReaComp line (all three
    end in '='), which emptied encoded_param entirely, and silently removed
    individual lines from the plugins that did report one.
    """
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-000000000005}\n'
        '    NAME "comp"\n'
        '    <FXCHAIN\n'
        '      BYPASS 0 0 0\n'
        '      <VST "VST: ReaComp (Cockos)" reacomp.vst.dylib 0 "" 1919247213<56535472> ""\n'
        '        bWNlcu9e7f4EAAAAAQAAAAAAAAACAAAAAAAAAA==\n'
        '        776t3g3wrd7UsYQ90tNVPTSFAD1negI9AAA+/w==\n'
        '        AHN0b2NrIC0gQWNvdXN0aWMgR3VpdGFyAAAAAAA=\n'
        '      >\n'
        '      PRESETNAME "stock - Acoustic Guitar"\n'
        '      WAK 0 0\n'
        '    >\n'
        '  >\n'
        '>\n'
    )

    fx = RPPParser(path).project.tracks[0].fx_chain[0]

    assert fx.name == 'VST: ReaComp (Cockos)'
    assert fx.fx_type == 'VST'
    assert fx.preset_name == 'stock - Acoustic Guitar'

    lines = fx.encoded_param.split('\n')
    assert len(lines) == 3
    assert lines[0].endswith('==')

    import base64
    for line in lines:
        base64.b64decode(line, validate=True)


def test_encoded_param_is_truncated_only_at_serialization(write_rpp):
    """Truncation belongs to output, never to parsing."""
    blob = 'QUFB' * 2000
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-000000000006}\n'
        '    NAME "fx"\n'
        '    <FXCHAIN\n'
        '      <VST "VST3: Helix Native (Line 6)" Helix.vst3 0 "" 1 ""\n'
        f'        {blob}\n'
        '      >\n'
        '    >\n'
        '  >\n'
        '>\n'
    )

    project = RPPParser(path).project
    assert len(project.tracks[0].fx_chain[0].encoded_param) == len(blob)

    serialized = truncate_encoded_params(asdict(project))
    assert serialized['tracks'][0]['fx_chain'][0]['encoded_param'].startswith(
        '<DATA_TRUNCATED: Original size 8000 bytes>'
    )


def test_routing_and_identity_fields(write_rpp):
    """Folder depth, sends, receives and track identity are all emitted."""
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-000000000007}\n'
        '    NAME "drum folder"\n'
        '    ISBUS 1 1\n'
        '    NCHAN 48\n'
        '    MAINSEND 0 0\n'
        '  >\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-000000000008}\n'
        '    NAME "Output #1"\n'
        '    VOLPAN 0.71255818392288 0 -1 -1 1\n'
        '    ISBUS 0 -1\n'
        '    AUXRECV 0 3 1 0 0 0 0 4 0 -1:U 31 -1 \'\'\n'
        '    MIDIOUT -1\n'
        '    MAINSEND 1 0\n'
        '  >\n'
        '>\n'
    )

    source, output = RPPParser(path).project.tracks

    assert source.track_number == 1
    assert source.guid == '{AAAAAAAA-0000-0000-0000-000000000007}'
    assert source.is_folder is True
    assert source.folder_depth == 1
    assert source.num_channels == 48
    # A track that does not reach the master is not the end of the signal path.
    assert source.main_send is False

    assert output.track_number == 2
    assert output.main_send is True
    assert len(output.receives) == 1

    receive = output.receives[0]
    assert receive.source_track_index == 0
    assert receive.source_track_name == 'drum folder'
    assert receive.source_channel == 4
    assert receive.volume == 1.0


def test_unnamed_track_keeps_its_name_key(write_rpp):
    """`NAME ""` must serialize as an empty string, not vanish."""
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-000000000009}\n'
        '    NAME ""\n'
        '    VOLPAN 0.29907261314897 0 -1 -1 1\n'
        '  >\n'
        '>\n'
    )

    payload = json.loads(json.dumps(remove_empty_strings(asdict(RPPParser(path).project))))
    track = payload['tracks'][0]

    assert 'name' in track
    assert track['name'] == ''
    assert track['track_number'] == 1


def test_multiple_takes_and_active_selection(write_rpp):
    """TAKE delimits takes; TAKE SEL marks the one that plays."""
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-00000000000A}\n'
        '    NAME "lead"\n'
        '    <ITEM\n'
        '      POSITION 9.07563025210084\n'
        '      LENGTH 9.07563025210084\n'
        '      NAME 03-lead-251019_2045.wav\n'
        '      VOLPAN 1 0 1 -1\n'
        '      SOFFS 4.03361344537717\n'
        '      PLAYRATE 1 1 0 -1 0 0.0025\n'
        '      <SOURCE WAVE\n'
        '        FILE "Media/03-lead-251019_2045.wav"\n'
        '      >\n'
        '      TAKE SEL\n'
        '      NAME "03-lead reversed 001.wav"\n'
        '      SOFFS 0\n'
        '      PLAYRATE 1 1 0 -1 0 0.0025\n'
        '      <SOURCE WAVE\n'
        '        FILE "Media/03-lead reversed 001.wav"\n'
        '      >\n'
        '    >\n'
        '  >\n'
        '>\n'
    )

    item = RPPParser(path).project.tracks[0].items[0]

    assert len(item.takes) == 2
    assert item.takes[0].active is False
    assert item.takes[1].active is True
    # Item-level fields follow the take that actually plays.
    assert item.name == '03-lead reversed 001.wav'
    assert item.audio_filepath.endswith('03-lead reversed 001.wav')
    assert item.start_offset == 0.0


def test_single_take_item_is_active_by_default(write_rpp):
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-00000000000B}\n'
        '    NAME "t"\n'
        '    <ITEM\n'
        '      POSITION 0.0\n'
        '      LENGTH 1.0\n'
        '      NAME only.wav\n'
        '      SOFFS 2.5\n'
        '      PLAYRATE 1.5 1 0 -1 0 0.0025\n'
        '      MUTE 1 0\n'
        '      FADEIN 1 0.25 0 1 0 0 0\n'
        '      FADEOUT 1 0.5 0 1 0 0 0\n'
        '      <SOURCE WAVE\n'
        '        FILE "only.wav"\n'
        '      >\n'
        '    >\n'
        '  >\n'
        '>\n'
    )

    item = RPPParser(path).project.tracks[0].items[0]

    assert len(item.takes) == 1
    assert item.takes[0].active is True
    assert item.start_offset == 2.5
    assert item.playrate == 1.5
    # A muted item inside an unmuted track otherwise looks active in the output.
    assert item.mute is True
    assert item.fade_in_seconds == 0.25
    assert item.fade_out_seconds == 0.5


def test_reversed_section_source_resolves_to_the_real_file(write_rpp):
    """Reversed/trimmed items nest the real source inside a SECTION."""
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-00000000000C}\n'
        '    NAME "rev"\n'
        '    <ITEM\n'
        '      POSITION 0.0\n'
        '      LENGTH 3.0\n'
        '      <SOURCE SECTION\n'
        '        LENGTH 3.0\n'
        '        MODE 3\n'
        '        <SOURCE WAVE\n'
        '          FILE "Media/real.wav"\n'
        '        >\n'
        '      >\n'
        '    >\n'
        '  >\n'
        '>\n'
    )

    item = RPPParser(path).project.tracks[0].items[0]

    assert item.source_type == 'WAVE'
    assert item.audio_filepath.endswith('Media/real.wav')


def test_total_length_spans_the_arrangement(write_rpp):
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  TEMPO 119 4 4\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-00000000000D}\n'
        '    NAME "a"\n'
        '    <ITEM\n'
        '      POSITION 0.0\n'
        '      LENGTH 10.0\n'
        '      <SOURCE WAVE\n'
        '        FILE "a.wav"\n'
        '      >\n'
        '    >\n'
        '  >\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-00000000000E}\n'
        '    NAME "b"\n'
        '    <ITEM\n'
        '      POSITION 125.0\n'
        '      LENGTH 42.83\n'
        '      <SOURCE WAVE\n'
        '        FILE "b.wav"\n'
        '      >\n'
        '    >\n'
        '  >\n'
        '>\n'
    )

    project = RPPParser(path).project

    assert project.total_length == pytest.approx(167.83)
    assert project.tempo == 119.0
    assert project.time_signature == '4/4'
    assert project.has_tempo_changes is False


def test_tempo_changes_are_flagged(write_rpp):
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  TEMPO 119 4 4\n'
        '  <TEMPOENVEX\n'
        '    ACT 1 -1\n'
        '    PT 0 119 0\n'
        '    PT 30.5 140 0\n'
        '  >\n'
        '>\n'
    )

    assert RPPParser(path).project.has_tempo_changes is True


# -- tokenizer ---------------------------------------------------------------


def test_tokenizer_tracks_depth():
    root = tokenize([
        '<REAPER_PROJECT 0.1',
        '  <TRACK {GUID}',
        '    NAME "outer"',
        '    <ITEM',
        '      <SOURCE MIDI',
        '        E 0 90 3b 6d',
        '      >',
        '    >',
        '  >',
        '>',
    ])

    project = root.find('REAPER_PROJECT')
    track = project.find('TRACK')
    item = track.find('ITEM')

    assert track.args == ['{GUID}']
    assert track.tokens('NAME') == ['outer']
    assert item.find('SOURCE').args == ['MIDI']


def test_tokenizer_preserves_body_order():
    root = tokenize([
        '<FXCHAIN',
        'BYPASS 1 0 0',
        '<VST "a"',
        '>',
        'PRESETNAME "p"',
        '>',
    ])

    chain = root.find('FXCHAIN')
    kinds = [entry if isinstance(entry, str) else entry.name for entry in chain.body]
    assert kinds == ['BYPASS 1 0 0', 'VST', 'PRESETNAME "p"']


def test_tokenizer_survives_unbalanced_close():
    """A stray '>' must not unwind past the root."""
    root = tokenize(['>', '<TRACK', 'NAME "x"', '>', '>', '>'])
    assert root.find('TRACK').tokens('NAME') == ['x']


def test_split_tokens_quoting():
    assert split_tokens('NAME "Output #1"') == ['NAME', 'Output #1']
    assert split_tokens("NAME 'has \" quote'") == ['NAME', 'has " quote']
    assert split_tokens('NAME `both \' and "`') == ['NAME', 'both \' and "']
    assert split_tokens('VOLPAN 1 0 -1 -1 1') == ['VOLPAN', '1', '0', '-1', '-1', '1']
    # The VST line embeds angle brackets mid-token.
    assert split_tokens('<VST "n" f.dylib 0 "" 1919247213<5653> ""')[-2] == '1919247213<5653>'


def test_bypass_applies_to_the_following_plugin(write_rpp):
    path = write_rpp(
        '<REAPER_PROJECT 0.1 "7.22/macOS-arm64" 1735524019\n'
        '  <TRACK {AAAAAAAA-0000-0000-0000-00000000000F}\n'
        '    NAME "t"\n'
        '    <FXCHAIN\n'
        '      BYPASS 1 0 0\n'
        '      <VST "VST: ReaTune (Cockos)" reatune.dylib 0 "" 1 ""\n'
        '        AAAA\n'
        '      >\n'
        '      WAK 0 0\n'
        '      BYPASS 0 0 0\n'
        '      <VST "VST: ReaEQ (Cockos)" reaeq.dylib 0 "" 1 ""\n'
        '        BBBB\n'
        '      >\n'
        '      WAK 0 0\n'
        '    >\n'
        '  >\n'
        '>\n'
    )

    fx_chain = RPPParser(path).project.tracks[0].fx_chain

    assert [fx.name for fx in fx_chain] == [
        'VST: ReaTune (Cockos)',
        'VST: ReaEQ (Cockos)',
    ]
    assert fx_chain[0].bypassed is True
    assert fx_chain[1].bypassed is False
