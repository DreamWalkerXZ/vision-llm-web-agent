"""
Tools package for Vision LLM Web Agent
Auto-discovering tool system with decorators
"""

from .registry import get_tool_registry, initialize_tool_registry
from .base import tool_registry, ToolMetadata
from .browser_control import BrowserState

# Initialize tool registry
initialize_tool_registry()

# Get all registered tools
_registry = get_tool_registry()
_all_tools = _registry.get_all_tools()

# Export all tool functions for backward compatibility
for tool_name, tool_func in _all_tools.items():
    globals()[tool_name] = tool_func

# Export registry and metadata for advanced usage
__all__ = [
    "get_tool_registry",
    "tool_registry", 
    "ToolMetadata",
    "BrowserState",
    *_all_tools.keys()
]
