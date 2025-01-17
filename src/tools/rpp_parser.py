from typing import List, Dict, Optional
from domains.reaper_dataclasses import Project, Track, FX

class RPPParser:
    MAX_ENCODED_DATA_LENGTH = 1024
    
    def __init__(self, file_path):
        self.file_path = file_path
        self.project = Project(
            name="",
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
        encoded_data = []
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
                
            if line.startswith('TEMPO'):
                parts = line.split()
                if len(parts) >= 3:
                    self.project.tempo = float(parts[1])
                    self.project.time_signature = f"{parts[2]}/{parts[3]}"

            if line.startswith('<TRACK'):
                current_track = {
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
                    'send_levels': []
                }
                track_stack.append(current_track)
                
            elif line.startswith('NAME') and current_track:
                if '"' in line:
                    current_track['name'] = line.split('"')[1]
                else:
                    current_track['name'] = line.split(' ', 1)[1]
            
            elif line.startswith('<FXCHAIN'):
                in_fx_chain = True
                current_fx_chain = []
                
            elif line.startswith('<VST') and in_fx_chain:
                if current_fx:
                    current_fx_chain.append(FX(
                        name=current_fx['name'],
                        encoded_param=''.join(current_fx['encoded_data']),
                        bypassed=current_fx['bypassed']
                    ))
                
                parts = line.split('"')
                fx_name = parts[1] if len(parts) > 1 else "Unknown"
                current_fx = {
                    'name': fx_name,
                    'encoded_data': [],
                    'bypassed': False  # Will be updated if BYPASS found
                }
                
            elif line.startswith('BYPASS') and current_fx:
                parts = line.split()
                current_fx['bypassed'] = bool(int(parts[1]))
                
            elif in_fx_chain and current_fx and line.strip().isalnum():
                current_fx['encoded_data'].append(line)
                
            elif line == '>' and in_fx_chain:
                if current_fx:
                    encoded_data = ''.join(current_fx['encoded_data'])
                    
                    # Some FX encoded data is huge (ex: amp sim or synth)
                    # I'm truncating this otherwise the data won't fit in the LLM's context window
                    if len(encoded_data) > self.MAX_ENCODED_DATA_LENGTH:
                        encoded_data = f"<DATA_TRUNCATED: Original size {len(encoded_data)} bytes>"
                    
                    current_fx_chain.append(FX(
                        name=current_fx['name'],
                        encoded_param=encoded_data,
                        bypassed=current_fx['bypassed']
                    ))
                    current_fx = None
                
                if not current_fx:
                    in_fx_chain = False
                    if current_track:
                        current_track['fx_chain'] = current_fx_chain
                    current_fx_chain = []
            
            elif line.startswith('VOLPAN') and current_track:
                parts = line.split()
                if len(parts) >= 3:
                    current_track['volume'] = float(parts[1])
                    current_track['pan'] = float(parts[2])
            
            elif line.startswith('MUTESOLO') and current_track:
                parts = line.split()
                if len(parts) >= 3:
                    current_track['mute'] = bool(int(parts[1]))
                    current_track['solo'] = bool(int(parts[2]))
            
            elif line == '>' and track_stack:
                finished_track = track_stack.pop()
                if finished_track:
                    track = Track(
                        name=finished_track['name'],
                        volume=finished_track['volume'],
                        pan=finished_track['pan'],
                        mute=finished_track['mute'],
                        solo=finished_track['solo'],
                        type=finished_track['type'],
                        input_source=finished_track['input_source'],
                        audio_filepath=finished_track['audio_filepath'],
                        fx_chain=finished_track['fx_chain'],
                        automation=finished_track['automation'],
                        peak_level=finished_track['peak_level'],
                        send_levels=finished_track['send_levels']
                    )
                    self.project.tracks.append(track)
                
                current_track = track_stack[-1] if track_stack else None
