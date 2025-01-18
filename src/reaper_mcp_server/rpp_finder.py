import os
from typing import List

class RPPFinder:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir


    def find_reaper_projects(self) -> List[dict]:

        projects = []
        for root, _, files in os.walk(self.base_dir):
            for file in files:
                if file.endswith('.RPP'):
                    rel_path = os.path.relpath(root, self.base_dir)
                    projects.append({
                        'path': os.path.join(root, file),
                        'project_name': os.path.splitext(file)[0],
                        'directory': rel_path
                    })
        return projects
