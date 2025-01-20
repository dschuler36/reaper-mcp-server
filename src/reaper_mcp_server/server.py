import argparse
import json
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

from .utils import remove_empty_strings
from .rpp_finder import RPPFinder
from .rpp_parser import RPPParser


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

    return server


if __name__ == '__main__':
    server = create_server()
    server.run(transport='stdio')