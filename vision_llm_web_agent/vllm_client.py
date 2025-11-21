"""
Vision Language Model Client
Interfaces with vision LLMs via OpenAI-compatible API
"""

import base64
import json
import os
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, List, Any

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from .config.settings import ARTIFACTS_DIR

# Load environment variables
load_dotenv()


class VLLMClient:
    """Client for Vision Language Models via OpenAI-compatible API"""
    
    def __init__(
        self, 
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ):
        """
        Initialize VLLM client.
        
        Args:
            base_url: API base URL. Defaults to env OPENAI_BASE_URL or OpenAI's API
            api_key: API key. Defaults to env OPENAI_API_KEY
            model: Model name. Defaults to env OPENAI_MODEL or "gpt-4o"
            max_tokens: Maximum tokens in response
            temperature: Temperature for generation (0-2)
        
        Supports:
            - Local vLLM server (base_url="http://localhost:8000/v1")
            - OpenAI API (base_url="https://api.openai.com/v1", model="gpt-4o")
            - Other OpenAI-compatible APIs (Claude, Gemini via proxy, etc.)
        """
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "EMPTY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        
        print(f"✅ VLLM Client initialized")
        print(f"   Base URL: {self.base_url}")
        print(f"   Model: {self.model}")
    
    def encode_image(self, image_path: str, max_size: tuple = (1280, 720)) -> str:
        """
        Encode image to base64 data URL.
        
        Args:
            image_path: Path to the image file
            max_size: Maximum size (width, height) to resize image to
        
        Returns:
            Base64 encoded data URL
        """
        try:
            with Image.open(image_path) as img:
                # Resize if too large (to save tokens)
                if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Convert to RGB if needed
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                
                # Encode to base64
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                return f"data:image/png;base64,{img_str}"
        except Exception as e:
            raise ValueError(f"Failed to encode image {image_path}: {e}")
    
    def clean_messages_for_logging(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Clean messages by removing image URLs for logging purposes.
        
        Args:
            messages: List of message dictionaries
        
        Returns:
            Cleaned messages with image URLs removed
        """
        cleaned_messages = []
        
        for message in messages:
            cleaned_message = message.copy()
            
            # Handle content that might contain image URLs
            if isinstance(cleaned_message.get('content'), list):
                # Multi-modal content (text + image)
                cleaned_content = []
                for item in cleaned_message['content']:
                    if item.get('type') == 'image_url':
                        # Replace image URL with placeholder
                        cleaned_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": "[IMAGE_DATA_REMOVED_FOR_LOGGING]",
                                "detail": item.get('image_url', {}).get('detail', 'high')
                            }
                        })
                    else:
                        # Keep text content as is
                        cleaned_content.append(item)
                cleaned_message['content'] = cleaned_content
            elif isinstance(cleaned_message.get('content'), str):
                # Text content - check if it contains base64 image data
                content = cleaned_message['content']
                if 'data:image/' in content and 'base64,' in content:
                    # Replace base64 image data with placeholder
                    import re
                    cleaned_content = re.sub(
                        r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+',
                        '[IMAGE_DATA_REMOVED_FOR_LOGGING]',
                        content
                    )
                    cleaned_message['content'] = cleaned_content
            
            cleaned_messages.append(cleaned_message)
        
        return cleaned_messages

    def build_system_prompt(self, available_tools: List[Dict[str, Any]]) -> str:
        """
        Build system prompt with tool descriptions.
        
        Args:
            available_tools: List of tool definitions
        
        Returns:
            System prompt string
        """
        prompt = """You are an autonomous web agent. Your job is to complete tasks by controlling a web browser and using available tools.

**Available Tools:**
"""
        
        for tool in available_tools:
            prompt += f"\n{tool['name']}: {tool['description']}\n"
            if tool.get('parameters'):
                prompt += f"Parameters: {json.dumps(tool['parameters'], indent=2)}\n"
        
        prompt += """
**Input Format:**
You will receive:
- Screenshot (if available)
- Current state in JSON format with: round, screenshot_available, dom_summary, instruction
- Tool execution results in JSON format: {"tool_execution": "tool_name", "result": "result_text"}

**Response Format (MUST be valid JSON):**

To use a tool:
```json
{
    "thought": "What I'm doing and why",
    "tool": "tool_name",
    "parameters": {"param": "value"}
}
```

When task is complete:
```json
{
    "thought": "Summary of what was accomplished",
    "status": "complete",
    "result": "Final answer for the user"
}
```

**Rules:**
1. Respond ONLY with valid JSON (start with {, end with })
2. Call ONE tool at a time
3. **CRITICAL: Trust DOM over screenshot** - If an element is not in dom_summary, it's NOT clickable, even if you see it in the screenshot
4. Use specific CSS selectors for click/type actions
5. If there is a CAPTCHA, try another site, DO NOT try to solve the CAPTCHA.
6. **Error Recovery:** If actions fail 2+ times, try different approaches - never repeat the exact same action more than 2 times
7. Call download_pdf for pdf download.
8. **File Paths:** For all file operations (download_pdf, pdf_extract_text, pdf_extract_images, save_image, write_text), provide ONLY the filename (e.g., "abc.pdf", "output.txt"), NOT directory paths. The system will automatically save files to artifacts/ directory in a single level (artifacts/filename).
9. Incase of opening a pdf link, always download the pdf using download_pdf tool and then consider using extract text/images using pdf_extract_text/pdf_extract_images tools on the pdf that you download to local.
10. When you are required to generate  summaries or answers based on large text content, always use the pdf_extract_text tool to extract text from the pdf and then generate your summaries/answers based on the extracted text and generate a file.
**Preferences:**
1. Prefer arXiv for academic and technical reports.
"""
        
        return prompt
    
    def plan_next_action(
        self, 
        history: List[Dict[str, Any]], 
        state_info: Dict[str, Any],
        available_tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze current state and plan next action.
        
        Args:
            history: Conversation history
            state_info: Current state (screenshot path, DOM, etc.)
            available_tools: List of available tool definitions
        
        Returns:
            Parsed response with action to take
        """
        # Build prompt with tool descriptions
        system_prompt = self.build_system_prompt(available_tools)
        
        # Prepare messages
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add history
        # History now contains alternating assistant (tool call) and user (tool result) messages
        for msg in history:
            if msg['role'] in ['user', 'assistant']:
                messages.append(msg)
        
        # Add current state with vision input (if screenshot available)
        current_state_content = []
        
        # Check if screenshot is available
        screenshot_available = state_info.get('screenshot_available', False)
        screenshot_path = state_info.get('screenshot')
        
        if screenshot_available and screenshot_path:
            try:
                # Add screenshot
                current_state_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": self.encode_image(screenshot_path),
                        "detail": "high"
                    }
                })
            except Exception as e:
                print(f"   ⚠️  Failed to encode screenshot: {e}")
                # Continue without screenshot
        
        # Add text description in JSON format
        dom_text = state_info.get('dom', 'N/A')
        round_num = state_info.get('round', 0)
        
        current_state_json = {
            "round": round_num,
            "screenshot_available": screenshot_available,
            "dom_summary": dom_text,
            "instruction": "Analyze the current state and decide the next action. Respond with valid JSON."
        }
        
        current_state_content.append({
            "type": "text",
            "text": f"Current State:\n```json\n{json.dumps(current_state_json, ensure_ascii=False, indent=2)}\n```"
        })
        
        messages.append({
            "role": "user",
            "content": current_state_content
        })
        
        # Debug: Print messages being sent to VLLM
        print(f"\n📤 Sending to VLLM:")
        print(f"   Model: {self.model}")
        print(f"   Messages count: {len(messages)}")
        for i, msg in enumerate(messages):
            if msg['role'] == 'system':
                print(f"   [{i}] System: {msg['content'][:200]}...")
            elif msg['role'] == 'user':
                if isinstance(msg['content'], list):
                    print(f"   [{i}] User: {len(msg['content'])} content items (image + text)")
                else:
                    print(f"   [{i}] User: {msg['content'][:200]}...")
            else:
                print(f"   [{i}] {msg['role']}: {str(msg['content'])[:200]}...")
        
        # Call the model
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            # Parse response
            content = response.choices[0].message.content
            
            # Debug: Print raw VLLM output
            print(f"\n🔍 VLLM Raw Output:")
            print("=" * 80)
            print(content)
            print("=" * 80)
            
            # Parse and debug the result
            parsed_result = self.parse_response(content)
            
            # Add raw input and output to parsed result
            parsed_result["vllm_raw_input"] = {
                "model": self.model,
                "messages": self.clean_messages_for_logging(messages),
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }
            parsed_result["vllm_raw_output"] = {
                "content": content,
                "response_object": {
                    "id": response.id,
                    "object": response.object,
                    "created": response.created,
                    "model": response.model,
                    "choices": [
                        {
                            "index": choice.index,
                            "message": {
                                "role": choice.message.role,
                                "content": choice.message.content
                            },
                            "finish_reason": choice.finish_reason
                        } for choice in response.choices
                    ],
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    } if response.usage else None
                }
            }
            
            # Debug: Print parsed result
            print(f"\n📋 Parsed Result:")
            print(f"   Is Complete: {parsed_result.get('is_complete', 'N/A')}")
            print(f"   Final Answer: {parsed_result.get('final_answer', 'N/A')}")
            print(f"   Tool Calls: {len(parsed_result.get('tool_calls', []))}")
            if parsed_result.get('tool_calls'):
                for i, tool_call in enumerate(parsed_result['tool_calls']):
                    print(f"     [{i}] {tool_call.get('name', 'unknown')}: {tool_call.get('params', {})}")
            if parsed_result.get('error'):
                print(f"   Error: {parsed_result['error']}")
                print(f"\n🔄 JSON Parse Error - Retrying with error feedback...")
                
                # Add assistant's invalid response to messages
                assistant_invalid_response = {
                    "role": "assistant",
                    "content": content
                }
                
                # Add error feedback as user message
                error_feedback = {
                    "role": "user",
                    "content": f"ERROR: Your response was not valid JSON. Please respond with valid JSON format only. Use the exact format specified in the system prompt.\n\nYour previous response:\n{content[:500]}..."
                }
                
                # Retry with error feedback
                print(f"\n🔄 Retrying with error feedback...")
                retry_messages = messages + [assistant_invalid_response, error_feedback]
                retry_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=retry_messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature
                )
                
                retry_content = retry_response.choices[0].message.content
                print(f"\n🔍 VLLM Retry Output:")
                print("=" * 80)
                print(retry_content)
                print("=" * 80)
                
                # Parse retry result
                parsed_result = self.parse_response(retry_content)
                
                # Add raw input and output for retry
                parsed_result["vllm_raw_input"] = {
                    "model": self.model,
                    "messages": self.clean_messages_for_logging(retry_messages),
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature
                }
                parsed_result["vllm_raw_output"] = {
                    "content": retry_content,
                    "response_object": {
                        "id": retry_response.id,
                        "object": retry_response.object,
                        "created": retry_response.created,
                        "model": retry_response.model,
                        "choices": [
                            {
                                "index": choice.index,
                                "message": {
                                    "role": choice.message.role,
                                    "content": choice.message.content
                                },
                                "finish_reason": choice.finish_reason
                            } for choice in retry_response.choices
                        ],
                        "usage": {
                            "prompt_tokens": retry_response.usage.prompt_tokens,
                            "completion_tokens": retry_response.usage.completion_tokens,
                            "total_tokens": retry_response.usage.total_tokens
                        } if retry_response.usage else None
                    }
                }
                print(f"\n📋 Retry Parsed Result:")
                print(f"   Is Complete: {parsed_result.get('is_complete', 'N/A')}")
                print(f"   Final Answer: {parsed_result.get('final_answer', 'N/A')}")
                print(f"   Tool Calls: {len(parsed_result.get('tool_calls', []))}")
                if parsed_result.get('tool_calls'):
                    for i, tool_call in enumerate(parsed_result['tool_calls']):
                        print(f"     [{i}] {tool_call.get('name', 'unknown')}: {tool_call.get('params', {})}")
                if parsed_result.get('error'):
                    print(f"   Error: {parsed_result['error']}")
                print()
            else:
                print()
            
            return parsed_result
        
        except Exception as e:
            return {
                "error": str(e),
                "is_complete": False
            }
    
    def parse_response(self, content: str) -> Dict[str, Any]:
        """
        Parse model response to extract tool calls or completion status.
        
        Args:
            content: Raw response content
        
        Returns:
            Parsed response dict
        """
        # Clean the content first
        content = content.strip()
        
        # Try to find JSON in the response
        try:
            # Look for JSON blocks
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
            else:
                json_str = content
            
            # Clean up the JSON string
            json_str = json_str.strip()
            
            # Parse JSON
            parsed = json.loads(json_str)
            
            # Check if task is complete
            if parsed.get("status") == "complete":
                return {
                    "is_complete": True,
                    "final_answer": parsed.get("result", "Task completed"),
                    "thought": parsed.get("thought", ""),
                    "raw_response": content
                }
            
            # Extract tool call
            if "tool" in parsed:
                return {
                    "is_complete": False,
                    "tool_calls": [{
                        "name": parsed["tool"],
                        "params": parsed.get("parameters", {})
                    }],
                    "thought": parsed.get("thought", ""),
                    "raw_response": content
                }
            
            # If no clear action, return the content
            return {
                "is_complete": False,
                "error": "No clear tool call or completion in response",
                "raw_response": content
            }
        
        except json.JSONDecodeError as e:
            # Try to extract information from text format like "Tool: scroll\nResult: ..."
            if "Tool:" in content and "Result:" in content:
                lines = content.strip().split('\n')
                tool_name = None
                for line in lines:
                    if line.startswith("Tool:"):
                        tool_name = line.replace("Tool:", "").strip()
                        break
                
                if tool_name:
                    return {
                        "is_complete": False,
                        "tool_calls": [{
                            "name": tool_name,
                            "params": {}
                        }],
                        "thought": f"Extracted tool from text format: {tool_name}",
                        "raw_response": content
                    }
            
            # If all else fails, return error
            return {
                "is_complete": False,
                "error": f"Failed to parse JSON: {e}",
                "raw_response": content
            }
    
    def test_connection(self) -> bool:
        """
        Test if the API connection is working.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            print(f"✅ API connection successful: {response.choices[0].message.content[:50]}")
            return True
        except Exception as e:
            print(f"❌ API connection failed: {e}")
            return False


# Utility function to create client from config
def create_vllm_client_from_env() -> VLLMClient:
    """
    Create VLLM client from environment variables.
    
    Environment variables:
        OPENAI_BASE_URL: API base URL
        OPENAI_API_KEY: API key
        OPENAI_MODEL: Model name
    
    Returns:
        Configured VLLMClient instance
    """
    return VLLMClient(
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("OPENAI_MODEL")
    )


if __name__ == "__main__":
    # Test the client
    print("Testing VLLM Client...")
    
    client = VLLMClient(
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "EMPTY"),
        model=os.getenv("OPENAI_MODEL", "gpt-4o")
    )
    
    # Test connection
    client.test_connection()
    
    # Test image encoding (if test screenshot exists)
    test_screenshot = ARTIFACTS_DIR / "test_screenshot.png"
    if test_screenshot.exists():
        print("\nTesting image encoding...")
        encoded = client.encode_image(str(test_screenshot))
        print(f"✅ Image encoded: {len(encoded)} characters")
    
    print("\n✅ VLLM Client ready!")

