from dataclasses import dataclass, field
from typing import List, Dict, Union, Optional


@dataclass
class FX:
    name: str
    encoded_param: str
    bypassed: bool


@dataclass
class LevelAnalysis:
    peak_db: float
    rms_db: float
    clipping_detected: bool
    clipped_samples_count: int


@dataclass
class FrequencyAnalysis:
    spectral_centroid_hz: float
    low_freq_energy_db: float
    mid_freq_energy_db: float
    high_freq_energy_db: float


@dataclass
class StereoAnalysis:
    is_stereo: bool
    stereo_width: float
    phase_coherence: float
    mono_compatible: bool


@dataclass
class DynamicsAnalysis:
    lufs_integrated: float
    true_peak_db: float
    crest_factor_db: float


@dataclass
class AudioAnalysisResult:
    file_path: str
    sample_rate: int
    duration_seconds: float
    channels: int
    level: LevelAnalysis
    frequency: FrequencyAnalysis
    stereo: StereoAnalysis
    dynamics: DynamicsAnalysis
    warnings: List[str]
    error: Optional[str] = None


@dataclass
class AudioItem:
    position: float
    length: float
    audio_filepath: str
    audio_analysis: Optional['AudioAnalysisResult'] = None


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
    items: List[AudioItem] = field(default_factory=list)


@dataclass
class Project:
    name: str
    location: str
    tempo: float
    time_signature: str
    total_length: float
    tracks: List[Track]
