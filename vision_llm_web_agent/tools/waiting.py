"""
Waiting and Synchronization Tools
Tools for waiting and timing operations
"""

import time
from .base import tool
from .browser_control import browser_state


@tool(
    name="wait_seconds",
    description="Wait for specified seconds",
    parameters={"seconds": "float (required)"},
    category="waiting"
)
def wait_for_seconds(seconds: float) -> str:
    """Wait for a specified number of seconds"""
    time.sleep(seconds)
    return f"✅ Waited for {seconds} seconds"