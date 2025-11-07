"""
Tests for waiting.py tools
"""

import pytest
import time
from vision_llm_web_agent.tools.waiting import wait_for_seconds
from vision_llm_web_agent.tools.browser_control import goto_url, browser_state


class TestWaitForSeconds:
    """Test the wait_for_seconds function"""
    
    def test_wait_basic(self):
        """Test basic wait functionality"""
        start = time.time()
        result = wait_for_seconds(0.5)
        elapsed = time.time() - start
        
        assert "✅" in result
        assert "0.5" in result
        assert elapsed >= 0.5
        assert elapsed < 0.7  # Allow some margin
    
    def test_wait_integer(self):
        """Test wait with integer seconds"""
        start = time.time()
        result = wait_for_seconds(1)
        elapsed = time.time() - start
        
        assert "✅" in result
        assert elapsed >= 1.0
        assert elapsed < 1.2
    
    def test_wait_zero(self):
        """Test wait with zero seconds"""
        result = wait_for_seconds(0)
        assert "✅" in result
    
    def test_wait_small_duration(self):
        """Test wait with very small duration"""
        start = time.time()
        result = wait_for_seconds(0.1)
        elapsed = time.time() - start
        
        assert "✅" in result
        assert elapsed >= 0.1

