from dataclasses import dataclass
from typing import List, Dict, Union


@dataclass
class FX:
    name: str
    encoded_param: str
    bypassed: bool

@dataclass
class Track:
    name: str
    volume: float
    pan: float
    mute: bool
    solo: bool
    type: str
    input_source: str
    audio_filepath: str
    fx_chain: List[FX]
    automation: Dict[str, List[Dict[str, Union[float, str]]]]
    peak_level: float
    send_levels: List[Dict[str, Union[str, float]]]


@dataclass
class Project:
    name: str
    location: str
    tempo: float
    time_signature: str
    total_length: float
    tracks: List[Track]
