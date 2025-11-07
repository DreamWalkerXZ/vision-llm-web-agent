"""
Base tool system with decorators and auto-discovery
"""

import inspect
from typing import Dict, Any, Callable, List, Optional
from functools import wraps


class ToolMetadata:
    """Metadata for a tool function"""
    
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, str],
        category: str = "general"
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.category = category


def tool(
    name: str,
    description: str,
    parameters: Dict[str, str],
    category: str = "general"
):
    """
    Decorator to mark a function as a tool with metadata
    
    Args:
        name: Tool name (used by VLLM)
        description: Tool description for VLLM
        parameters: Parameter definitions in format {"param": "type description"}
        category: Tool category for organization
    """
    def decorator(func: Callable) -> Callable:
        # Store metadata on the function
        func._tool_metadata = ToolMetadata(
            name=name,
            description=description,
            parameters=parameters,
            category=category
        )
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        # Copy metadata to wrapper
        wrapper._tool_metadata = func._tool_metadata
        return wrapper
    
    return decorator


class ToolRegistry:
    """Registry for managing tools with auto-discovery"""
    
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._metadata: Dict[str, ToolMetadata] = {}
        self._categories: Dict[str, List[str]] = {}
    
    def register_tool(self, func: Callable) -> None:
        """Register a tool function"""
        if not hasattr(func, '_tool_metadata'):
            raise ValueError(f"Function {func.__name__} is not decorated with @tool")
        
        metadata = func._tool_metadata
        self._tools[metadata.name] = func
        self._metadata[metadata.name] = metadata
        
        # Add to category
        if metadata.category not in self._categories:
            self._categories[metadata.category] = []
        if metadata.name not in self._categories[metadata.category]:
            self._categories[metadata.category].append(metadata.name)
    
    def get_tool(self, name: str) -> Optional[Callable]:
        """Get a tool function by name"""
        return self._tools.get(name)
    
    def get_tool_metadata(self, name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name"""
        return self._metadata.get(name)
    
    def get_all_tools(self) -> Dict[str, Callable]:
        """Get all registered tools"""
        return self._tools.copy()
    
    def get_all_metadata(self) -> Dict[str, ToolMetadata]:
        """Get all tool metadata"""
        return self._metadata.copy()
    
    def get_tools_by_category(self, category: str) -> Dict[str, Callable]:
        """Get tools by category"""
        tools = {}
        for tool_name in self._categories.get(category, []):
            tools[tool_name] = self._tools[tool_name]
        return tools
    
    def get_tool_definitions_for_vllm(self) -> List[Dict[str, Any]]:
        """Get tool definitions in VLLM format"""
        definitions = []
        for metadata in self._metadata.values():
            definition = {
                "name": metadata.name,
                "description": metadata.description,
                "parameters": metadata.parameters
            }
            definitions.append(definition)
        return definitions
    
    def discover_tools_in_module(self, module) -> None:
        """Auto-discover and register tools in a module"""
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and hasattr(obj, '_tool_metadata'):
                self.register_tool(obj)
    
    def discover_tools_in_package(self, package) -> None:
        """Auto-discover tools in all modules of a package"""
        import pkgutil
        import importlib
        
        for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
            try:
                module = importlib.import_module(f"{package.__name__}.{modname}")
                self.discover_tools_in_module(module)
            except Exception as e:
                print(f"Warning: Could not import {modname}: {e}")


# Global tool registry instance
tool_registry = ToolRegistry()
