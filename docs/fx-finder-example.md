# FX Finder Usage Examples

The `list_installed_fx` tool allows you to query your installed Reaper plugins directly from Claude Desktop.

## Example Conversations

### Finding Synth Plugins

**You:** "I'm looking for a warbly synth. What options do I have from my already installed plugins?"

**Claude:** *Uses the `list_installed_fx` tool with `search_query="synth"`*

"You have 2 synth plugins installed:
- **AUMIDISynth** (Apple) - AU Plugin
- **ReaSynth** (Cockos) - VST2

For a warbly sound, ReaSynth is a good basic option that comes with Reaper. You could use its built-in LFO to modulate the oscillators for warble effects. If you're looking for more advanced options, you might want to consider installing a dedicated synth like Serum or Vital."

### Filtering by Manufacturer

**You:** "What iZotope plugins do I have?"

**Claude:** *Uses the `list_installed_fx` tool with `search_query="iZotope"`*

"You have 9 iZotope plugins installed:
- iZotope Trash 2 (VST2 & VST3)
- Nectar 3 Elements (VST2 & VST3)
- Neutron 3 Elements (VST2 & VST3)
- Ozone 9 Elements (VST2 & VST3)"

### Filtering by Plugin Type

**You:** "List all my Audio Unit plugins"

**Claude:** *Uses the `list_installed_fx` tool with `plugin_type="AU"`*

"You have 8 Audio Unit plugins installed:
- AUMIDISynth (Apple)
- AUSampler (Apple)
- DLSMusicDevice (Apple)
- Plus 5 more Apple AU plugins..."

### Exploring Available Options

**You:** "I want to add some saturation to my vocal track. What do I have?"

**Claude:** *Uses the `list_installed_fx` tool with `search_query="trash"` and/or `search_query="distortion"`*

"For saturation on vocals, here are your options:
1. **iZotope Trash 2** - Excellent for creative distortion and saturation
2. **Apple: AUDistortion** - Basic distortion/saturation AU plugin

iZotope Trash 2 would be my recommendation as it offers more control and character options specifically designed for creative audio processing. You can use its multiband saturation for warmth without making the vocals harsh."

## Technical Details

### How It Works

The FX Finder tool reads Reaper's plugin cache files located at:
- **macOS**: `~/Library/Application Support/REAPER/`
- **Linux**: `~/.config/REAPER/`
- **Windows**: `%APPDATA%/REAPER/`

It parses the following files:
- `reaper-vstplugins*.ini` - VST2 and VST3 plugins
- `reaper-auplugins*.ini` - Audio Unit plugins (macOS only)
- `reaper-jsfx.ini` - JSFX/JS plugins
- `reaper-clapplugins*.ini` - CLAP plugins

### Supported Plugin Types

- **VST2**: Legacy VST plugins
- **VST3**: Modern VST3 format
- **AU**: Audio Units (macOS only)
- **JS**: JSFX/ReaScript plugins
- **CLAP**: CLAP format plugins

### Limitations

- Only shows plugins that have been scanned by Reaper
- If you install new plugins, open Reaper and let it scan them before they'll appear in results
- Plugin metadata (manufacturer, category) is extracted from Reaper's cache files, which may vary in completeness
