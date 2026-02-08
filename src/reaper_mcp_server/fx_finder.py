import os
import configparser
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class InstalledPlugin:
    name: str
    plugin_type: str  # VST, VST3, AU, JS, CLAP
    path: str
    manufacturer: Optional[str] = None
    category: Optional[str] = None


class FXFinder:
    """Finds and parses installed Reaper FX/plugins from Reaper's plugin cache files."""

    def __init__(self, reaper_resource_path: Optional[str] = None):
        """
        Initialize FXFinder.

        Args:
            reaper_resource_path: Path to REAPER resource directory.
                                 Defaults to ~/Library/Application Support/REAPER on macOS,
                                 or ~/.config/REAPER on Linux.
        """
        if reaper_resource_path:
            self.reaper_path = Path(reaper_resource_path)
        else:
            # Try common locations
            mac_path = Path.home() / "Library" / "Application Support" / "REAPER"
            linux_path = Path.home() / ".config" / "REAPER"
            windows_path = Path(os.environ.get('APPDATA', '')) / "REAPER"

            if mac_path.exists():
                self.reaper_path = mac_path
            elif linux_path.exists():
                self.reaper_path = linux_path
            elif windows_path.exists():
                self.reaper_path = windows_path
            else:
                self.reaper_path = mac_path  # default to mac, will error later if not found

    def find_installed_plugins(self) -> List[Dict]:
        """
        Find all installed plugins from Reaper's cache files.

        Returns:
            List of dictionaries containing plugin information.
        """
        plugins = []

        # Parse VST plugins
        plugins.extend(self._parse_vst_plugins())

        # Parse VST3 plugins
        plugins.extend(self._parse_vst3_plugins())

        # Parse AU plugins (macOS only)
        plugins.extend(self._parse_au_plugins())

        # Parse JS (JSFX) plugins
        plugins.extend(self._parse_js_plugins())

        # Parse CLAP plugins
        plugins.extend(self._parse_clap_plugins())

        return plugins

    def _parse_vst_plugins(self) -> List[Dict]:
        """Parse VST2/VST3 plugins from reaper-vstplugins*.ini"""
        plugins = []
        vst_files = [
            self.reaper_path / "reaper-vstplugins_arm64.ini",  # Apple Silicon
            self.reaper_path / "reaper-vstplugins64.ini",
            self.reaper_path / "reaper-vstplugins.ini",
        ]

        for vst_file in vst_files:
            if not vst_file.exists():
                continue

            try:
                with open(vst_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith(';') or line.startswith('['):
                            continue

                        # VST entries are in format: filename=hash,id,Display Name (Manufacturer)!!!VSTi
                        if '=' in line:
                            filename, info = line.split('=', 1)
                            filename = filename.strip()
                            info = info.strip()

                            # Determine plugin type from filename extension
                            if filename.endswith('.vst3'):
                                plugin_type = 'VST3'
                            else:
                                plugin_type = 'VST2'

                            # Parse the info part: hash,id,Display Name (Manufacturer)
                            parts = info.split(',', 2)
                            if len(parts) >= 3:
                                display_info = parts[2]

                                # Remove VSTi marker if present
                                display_info = display_info.replace('!!!VSTi', '').strip()

                                # Extract name and manufacturer from "Display Name (Manufacturer)"
                                name, manufacturer = self._parse_vst_display_name(display_info)

                                plugin = InstalledPlugin(
                                    name=name,
                                    plugin_type=plugin_type,
                                    path=filename,
                                    manufacturer=manufacturer
                                )
                                plugins.append(asdict(plugin))
            except Exception as e:
                print(f"Error parsing {vst_file}: {e}")

        return plugins

    @staticmethod
    def _parse_vst_display_name(display_info: str) -> tuple[str, Optional[str]]:
        """Parse VST display name to extract name and manufacturer.

        Format is typically: "Plugin Name (Manufacturer) (additional info)"
        """
        # Look for manufacturer in parentheses
        if '(' in display_info:
            # Split by opening parenthesis
            parts = display_info.split('(')
            name = parts[0].strip()

            # Extract manufacturer from first set of parentheses
            if len(parts) > 1:
                manufacturer = parts[1].split(')')[0].strip()
                return name, manufacturer

        return display_info.strip(), None

    def _parse_vst3_plugins(self) -> List[Dict]:
        """VST3 plugins are now parsed in _parse_vst_plugins()"""
        # This method is kept for compatibility but returns empty list
        # since VST3 is now handled in _parse_vst_plugins
        return []

    def _parse_au_plugins(self) -> List[Dict]:
        """Parse Audio Unit plugins (macOS only) from reaper-auplugins*.ini"""
        plugins = []
        au_files = [
            self.reaper_path / "reaper-auplugins_arm64.ini",  # Apple Silicon
            self.reaper_path / "reaper-auplugins64.ini",
            self.reaper_path / "reaper-auplugins.ini",
        ]

        for au_file in au_files:
            if not au_file.exists():
                continue

            try:
                with open(au_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith(';') or line.startswith('['):
                            continue

                        # AU entries are in format: "Manufacturer: Plugin Name=<inst>"
                        if '=' in line:
                            name_part, info = line.split('=', 1)
                            name_part = name_part.strip()

                            # Skip if it's marked as not installed (<!inst>)
                            if info.strip() == '<!inst>':
                                continue

                            # Parse manufacturer and name from "Manufacturer: Plugin Name"
                            manufacturer, name = self._parse_au_name(name_part)

                            plugin = InstalledPlugin(
                                name=name,
                                plugin_type='AU',
                                path=f"AU:{name_part}",
                                manufacturer=manufacturer
                            )
                            plugins.append(asdict(plugin))
            except Exception as e:
                print(f"Error parsing {au_file}: {e}")

        return plugins

    @staticmethod
    def _parse_au_name(name_part: str) -> tuple[Optional[str], str]:
        """Parse AU name to extract manufacturer and plugin name.

        Format is typically: "Manufacturer: Plugin Name"
        """
        if ':' in name_part:
            parts = name_part.split(':', 1)
            manufacturer = parts[0].strip()
            name = parts[1].strip()
            return manufacturer, name

        return None, name_part

    def _parse_js_plugins(self) -> List[Dict]:
        """Parse JSFX plugins from reaper-jsfx.ini"""
        plugins = []
        js_file = self.reaper_path / "reaper-jsfx.ini"

        if not js_file.exists():
            return plugins

        try:
            with open(js_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(';') or line.startswith('['):
                        continue

                    # JSFX entries are in format: "Category/Plugin Name=path"
                    if '=' in line:
                        name_part, path = line.split('=', 1)
                        name_part = name_part.strip()
                        path = path.strip()

                        # Extract category and name
                        category = None
                        if '/' in name_part:
                            parts = name_part.split('/')
                            category = parts[0]
                            name = '/'.join(parts[1:])
                        else:
                            name = name_part

                        plugin = InstalledPlugin(
                            name=name,
                            plugin_type='JS',
                            path=path,
                            manufacturer='JSFX',
                            category=category
                        )
                        plugins.append(asdict(plugin))
        except Exception as e:
            print(f"Error parsing {js_file}: {e}")

        return plugins

    def _parse_clap_plugins(self) -> List[Dict]:
        """Parse CLAP plugins from reaper-clapplugins64.ini"""
        plugins = []
        clap_files = [
            self.reaper_path / "reaper-clapplugins64.ini",
            self.reaper_path / "reaper-clapplugins.ini",
        ]

        for clap_file in clap_files:
            if not clap_file.exists():
                continue

            try:
                with open(clap_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith(';'):
                            continue

                        if '=' in line:
                            name, path = line.split('=', 1)
                            name = name.strip().strip('"')
                            path = path.strip().strip('"')

                            manufacturer = self._extract_manufacturer(name, path)

                            plugin = InstalledPlugin(
                                name=name,
                                plugin_type='CLAP',
                                path=path,
                                manufacturer=manufacturer
                            )
                            plugins.append(asdict(plugin))
            except Exception as e:
                print(f"Error parsing {clap_file}: {e}")

        return plugins

    @staticmethod
    def _extract_manufacturer(name: str, path: str) -> Optional[str]:
        """Try to extract manufacturer from plugin name or path"""
        # Common patterns in plugin names: "Manufacturer - Plugin Name" or "Manufacturer: Plugin Name"
        for separator in [' - ', ': ', ' : ']:
            if separator in name:
                return name.split(separator)[0].strip()

        # Try to extract from path
        path_parts = Path(path).parts
        for part in path_parts:
            # Look for manufacturer folders
            if part not in ['VST', 'VST3', 'Plugins', 'Audio', 'Components']:
                return part

        return None


    def get_plugins_by_type(self, plugin_type: str) -> List[Dict]:
        """Get plugins filtered by type (VST2, VST3, AU, JS, CLAP)"""
        all_plugins = self.find_installed_plugins()
        return [p for p in all_plugins if p['plugin_type'].upper() == plugin_type.upper()]

    def search_plugins(self, query: str) -> List[Dict]:
        """Search plugins by name, manufacturer, or type"""
        all_plugins = self.find_installed_plugins()
        query_lower = query.lower()

        return [
            p for p in all_plugins
            if query_lower in p['name'].lower()
            or (p.get('manufacturer') and query_lower in p['manufacturer'].lower())
            or query_lower in p['plugin_type'].lower()
        ]
