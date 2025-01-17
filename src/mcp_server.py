import json
import argparse
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

from tools.rpp_finder import RPPFinder
from tools.rpp_parser import RPPParser

parser = argparse.ArgumentParser()
parser.add_argument('--reaper-projects-dir',
                   help="Base directory for REAPER projects")
args = parser.parse_args()

mcp = FastMCP("reaper-mcp-server")
REAPER_PROJECT_DIR = args.reaper_projects_dir

@mcp.tool()
def find_reaper_projects():
    rpp_finder = RPPFinder(args.reaper_projects_dir)
    return json.dumps(rpp_finder.find_reaper_projects())


@mcp.tool()
def parse_reaper_project(project_path: str):
    rpp_parser = RPPParser(project_path)
    return json.dumps(asdict(rpp_parser.project))


if __name__ == "__main__":
    mcp.run(transport='stdio')
