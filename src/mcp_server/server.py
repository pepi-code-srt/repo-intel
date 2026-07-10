from mcp.server.fastmcp import FastMCP
from .tools.github_tools import clone_repo, get_repo_structure, get_repo_metadata
from .tools.file_tools import read_file
from .tools.dep_tools import parse_requirements, parse_package_json

mcp = FastMCP("RepoIntel MCP Server")

# Register GitHub tools
mcp.tool()(clone_repo)
mcp.tool()(get_repo_structure)
mcp.tool()(get_repo_metadata)

# Register File tools
mcp.tool()(read_file)

# Register Dependency tools
mcp.tool()(parse_requirements)
mcp.tool()(parse_package_json)

if __name__ == "__main__":
    mcp.run()
