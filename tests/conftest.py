"""
Pytest configuration and fixtures
"""

import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def test_artifacts_dir():
    """Create a temporary artifacts directory for tests"""
    artifacts = Path("artifacts/test")
    artifacts.mkdir(parents=True, exist_ok=True)
    yield artifacts
    # Cleanup after all tests
    # shutil.rmtree(artifacts, ignore_errors=True)


@pytest.fixture(scope="function")
def cleanup_browser():
    """Cleanup browser state after each test"""
    yield
    # Import here to avoid circular dependency
    from vision_llm_web_agent.tools.browser_control import browser_state
    browser_state.cleanup()


@pytest.fixture(scope="session")
def sample_html_file(tmp_path_factory):
    """Create a sample HTML file for testing"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Page</title>
    </head>
    <body>
        <h1>Test Page</h1>
        <input id="test-input" type="text" placeholder="Enter text">
        <button id="test-button">Click Me</button>
        <a href="https://example.com" id="test-link">Example Link</a>
        <div id="result"></div>
        <script>
            document.getElementById('test-button').addEventListener('click', function() {
                const input = document.getElementById('test-input');
                const result = document.getElementById('result');
                result.textContent = 'Clicked: ' + input.value;
            });
        </script>
    </body>
    </html>
    """
    
    tmp_dir = tmp_path_factory.mktemp("html")
    html_file = tmp_dir / "test_page.html"
    html_file.write_text(html_content)
    return html_file

