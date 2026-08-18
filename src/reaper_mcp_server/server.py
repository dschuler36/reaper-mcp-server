import argparse
import json
from dataclasses import asdict
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .utils import remove_empty_strings, sanitize_floats, truncate_encoded_params
from .rpp_finder import RPPFinder
from .rpp_parser import RPPParser
from .audio_analyzer import AudioAnalyzer
from .fx_finder import FXFinder


def _serialize(payload) -> str:
    """Shared output pipeline: truncate blobs, drop empties, make JSON-safe."""
    return json.dumps(sanitize_floats(remove_empty_strings(truncate_encoded_params(payload))))


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
        return _serialize(asdict(rpp_parser.project))

    @server.tool()
    def analyze_audio_files(
        project_path: str,
        track_filter: Optional[str] = None,
        whole_file: bool = False,
    ):
        """Analyze audio in a Reaper project for mixing feedback.

        Measurements are taken from the source files on disk, so they are
        pre-FX and pre-fader: a track running an amp sim or EQ will sound
        nothing like its analysis.

        Args:
            project_path: Path to .RPP file
            track_filter: Optional substring to filter track names
            whole_file: Analyze entire source files instead of only the region
                each item actually plays. Off by default.

        Returns:
            JSON with per-item analysis, warnings, and skipped items
        """
        rpp_parser = RPPParser(project_path)

        tracks = [t for t in rpp_parser.project.tracks
                  if not track_filter or track_filter.lower() in t.name.lower()]

        results = {
            'project_name': rpp_parser.project.name,
            'signal_stage': 'pre-fx (raw source files, before FX chain and fader)',
            'analyzed_files': [],
            'skipped': [],
            'errors': []
        }

        # Identical regions of the same file measure identically, so analyse
        # each distinct region once. Repeated items previously re-read and
        # re-analysed the same file dozens of times per call.
        cache = {}

        for track in tracks:
            for item in track.items:
                if not item.audio_filepath:
                    results['skipped'].append({
                        'track_name': track.name,
                        'track_number': track.track_number,
                        'item_name': item.name,
                        'position': item.position,
                        'reason': (
                            'MIDI item - no audio source'
                            if item.source_type == 'MIDI'
                            else 'Item has no audio source'
                        )
                    })
                    continue

                if whole_file:
                    start, length = 0.0, None
                else:
                    # An item plays LENGTH seconds of timeline, which consumes
                    # LENGTH * playrate seconds of source from SOFFS.
                    start = item.start_offset
                    length = item.length * (item.playrate or 1.0)

                key = (item.audio_filepath, round(start, 6), round(length or -1.0, 6))
                if key not in cache:
                    cache[key] = AudioAnalyzer(item.audio_filepath, start, length).analyze()
                analysis = cache[key]

                entry = {
                    'track_name': track.name,
                    'track_number': track.track_number,
                    'item_name': item.name,
                    'audio_file': item.audio_filepath,
                    'position': item.position,
                    'length': item.length,
                    'item_muted': item.mute,
                    'track_muted': track.mute,
                }

                if analysis.error:
                    entry['error'] = analysis.error
                    results['errors'].append(entry)
                else:
                    entry['analysis'] = asdict(analysis)
                    entry['warnings'] = analysis.warnings
                    results['analyzed_files'].append(entry)

        results['distinct_regions_analyzed'] = len(cache)
        return _serialize(results)

    @server.tool()
    def list_installed_fx(plugin_type: Optional[str] = None, search_query: Optional[str] = None):
        """List all installed FX/plugins available in Reaper.

        Args:
            plugin_type: Optional filter by plugin type (VST2, VST3, AU, JS, CLAP)
            search_query: Optional search query to filter by name, manufacturer, or type

        Returns:
            JSON with list of installed plugins including name, type, path, and manufacturer
        """
        fx_finder = FXFinder()

        if search_query:
            plugins = fx_finder.search_plugins(search_query)
        elif plugin_type:
            plugins = fx_finder.get_plugins_by_type(plugin_type)
        else:
            plugins = fx_finder.find_installed_plugins()

        return json.dumps({
            'total_count': len(plugins),
            'plugins': plugins
        })

    return server


def main():
    """Console-script entry point declared in pyproject.toml."""
    create_server().run(transport='stdio')


if __name__ == '__main__':
    main()