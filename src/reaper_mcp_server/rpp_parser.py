import os
from typing import List, Dict, Optional

from .reaper_dataclasses import Project, Track, FX, AudioItem
from .utils import remove_empty_strings


class RPPParser:
    
    def __init__(self, file_path):
        self.MAX_ENCODED_DATA_LENGTH = 1024
        self.file_path = file_path
        self.project = Project(
            name=file_path.split('/')[-1].rsplit('.', 1)[0],
            location=file_path,
            tempo=0.0,
            time_signature='',
            total_length=0.0,
            tracks=[]
        )
        self.parse_file()
    
    def parse_file(self):
        with open(self.file_path, 'r') as f:
            lines = f.readlines()
            
        current_track: Optional[Dict] = None
        track_stack: List[Dict] = []
        current_fx_chain: List[FX] = []
        in_fx_chain = False
        current_fx: Optional[Dict] = None
        in_item_block = False
        in_source_block = False
        current_item: Optional[Dict] = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('TEMPO'):
                self._parse_tempo(line)
                
            elif line.startswith('<TRACK'):
                current_track = self._create_empty_track()
                track_stack.append(current_track)
                
            elif line.startswith('NAME') and current_track:
                current_track['name'] = self._parse_name(line)
            
            elif line.startswith('<FXCHAIN'):
                in_fx_chain = True
                current_fx_chain = []
                
            elif line.startswith('<VST') and in_fx_chain:
                if current_fx:
                    current_fx_chain.append(self._create_fx(current_fx))
                current_fx = self._parse_vst_line(line)
                
            elif line.startswith('BYPASS') and current_fx:
                current_fx['bypassed'] = self._parse_bypass(line)
                
            elif in_fx_chain and current_fx and line.strip().isalnum():
                current_fx['encoded_data'].append(line)
                
            elif line == '>' and in_fx_chain:
                if current_fx:
                    current_fx_chain.append(self._create_fx(current_fx))
                    current_fx = None
                else:
                    # Only close FX chain if there's no open FX (closing the FXCHAIN block itself)
                    in_fx_chain = False
                    if current_track:
                        current_track['fx_chain'] = current_fx_chain
                    current_fx_chain = []
            
            elif line.startswith('VOLPAN') and current_track:
                volume, pan = self._parse_volpan(line)
                current_track['volume'] = volume
                current_track['pan'] = pan
            
            elif line.startswith('MUTESOLO') and current_track:
                mute, solo = self._parse_mutesolo(line)
                current_track['mute'] = mute
                current_track['solo'] = solo

            elif line.startswith('<ITEM') and current_track:
                in_item_block = True
                current_item = {'position': 0.0, 'length': 0.0, 'audio_filepath': ''}

            elif line.startswith('POSITION') and in_item_block and current_item:
                current_item['position'] = self._parse_position(line)

            elif line.startswith('LENGTH') and in_item_block and current_item:
                current_item['length'] = self._parse_length(line)

            elif line.startswith('<SOURCE WAVE') and in_item_block:
                in_source_block = True

            elif line.startswith('FILE') and in_source_block and current_item:
                current_item['audio_filepath'] = self._parse_file_path(line)

            elif line == '>' and in_item_block:
                if in_source_block:
                    in_source_block = False
                elif current_item:
                    if current_track:
                        current_track['items'].append(self._create_audio_item(current_item))
                    current_item = None
                    in_item_block = False

            elif line == '>' and track_stack:
                finished_track = track_stack.pop()
                if finished_track:
                    track = self._create_track_from_dict(finished_track)
                    self.project.tracks.append(track)
                current_track = track_stack[-1] if track_stack else None

    def _parse_tempo(self, line: str) -> None:
        parts = line.split()
        if len(parts) >= 3:
            self.project.tempo = float(parts[1])
            self.project.time_signature = f"{parts[2]}/{parts[3]}"

    @staticmethod
    def _create_empty_track() -> Dict:
        return {
            'name': '',
            'volume': 1.0,
            'pan': 0.0,
            'mute': False,
            'solo': False,
            'type': 'audio',
            'input_source': '',
            'audio_filepath': '',
            'fx_chain': [],
            'automation': {},
            'peak_level': 0.0,
            'send_levels': [],
            'items': []
        }

    @staticmethod
    def _parse_name(line: str) -> str:
        if '"' in line:
            return line.split('"')[1]
        return line.split(' ', 1)[1]

    @staticmethod
    def _parse_vst_line(line: str) -> Dict:
        parts = line.split('"')
        fx_name = parts[1] if len(parts) > 1 else "Unknown"
        return {
            'name': fx_name,
            'encoded_data': [],
            'bypassed': False
        }

    @staticmethod
    def _parse_bypass(line: str) -> bool:
        parts = line.split()
        return bool(int(parts[1]))

    @staticmethod
    def _parse_volpan( line: str) -> tuple[float, float]:
        parts = line.split()
        if len(parts) >= 3:
            return float(parts[1]), float(parts[2])
        return 1.0, 0.0

    @staticmethod
    def _parse_mutesolo(line: str) -> tuple[bool, bool]:
        parts = line.split()
        if len(parts) >= 3:
            return bool(int(parts[1])), bool(int(parts[2]))
        return False, False

    def _create_fx(self, fx_dict: Dict) -> FX:
        encoded_data = ''.join(fx_dict['encoded_data'])
        if len(encoded_data) > self.MAX_ENCODED_DATA_LENGTH:
            encoded_data = f"<DATA_TRUNCATED: Original size {len(encoded_data)} bytes>"
        
        return FX(
            name=fx_dict['name'],
            encoded_param=encoded_data,
            bypassed=fx_dict['bypassed']
        )

    @staticmethod
    def _parse_position(line: str) -> float:
        parts = line.split()
        if len(parts) >= 2:
            return float(parts[1])
        return 0.0

    @staticmethod
    def _parse_length(line: str) -> float:
        parts = line.split()
        if len(parts) >= 2:
            return float(parts[1])
        return 0.0

    def _parse_file_path(self, line: str) -> str:
        # Extract path from FILE line (handles quoted paths)
        if '"' in line:
            path = line.split('"')[1]
        else:
            parts = line.split()
            path = parts[1] if len(parts) > 1 else ''

        # Resolve relative paths
        if path and not os.path.isabs(path):
            base_dir = os.path.dirname(self.file_path)
            path = os.path.abspath(os.path.join(base_dir, path))

        return path

    @staticmethod
    def _create_audio_item(item_dict: Dict) -> AudioItem:
        return AudioItem(
            position=item_dict['position'],
            length=item_dict['length'],
            audio_filepath=item_dict['audio_filepath']
        )

    @staticmethod
    def _create_track_from_dict(track_dict: Dict) -> Track:
        return Track(
            name=track_dict['name'],
            volume=track_dict['volume'],
            pan=track_dict['pan'],
            mute=track_dict['mute'],
            solo=track_dict['solo'],
            type=track_dict['type'],
            input_source=track_dict.get('input_source', ''),
            audio_filepath=track_dict.get('audio_filepath', ''),
            fx_chain=track_dict['fx_chain'],
            automation=track_dict['automation'],
            peak_level=track_dict['peak_level'],
            send_levels=track_dict['send_levels'],
            items=track_dict.get('items', [])
        )
