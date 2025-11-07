"""
Tool Registry and Auto-Discovery
Automatically discovers and registers all tools in the tools package
"""

from .base import tool_registry
from . import browser_control, waiting, information, file_operations


def initialize_tool_registry():
    """Initialize the tool registry with all available tools"""
    # Register tools from each module
    tool_registry.discover_tools_in_module(browser_control)
    tool_registry.discover_tools_in_module(waiting)
    tool_registry.discover_tools_in_module(information)
    tool_registry.discover_tools_in_module(file_operations)
    
    print(f"🔧 Registered {len(tool_registry.get_all_tools())} tools:")
    for category, tools in tool_registry._categories.items():
        print(f"   {category}: {', '.join(tools)}")


def get_tool_registry():
    """Get the initialized tool registry"""
    if not tool_registry._tools:
        initialize_tool_registry()
    return tool_registry