# Vision-LLM Web Agent

An autonomous web agent powered by Vision Language Models and Playwright that executes natural language instructions through multi-round interaction. Supports using vision language models through OpenAI-compatible APIs (can be local or remote).

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/DreamWalkerXZ/vision-llm-web-agent.git
cd vision-llm-web-agent

# Initialize and install dependencies
uv sync

# Install Playwright browsers
uv run playwright install chromium
```

### Usage

```bash
# Copy example environment variables
cp example.env .env

# Edit the .env file with your own API keys and model names.

# Run the agent
uv run python main.py
```

## 📦 Project Structure

```text
.
├── docs
├── tests
│   ├── conftest.py
│   ├── test_browser_control.py
│   ├── test_file_operations.py
│   ├── test_information.py
│   └── test_waiting.py
├── vision_llm_web_agent
│   ├── config
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── tools
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── browser_control.py
│   │   ├── file_operations.py
│   │   ├── information.py
│   │   ├── registry.py
│   │   └── waiting.py
│   ├── __init__.py
│   ├── agent_controller.py
│   └── vllm_client.py
├── example.env
├── main.py
├── pyproject.toml
└── README.md
```

## 🛠️ Tools Provided

| Program File Name    | Tool Name            | Description                  | Implemented | Tested |
| -------------------- | -------------------- | ---------------------------- | ----------- | ------ |
| `browser_control.py` | `goto`               | Navigate to URL              | ✅           | ✅      |
| `browser_control.py` | `click`              | Click element                | ✅           | ✅      |
| `browser_control.py` | `type_text`          | Type into input              | ✅           | ✅      |
| `browser_control.py` | `press_key`          | Press keyboard keys          | ✅           | ✅      |
| `waiting.py`         | `wait_seconds`       | Wait for duration            | ✅           | ✅      |
| `information.py`     | `screenshot`         | Capture page screenshot      | ✅           | ✅      |
| `information.py`     | `dom_summary`        | Get simplified DOM structure | ✅           | ✅      |
| `information.py`     | `ocr`                | Extract text from images     | ❌           | ❌      |
| `file_operations.py` | `download_pdf`       | Download PDF files           | ✅           | ✅      |
| `file_operations.py` | `pdf_extract_text`   | Extract text from PDFs       | ❓           | ❓      |
| `file_operations.py` | `pdf_extract_images` | Extract images from PDFs     | ❓           | ❓      |
| `file_operations.py` | `save_image`         | Save/crop images             | ❓           | ❓      |
| `file_operations.py` | `write_text`         | Write text to files          | ❓           | ❓      |

- ✅ Implemented
- ❌ Not implemented
- ❓ Problematic

## 📋 Example Task

```text
Find the most recent technical report (PDF) about Qwen, 
then interpret Figure 1 by describing its purpose and key findings.
```

## 📊 Output Artifacts

After execution, check the `artifacts/` directory for:

- Step-by-step screenshots (`step_0.png`, `step_1.png`, ...)
- Execution log (`execution_log.json`)
- Downloaded PDFs
- Extracted images

## 🔧 Roadmap

- [ ] Implement and test pdf related tools.
- [ ] Implement and test the ocr tool.
- [ ] Multiple rounds of interaction.
- [ ] Save the final answer to a txt file.
- [ ] Implement locale alignment and check whether it is useful.
- [ ] Make the agent more robust and reliable (maybe tuning the dom_summary tool and prompt).
- [ ] Add more tests.
- [ ] Add supported vision LLMs list.
- [ ] Add hardware requirements.
- [ ] Add license.
- [ ] Add documentation.
