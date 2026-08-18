from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FX:
    name: str
    encoded_param: str
    bypassed: bool
    fx_type: str = ''
    preset_name: str = ''


@dataclass
class LevelAnalysis:
    peak_db: float
    rms_db: float
    clipping_detected: bool
    clipped_samples_count: int
    dc_offset: float = 0.0


@dataclass
class FrequencyAnalysis:
    spectral_centroid_hz: float
    # Each band's share of total spectral power, in dB (so always <= 0).
    # Relative rather than absolute: an absolute figure scales with clip
    # length, which made cross-file comparison meaningless.
    low_freq_energy_db: float
    mid_freq_energy_db: float
    high_freq_energy_db: float
    # The same shares as plain fractions, summing to ~1.0.
    low_freq_ratio: float = 0.0
    mid_freq_ratio: float = 0.0
    high_freq_ratio: float = 0.0
    # 200-500 Hz share. Overlaps the mid band; this is the range that actually
    # sounds boxy.
    mud_ratio: float = 0.0
    # 200-500 Hz against 500-2000 Hz, in dB. Positive means bottom-heavy mids.
    # This is what the boxiness warning tests: measuring a band against the
    # whole spectrum instead makes any bass-light source look boxy and any
    # bass guitar look muddy, regardless of how it actually sounds.
    low_mid_tilt_db: float = 0.0


@dataclass
class StereoAnalysis:
    is_stereo: bool
    stereo_width: float
    phase_coherence: float
    mono_compatible: bool


@dataclass
class DynamicsAnalysis:
    # None when loudness could not be measured (region shorter than one 400 ms
    # block, or pyloudnorm unavailable). Previously this fell back to a
    # hard-coded -23.0, which was indistinguishable from a real measurement.
    lufs_integrated: Optional[float]
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
    # Which slice of the source file was measured. When the caller asked for a
    # region these describe that region, not the whole file.
    region_start_seconds: float = 0.0
    region_length_seconds: float = 0.0
    whole_file: bool = True
    # Analysis reads the source file from disk, so it reflects neither the
    # track's FX chain nor its fader.
    signal_stage: str = 'pre-fx (raw source file)'


@dataclass
class Take:
    name: str
    source_type: str
    audio_filepath: str
    start_offset: float = 0.0
    playrate: float = 1.0
    active: bool = False
    # Populated from a take VOLPAN line. Takes after the first use TAKEVOLPAN,
    # whose field order is not verified, so they are left unset rather than
    # guessed at.
    volume: Optional[float] = None
    pan: Optional[float] = None


@dataclass
class AudioItem:
    position: float
    length: float
    audio_filepath: str
    name: str = ''
    source_type: str = ''
    mute: bool = False
    volume: float = 1.0
    pan: float = 0.0
    start_offset: float = 0.0
    playrate: float = 1.0
    fade_in_seconds: float = 0.0
    fade_out_seconds: float = 0.0
    takes: List[Take] = field(default_factory=list)


@dataclass
class TrackReceive:
    """One AUXRECV line: audio arriving from another track in this project."""

    source_track_index: int
    source_track_name: str = ''
    mode: int = 0
    volume: float = 1.0
    pan: float = 0.0
    mute: bool = False
    mono: bool = False
    phase_invert: bool = False
    source_channel: int = 0


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
    track_number: int = 0
    guid: str = ''
    # ISBUS <isbus> <depth>: 1 opens a folder, -1 (or lower) closes one.
    is_folder: bool = False
    folder_depth: int = 0
    main_send: bool = True
    num_channels: int = 2
    pan_mode: Optional[int] = None
    width: Optional[float] = None
    receives: List[TrackReceive] = field(default_factory=list)
    midi_hardware_out: Optional[int] = None
    items: List[AudioItem] = field(default_factory=list)


@dataclass
class Project:
    name: str
    location: str
    tempo: float
    time_signature: str
    total_length: float
    tracks: List[Track]
    # True when the project carries a tempo envelope with points, meaning
    # `tempo` is only the starting tempo.
    has_tempo_changes: bool = False
