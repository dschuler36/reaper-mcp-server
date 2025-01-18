# Reaper MCP Server

This is a simple MCP server that connects a Reaper project to an MCP client like Claude Desktop and enables you to ask questions about the project.

## Tools

- `find_reaper_projects`: Finds all Reaper projects in the directory you specified in the config.
- `parse_reaper_project`: Parses a Reaper project and returns a JSON object.

These tools work in tandem. When you ask Claude a question about a specific Reaper project, it will use the `find_reaper_projects` tool to find the project, then use the `parse_reaper_project` tool to parse the project and answer your question. To see all data that is parsed from the project, check out the `src/domains/reaper_dataclasses.py` file.

## Setup

1. **Install Dependencies**
   ```bash
   uv venv
   source .venv/bin/activate

   uv pip install .
   ```

2. **Configure Claude Desktop**
   - Follow [the instructions to configure Claude Desktop](https://modelcontextprotocol.io/quickstart/server#core-mcp-concepts) for use with a custom MCP server
   - Find the sample config in `setup/claude_desktop_config.json`
   - Update the following paths in the config:
     - Your `uv` installation path
     - Your Reaper project directory
     - This server's directory

3. **Launch and Configure**
   - Open Claude Desktop
   - Look for the hammer icon in the bottom right of your chat box
   - Click the hammer icon to verify you see two Reaper tools available:
     - `find_reaper_projects`
     - `parse_reaper_project`
   
   ![Claude Desktop Tools](./docs/claude-desktop-tools.png)

4. **Ask Away!**
   - Ask questions about your Reaper project
   - Always include the name of the specific Reaper project you're asking about
   - You can expand the tool boxes to see the raw project data being passed to Claude
   ![Claude Desktop Tools](./docs/example-question.png)
