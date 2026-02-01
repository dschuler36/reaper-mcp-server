import argparse
import json
from dataclasses import asdict
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .utils import remove_empty_strings
from .rpp_finder import RPPFinder
from .rpp_parser import RPPParser
from .audio_analyzer import AudioAnalyzer


def create_server():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reaper-projects-dir',
                       help="Base directory for REAPER projects")
    args = parser.parse_args()

    server = FastMCP("reaper-mcp-server")

    @server.tool()
    def find_reaper_projects():
        rpp_finder = RPPFinder(args.reaper_projects_dir)
        return json.dumps(rpp_finder.find_reaper_projects())

    @server.tool()
    def parse_reaper_project(project_path: str):
        rpp_parser = RPPParser(project_path)
        return json.dumps(remove_empty_strings(asdict(rpp_parser.project)))

    @server.tool()
    def analyze_audio_files(project_path: str, track_filter: Optional[str] = None):
        """Analyze audio files in a Reaper project for mixing feedback.

        Args:
            project_path: Path to .RPP file
            track_filter: Optional substring to filter track names

        Returns:
            JSON with analysis results and warnings for each audio file
        """
        # Parse RPP to get tracks with items
        rpp_parser = RPPParser(project_path)

        # Filter tracks if requested
        tracks = [t for t in rpp_parser.project.tracks
                  if not track_filter or track_filter.lower() in t.name.lower()]

        # Analyze each audio file
        results = {
            'project_name': rpp_parser.project.name,
            'analyzed_files': [],
            'errors': []
        }

        for track in tracks:
            for item in track.items:
                try:
                    analyzer = AudioAnalyzer(item.audio_filepath)
                    analysis = analyzer.analyze()

                    if analysis.error:
                        results['errors'].append({
                            'track_name': track.name,
                            'audio_file': item.audio_filepath,
                            'error': analysis.error
                        })
                    else:
                        results['analyzed_files'].append({
                            'track_name': track.name,
                            'audio_file': item.audio_filepath,
                            'position': item.position,
                            'length': item.length,
                            'analysis': asdict(analysis),
                            'warnings': analysis.warnings
                        })
                except Exception as e:
                    results['errors'].append({
                        'track_name': track.name,
                        'audio_file': item.audio_filepath,
                        'error': str(e)
                    })

        return json.dumps(remove_empty_strings(results))

    return server


if __name__ == '__main__':
    server = create_server()
    server.run(transport='stdio')