import os
from typing import List, Optional, Union

from .rpp_chunks import Chunk, split_tokens, tokenize_file
from .reaper_dataclasses import (
    AudioItem,
    FX,
    Project,
    Take,
    Track,
    TrackReceive,
)

# Chunk names that hold a plugin instance inside an FXCHAIN.
PLUGIN_CHUNKS = {'VST', 'AU', 'AUDIOUNIT', 'CLAP', 'DX', 'LV2', 'JS'}


def _to_float(tokens: Optional[List[str]], index: int, default: float = 0.0) -> float:
    if not tokens or index >= len(tokens):
        return default
    try:
        return float(tokens[index])
    except ValueError:
        return default


def _to_int(tokens: Optional[List[str]], index: int, default: int = 0) -> int:
    if not tokens or index >= len(tokens):
        return default
    try:
        return int(float(tokens[index]))
    except ValueError:
        return default


def _to_bool(tokens: Optional[List[str]], index: int, default: bool = False) -> bool:
    if not tokens or index >= len(tokens):
        return default
    try:
        return bool(int(float(tokens[index])))
    except ValueError:
        return default


class RPPParser:
    """Parses a REAPER .RPP project into the dataclasses in reaper_dataclasses.

    Structure is resolved by rpp_chunks.tokenize first, so a field is only ever
    read from the chunk that owns it. Reading fields off a flat line stream is
    what previously let an ITEM's NAME and VOLPAN overwrite its track's.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.project = Project(
            name=os.path.basename(file_path).rsplit('.', 1)[0],
            location=file_path,
            tempo=0.0,
            time_signature='',
            total_length=0.0,
            tracks=[],
        )
        self.parse_file()

    def parse_file(self) -> None:
        root = tokenize_file(self.file_path)
        project_chunk = root.find('REAPER_PROJECT')
        if project_chunk is None:
            return

        self._parse_tempo(project_chunk)

        for index, track_chunk in enumerate(project_chunk.find_all('TRACK'), start=1):
            self.project.tracks.append(self._parse_track(track_chunk, index))

        self._resolve_receive_names()
        self.project.total_length = self._compute_total_length()

    # -- project -----------------------------------------------------------

    def _parse_tempo(self, project_chunk: Chunk) -> None:
        tokens = project_chunk.tokens('TEMPO')
        if tokens:
            self.project.tempo = _to_float(tokens, 0)
            if len(tokens) >= 3:
                self.project.time_signature = f"{tokens[1]}/{tokens[2]}"

        tempo_env = project_chunk.find('TEMPOENVEX')
        if tempo_env is not None:
            # A single point is just the starting tempo restated.
            self.project.has_tempo_changes = len(tempo_env.tokens_all('PT')) > 1

    def _compute_total_length(self) -> float:
        ends = [
            item.position + item.length
            for track in self.project.tracks
            for item in track.items
        ]
        return max(ends) if ends else 0.0

    def _resolve_receive_names(self) -> None:
        for track in self.project.tracks:
            for receive in track.receives:
                # AUXRECV holds a 0-based index into project track order.
                if 0 <= receive.source_track_index < len(self.project.tracks):
                    receive.source_track_name = (
                        self.project.tracks[receive.source_track_index].name
                    )

    # -- tracks ------------------------------------------------------------

    def _parse_track(self, chunk: Chunk, track_number: int) -> Track:
        volpan = chunk.tokens('VOLPAN')
        mutesolo = chunk.tokens('MUTESOLO')
        isbus = chunk.tokens('ISBUS')
        mainsend = chunk.tokens('MAINSEND')
        panmode = chunk.tokens('PANMODE')
        width = chunk.tokens('WIDTH')
        midiout = chunk.tokens('MIDIOUT')

        name_tokens = chunk.tokens('NAME')
        name = name_tokens[0] if name_tokens else ''

        items = [self._parse_item(item_chunk) for item_chunk in chunk.find_all('ITEM')]
        fx_chain = self._parse_fx_chain(chunk.find('FXCHAIN'))

        return Track(
            name=name,
            volume=_to_float(volpan, 0, 1.0),
            pan=_to_float(volpan, 1, 0.0),
            mute=_to_bool(mutesolo, 0),
            solo=_to_bool(mutesolo, 1),
            type='midi' if any(i.source_type == 'MIDI' for i in items) else 'audio',
            input_source='',
            audio_filepath='',
            fx_chain=fx_chain,
            track_number=track_number,
            guid=chunk.args[0] if chunk.args else '',
            is_folder=_to_int(isbus, 0) == 1,
            folder_depth=_to_int(isbus, 1),
            main_send=_to_bool(mainsend, 0, True),
            num_channels=_to_int(chunk.tokens('NCHAN'), 0, 2),
            pan_mode=_to_int(panmode, 0) if panmode else None,
            width=_to_float(width, 0, 1.0) if width else None,
            receives=[self._parse_receive(t) for t in chunk.tokens_all('AUXRECV')],
            midi_hardware_out=_to_int(midiout, 0) if midiout else None,
            items=items,
        )

    @staticmethod
    def _parse_receive(tokens: List[str]) -> TrackReceive:
        return TrackReceive(
            source_track_index=_to_int(tokens, 0, -1),
            mode=_to_int(tokens, 1),
            volume=_to_float(tokens, 2, 1.0),
            pan=_to_float(tokens, 3, 0.0),
            mute=_to_bool(tokens, 4),
            mono=_to_bool(tokens, 5),
            phase_invert=_to_bool(tokens, 6),
            source_channel=_to_int(tokens, 7),
        )

    # -- fx ----------------------------------------------------------------

    def _parse_fx_chain(self, chunk: Optional[Chunk]) -> List[FX]:
        if chunk is None:
            return []

        fx_chain: List[FX] = []
        pending_bypass = False
        last_fx: Optional[FX] = None

        for entry in chunk.body:
            if isinstance(entry, str):
                tokens = split_tokens(entry)
                if not tokens:
                    continue
                if tokens[0] == 'BYPASS':
                    pending_bypass = _to_bool(tokens[1:], 0)
                elif tokens[0] == 'PRESETNAME' and last_fx is not None:
                    # PRESETNAME trails the plugin chunk it belongs to.
                    last_fx.preset_name = tokens[1] if len(tokens) > 1 else ''
            elif entry.name in PLUGIN_CHUNKS:
                last_fx = self._create_fx(entry, pending_bypass)
                fx_chain.append(last_fx)
                pending_bypass = False

        return fx_chain

    @staticmethod
    def _create_fx(chunk: Chunk, bypassed: bool) -> FX:
        # Every payload line is kept verbatim. A plugin chunk is a sequence of
        # independently-padded base64 records (config header, plugin state,
        # preset name), not one continuous stream, so the lines are joined with
        # newlines and each decodes on its own. Concatenating them instead
        # yields a blob that fails base64 validation.
        return FX(
            name=chunk.args[0] if chunk.args else 'Unknown',
            encoded_param='\n'.join(chunk.lines),
            bypassed=bypassed,
            fx_type=chunk.name,
        )

    # -- items and takes ---------------------------------------------------

    def _parse_item(self, chunk: Chunk) -> AudioItem:
        takes = self._parse_takes(chunk)
        active = next((take for take in takes if take.active), takes[0] if takes else None)

        volpan = chunk.tokens('VOLPAN')
        fadein = chunk.tokens('FADEIN')
        fadeout = chunk.tokens('FADEOUT')

        return AudioItem(
            position=_to_float(chunk.tokens('POSITION'), 0),
            length=_to_float(chunk.tokens('LENGTH'), 0),
            audio_filepath=active.audio_filepath if active else '',
            name=active.name if active else '',
            source_type=active.source_type if active else '',
            mute=_to_bool(chunk.tokens('MUTE'), 0),
            # REAPER stores the item volume/pan knob on the take; this is the
            # first take's VOLPAN line.
            volume=_to_float(volpan, 0, 1.0),
            pan=_to_float(volpan, 1, 0.0),
            start_offset=active.start_offset if active else 0.0,
            playrate=active.playrate if active else 1.0,
            fade_in_seconds=_to_float(fadein, 1),
            fade_out_seconds=_to_float(fadeout, 1),
            takes=takes,
        )

    def _parse_takes(self, chunk: Chunk) -> List[Take]:
        """Split an ITEM body into takes.

        Takes are not nested chunks -- they are delimited by bare ``TAKE``
        lines, with the first take implicit. ``TAKE SEL`` marks the active one.
        """
        segments: List[List[Union[str, Chunk]]] = [[]]
        selected_index: Optional[int] = None

        for entry in chunk.body:
            if isinstance(entry, str):
                tokens = split_tokens(entry)
                if tokens and tokens[0] == 'TAKE':
                    segments.append([])
                    if 'SEL' in tokens[1:]:
                        selected_index = len(segments) - 1
                    continue
            segments[-1].append(entry)

        takes = [self._parse_take(segment) for segment in segments]
        if takes:
            # With no explicit selection the first take plays.
            takes[selected_index if selected_index is not None else 0].active = True
        return takes

    def _parse_take(self, segment: List[Union[str, Chunk]]) -> Take:
        take_chunk = Chunk(name='TAKE', body=list(segment))
        source = take_chunk.find('SOURCE')

        name_tokens = take_chunk.tokens('NAME')
        volpan = take_chunk.tokens('VOLPAN')

        return Take(
            name=name_tokens[0] if name_tokens else '',
            source_type=self._source_type(source),
            audio_filepath=self._source_file(source),
            start_offset=_to_float(take_chunk.tokens('SOFFS'), 0),
            playrate=_to_float(take_chunk.tokens('PLAYRATE'), 0, 1.0),
            volume=_to_float(volpan, 0, 1.0) if volpan else None,
            pan=_to_float(volpan, 1, 0.0) if volpan else None,
        )

    def _source_type(self, source: Optional[Chunk]) -> str:
        if source is None:
            return ''
        kind = source.args[0] if source.args else ''
        if kind == 'SECTION':
            # Reversed/trimmed items wrap the real source in a SECTION.
            inner = source.find('SOURCE')
            return self._source_type(inner) if inner else kind
        return kind

    def _source_file(self, source: Optional[Chunk]) -> str:
        if source is None:
            return ''
        tokens = source.tokens('FILE')
        if tokens is None:
            inner = source.find('SOURCE')
            return self._source_file(inner) if inner else ''
        return self._resolve_path(tokens[0] if tokens else '')

    def _resolve_path(self, path: str) -> str:
        if path and not os.path.isabs(path):
            base_dir = os.path.dirname(self.file_path)
            return os.path.abspath(os.path.join(base_dir, path))
        return path

    # -- line helpers kept for direct unit testing -------------------------

    @staticmethod
    def _parse_name(line: str) -> str:
        tokens = split_tokens(line)
        return tokens[1] if len(tokens) > 1 else ''

    @staticmethod
    def _parse_volpan(line: str) -> tuple[float, float]:
        tokens = split_tokens(line)[1:]
        return _to_float(tokens, 0, 1.0), _to_float(tokens, 1, 0.0)

    @staticmethod
    def _parse_mutesolo(line: str) -> tuple[bool, bool]:
        tokens = split_tokens(line)[1:]
        return _to_bool(tokens, 0), _to_bool(tokens, 1)

    @staticmethod
    def _parse_position(line: str) -> float:
        return _to_float(split_tokens(line)[1:], 0)

    @staticmethod
    def _parse_length(line: str) -> float:
        return _to_float(split_tokens(line)[1:], 0)

    def _parse_file_path(self, line: str) -> str:
        tokens = split_tokens(line)
        return self._resolve_path(tokens[1] if len(tokens) > 1 else '')
