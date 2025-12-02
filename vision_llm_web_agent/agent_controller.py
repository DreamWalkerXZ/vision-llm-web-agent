"""
Web Agent Controller
Orchestrates multi-round interaction between VLLM and browser automation tools
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from .vllm_client import VLLMClient
from .tools import get_tool_registry
from .config.settings import ARTIFACTS_DIR
from .tools.dom_analyzer import semantic_dom_analyzer


class Agent:
    """
    Autonomous web agent that executes tasks through multi-round VLLM interaction
    """
    
    # Tool registry will be initialized dynamically
    _tool_registry = None
    
    @classmethod
    def get_tool_registry(cls):
        """Get the tool registry, initializing if needed"""
        if cls._tool_registry is None:
            cls._tool_registry = get_tool_registry()
        return cls._tool_registry
    
    @classmethod
    def get_tool_definitions(cls):
        """Get tool definitions for VLLM from the registry"""
        registry = cls.get_tool_registry()
        return registry.get_tool_definitions_for_vllm()
    
    def __init__(
        self,
        vllm_client: VLLMClient,
        max_rounds: int = 20,
        timeout_per_round: int = 30,
        artifacts_dir: Optional[str] = None
    ):
        """
        Initialize Web Agent.
        
        Args:
            vllm_client: Vision LLM client
            max_rounds: Maximum number of execution rounds
            timeout_per_round: Timeout in seconds for each round
            artifacts_dir: Directory to save execution artifacts
        """
        self.vllm = vllm_client
        self.max_rounds = max_rounds
        self.timeout_per_round = timeout_per_round
        
        # Generate session ID first
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create session-specific artifacts directory
        # Each run gets its own subdirectory: artifacts/YYYYMMDD_HHMMSS/
        base_artifacts_dir = Path(artifacts_dir) if artifacts_dir else ARTIFACTS_DIR
        self.artifacts_dir = base_artifacts_dir / self.session_id
        
        # Set the session artifacts directory globally so tools can access it
        from .config.settings import set_session_artifacts_dir
        set_session_artifacts_dir(self.artifacts_dir)
        
        self.history: List[Dict[str, Any]] = []
        self.execution_log: List[Dict[str, Any]] = []
        self.next_step = ""
        
        # Context mode: 'web_browsing' or 'local_file_processing'
        self.context_mode = "web_browsing"
        self.downloaded_pdf_files: List[str] = []  # Track downloaded PDFs
        self.extracted_images: List[str] = []  # Track extracted image paths (relative to artifacts/)
        self.original_instruction: str = ""  # Store original task for multi-step detection
        
        # Track recent failed actions to detect loops
        self.recent_failures: List[Dict[str, Any]] = []  # List of recent failed tool calls
        self.recent_tool_calls: List[Dict[str, Any]] = []  # Track recent tool calls to detect repetition
        self.max_recent_calls = 5  # Track last 5 tool calls
        self.max_failure_history = 10  # Keep last 10 failures
        self.repeated_failure_threshold = 3  # If same action fails 3 times, force intervention
        self.force_dom_summary_threshold = 5  # If same action fails 5 times, force dom_summary call
        self.blocked_actions: Dict[str, int] = {}  # Track blocked actions: {action_key: failure_count}
        
        # File processing tools that should trigger auto-completion after 3 repeated calls
        self.file_processing_tools = [
            "pdf_extract_text",
            "pdf_extract_images",
            "save_image",
            "write_text",
            "ocr_image_to_text"
        ]
        self.file_processing_repeat_threshold = 3  # If same file processing tool called 3 times, end instruction
        
        # Create session-specific artifacts directory
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        print("🤖 Web Agent initialized")
        print(f"   Session ID: {self.session_id}")
        print(f"   Max rounds: {max_rounds}")
        print(f"   Timeout per round: {timeout_per_round}s")
        print(f"   Artifacts dir: {self.artifacts_dir}")
    
    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """
        Execute a tool with given parameters.
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
        
        Returns:
            Tool execution result as string
        """
        registry = self.get_tool_registry()
        tool_func = registry.get_tool(tool_name)
        
        if tool_func is None:
            return f"❌ Unknown tool: {tool_name}"
        
        try:
            # Block download_pdf if already in local_file_processing mode
            if tool_name == "download_pdf" and self.context_mode == "local_file_processing":
                if self.downloaded_pdf_files:
                    return f"⚠️ PDF already downloaded! You are in LOCAL FILE PROCESSING mode. Available files: {', '.join(self.downloaded_pdf_files)}. Use pdf_extract_text/pdf_extract_images tools to process the existing PDF. DO NOT download again!"
                else:
                    # Allow download if no files tracked (edge case)
                    pass
            
            result = tool_func(**parameters)
            result_str = str(result)
            
            # Switch to local file processing mode after successful PDF download
            if tool_name == "download_pdf" and "✅" in result_str:
                file_name = parameters.get("file_name")
                if file_name:
                    # Check if file already exists in the list
                    if file_name not in self.downloaded_pdf_files:
                        self.downloaded_pdf_files.append(file_name)
                    # Switch context mode
                    self.context_mode = "local_file_processing"
                    print(f"\n📄 PDF downloaded: {file_name}")
                    print(f"🔄 Context switched to: local_file_processing mode")
                    print(f"   💡 VLLM should now use pdf_extract_text/pdf_extract_images tools to process the local file")
                    print(f"   ⚠️  DO NOT download PDF again - use the existing file!")
                    
                    # Add context switch message to history with multi-step task reminder
                    context_switch_msg = {
                        "role": "user",
                        "content": json.dumps({
                            "tool_execution": "download_pdf",
                            "result": result_str,
                            "context_switch": {
                                "mode": "local_file_processing",
                                "message": f"PDF file '{file_name}' has been successfully downloaded to local artifacts directory. You should now use local file processing tools (pdf_extract_text, pdf_extract_images, ocr_image_to_text, save_image, write_text) to process this file. These tools work on local files and do NOT require web browser operations. Ignore any screenshot/DOM information when processing local files.",
                                "available_local_files": self.downloaded_pdf_files
                            }
                        })
                    }
                    self.history.append(context_switch_msg)
            
            return result_str
        except TypeError as e:
            return f"❌ Invalid parameters for {tool_name}: {e}"
        except Exception as e:
            return f"❌ Tool execution failed: {e}"
    
    def execute(self, instruction: str, is_followup: bool = False) -> str:
        """
        Execute a user instruction through multi-round interaction.
        
        Args:
            instruction: Natural language instruction from user
        
        Returns:
            Final answer or error message
        """
        print(f"\n{'='*80}")
        if is_followup:
            print(f"🔄 Follow-up Task: {instruction}")
        else:
            print(f"🎯 Task: {instruction}")
        print(f"{'='*80}\n")
        
        # Reset recent tool calls for new instruction (to track repetition within this instruction)
        self.recent_tool_calls = []
        
        # Initialize history with user instruction (or append if follow-up)
        if not is_followup:
            self.history = [{
                "role": "user",
                "content": instruction
            }]
            self.original_instruction = instruction
        else:
            self.history.append({
                "role": "user",
                "content": instruction
            })
            self.original_instruction = instruction
        
        start_time = time.time()
        
        # Open browser to DuckDuckGo before first round (only if not follow-up)
        if not is_followup:
            print("🌐 Opening browser to DuckDuckGo")
            try:
                registry = self.get_tool_registry()
                goto_func = registry.get_tool("goto")
                if goto_func:
                    result = goto_func("https://duckduckgo.com/")
                    print(f"   {result}")
                else:
                    print("   ⚠️  goto tool not available")
            except Exception as e:
                print(f"   ⚠️  Failed to open browser: {e}")
        
        try:
            # Determine starting round number (for follow-ups, continue from where we left off)
            start_round = len(self.execution_log) if is_followup else 0
            for i in range(start_round, self.max_rounds):
                round_num = i
                print(f"\n{'─'*80}")
                print(f"🔄 Round {round_num + 1}/{self.max_rounds}")
                print(f"{'─'*80}")
                
                # Execute one round
                result = self.execute_round(round_num)
                
                if result["is_complete"]:
                    elapsed = time.time() - start_time
                    print(f"\n{'='*80}")
                    print(f"✅ Task completed in {elapsed:.1f}s ({round_num + 1} rounds)")
                    print(f"{'='*80}")
                    print(f"\n{result['final_answer']}")
                    summary = self.summary_history()
                    self.history = [{
                        'role': "assistant",
                        'content': "I have completed the previous task. Here is a brief summary of what was done:\n" + summary
                    }]
                    
                    return result["final_answer"]
                
                # Check for errors
                if result.get("error"):
                    print(f"⚠️  Error in round {round_num + 1}: {result['error']}")
                    # Continue to next round to let VLLM recover
            
            # Max rounds reached
            print(f"\n{'='*80}")
            print(f"⚠️  Max rounds ({self.max_rounds}) reached")
            print(f"{'='*80}")
            
            return f"Task incomplete after {self.max_rounds} rounds. Last state saved to artifacts."
        
        except Exception as e:
            print(f"\n❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            
            return f"Fatal error: {str(e)}"
    
    def execute_round(self, round_num: int) -> Dict[str, Any]:
        """
        Execute one round of the agent loop.
        
        Args:
            round_num: Current round number (0-indexed)
        
        Returns:
            Round result dict with is_complete, final_answer, or error
        """
        round_start_time = time.time()
        
        # 1. Get current state (screenshot + DOM)
        print("📸 Capturing current state...")
        screenshot_path = str(self.artifacts_dir / f"step_{round_num:02d}.png")
        screenshot_available = False
        
        try:
            registry = self.get_tool_registry()
            screenshot_func = registry.get_tool("screenshot")
            if screenshot_func:
                screenshot_result = screenshot_func(screenshot_path)
                print(f"   {screenshot_result}")
                # Check if screenshot was actually created
                if Path(screenshot_path).exists():
                    screenshot_available = True
                else:
                    print("   ⚠️  Screenshot file not created")
            else:
                print("   ⚠️  Screenshot tool not available")
        except Exception as e:
            print(f"   ⚠️  Screenshot failed: {e}")
        
        # Initialize dom variable before try block to ensure it's always defined
        dom = "DOM not available"
        dom_analysis = None
        
        try:
            # Check if browser is initialized
            from .tools.browser_control import browser_state
            if browser_state.is_initialized:
                # Get next_step or use first instruction, with safety check for empty history
                next_step = self.next_step if self.next_step else (self.history[0]['content'] if self.history else "Analyze the page")
                
                # Use semantic_dom_analyzer directly (not through tool registry)
                # This allows passing client and model parameters without breaking tool abstraction
                dom_analysis = semantic_dom_analyzer.analyze_page(
                    browser_state.get_current_page(), 
                    self.vllm.client, 
                    user_prompt=next_step, 
                    model=self.vllm.language_model, 
                    max_elements=5
                )
                
                # Handle error case where dom_analysis is a string
                if isinstance(dom_analysis, str):
                    dom = dom_analysis
                    print(f"   ⚠️  DOM analysis returned error: {dom_analysis}")
                elif isinstance(dom_analysis, dict):
                    # Successfully got DOM analysis dictionary
                    dom = dom_analysis.get("llm_text", "No DOM text available")
                    print(f"   ✅ DOM extracted ({len(dom)} chars)")
                    
                    # Annotate screenshot with element numbers if we have both
                    if screenshot_available and dom_analysis.get('filtered_elements'):
                        annotated_path = str(self.artifacts_dir / f"{self.session_id}_step_{round_num:03d}_annotated.png")
                        annotation_result = semantic_dom_analyzer.annotate_screenshot(
                            screenshot_path, 
                            dom_analysis['filtered_elements'],
                            output_path=annotated_path
                        )
                        print(f"   {annotation_result}")
                        # Use annotated screenshot for VLLM
                        if Path(annotated_path).exists():
                            screenshot_path = annotated_path
                else:
                    dom = "DOM analysis returned unexpected type"
                    print(f"   ⚠️  DOM analysis returned unexpected type: {type(dom_analysis)}")
            else:
                dom = "Browser not initialized"
                print("   ⚠️  Browser not initialized")
        except Exception as e:
            dom = f"Failed to extract DOM: {str(e)}"
            print(f"   ⚠️  DOM extraction failed: {e}")
        
        # 2. Check for blocked actions and force dom_summary if needed
        if self.context_mode == "web_browsing" and self.blocked_actions:
            # Check if we need to force dom_summary
            for action_key, failure_count in self.blocked_actions.items():
                if failure_count >= self.force_dom_summary_threshold:
                    print(f"\n🚨 FORCING DOM SUMMARY: Action '{action_key}' has failed {failure_count} times")
                    print(f"   🔍 Automatically calling dom_summary to find correct selector...")
                    try:
                        
                        dom_analysis = semantic_dom_analyzer.analyze_page(
                            browser_state.get_current_page(), 
                            self.vllm.client, 
                            user_prompt=next_step, 
                            model=self.vllm.language_model, 
                            max_elements=5
                        )
                        dom_result = dom_analysis.get("llm_text", "No DOM text available") if isinstance(dom_analysis, dict) else str(dom_analysis)
                        # Add forced dom_summary result to history
                        forced_dom_msg = {
                            "role": "user",
                            "content": f"🚨 FORCED ACTION: dom_summary was automatically called because '{action_key}' has failed {failure_count} times. Here is the DOM summary:\n{dom_result}\n\nYou MUST use the selectors from the INPUT FIELDS section above. DO NOT repeat the blocked action!"
                        }
                        self.history.append(forced_dom_msg)
                        print(f"   ✅ Forced dom_summary completed and added to history")
                        # Update dom in state_info
                        if "dom" in locals():
                            dom = dom_result
                    except Exception as e:
                        print(f"   ⚠️  Failed to force dom_summary: {e}")
        
        # 3. VLLM decides next action
        print("🤔 VLLM planning next action...")
        
        # Adjust state info based on context mode
        if self.context_mode == "local_file_processing":
            # Build instruction based on original task to remind about multi-step tasks
            multi_step_reminder = ""
            if self.original_instruction:
                original_lower = self.original_instruction.lower()
                if "save all" in original_lower:
                    multi_step_reminder = "\n\n**🚨 CRITICAL - MULTI-STEP TASK DETECTED:**\nYour original task requires multiple steps. You MUST complete ALL steps before marking as complete:\n1. **FIRST:** Extract ALL images with pdf_extract_images(file_name=\"report.pdf\", output_dir=\"extracted_images\") WITHOUT page_num\n2. **SECOND:** Save all extracted images using save_image for each image\n3. **THIRD:** Find and interpret the first image (if task says 'interpret the first image')\n4. **ONLY THEN:** Mark status as \"complete\" after ALL steps are done!\n\n**DO NOT skip steps!** Check your original task requirements carefully!"
            
            # In local file processing mode, screenshot/DOM are not relevant
            state_info = {
                "context_mode": "local_file_processing",
                "screenshot": None,
                "dom": "N/A - Currently processing local files, web browser context not relevant",
                "round": round_num,
                "screenshot_available": False,
                "available_local_files": self.downloaded_pdf_files,
                "extracted_images": self.extracted_images,  # Add extracted images for VLLM visualization
                "instruction": f"You are currently in LOCAL FILE PROCESSING mode. Use pdf_extract_text, pdf_extract_images, save_image, write_text, and ocr_image_to_text tools to process the downloaded PDF files. These tools work on local files in the artifacts/ directory. Do NOT use web browser tools (click, type_text, etc.) in this mode. DO NOT download PDF again - it's already downloaded!{multi_step_reminder}"
            }
            print(f"   📁 Context: Local file processing mode (available files: {self.downloaded_pdf_files})")
            if self.extracted_images:
                print(f"   🖼️  Extracted images available for visualization: {len(self.extracted_images)} images")
        else:
            # Normal web browsing mode
            # Check if current page is a PDF
            is_pdf_page = False
            pdf_url = None
            try:
                registry = self.get_tool_registry()
                # Get current URL from browser state
                from .tools.browser_control import browser_state
                if browser_state.is_initialized:
                    current_url = browser_state.get_current_page().url
                    # Check if URL indicates PDF
                    if current_url.lower().endswith('.pdf') or '/pdf' in current_url.lower() or 'application/pdf' in current_url.lower():
                        is_pdf_page = True
                        pdf_url = current_url
            except Exception:
                pass
            
            state_info = {
                "context_mode": "web_browsing",
                "screenshot": screenshot_path if screenshot_available else None,
                "dom": dom,
                "round": round_num,
                "screenshot_available": screenshot_available,
                "instruction": "Analyze the current state and decide the next action. Respond with valid JSON."
            }
            
            # Add PDF detection warning if PDF page detected
            if is_pdf_page:
                state_info["pdf_detected"] = True
                state_info["pdf_url"] = pdf_url
                state_info["instruction"] = f"🚨 CRITICAL: PDF PAGE DETECTED! The current page is a PDF file (URL: {pdf_url}). You MUST download it using download_pdf(url=\"{pdf_url}\", file_name=\"report.pdf\") before processing. DO NOT try to scroll or interact with the PDF in the browser - download it first!"
        
        try:
            response = self.vllm.plan_next_action(
                self.history,
                state_info,
                self.get_tool_definitions()
            )
        except Exception as e:
            return {"error": f"VLLM planning failed: {e}", "is_complete": False}
        
        # Extract VLLM raw input and output for logging
        vllm_raw_input = response.get("vllm_raw_input")
        vllm_raw_output = response.get("vllm_raw_output")
        
        # Log thought
        if response.get("thought"):
            print(f"💭 Thought: {response['thought']}")
        
        if response.get("next"):
            self.next_step = response["next"]
            print(f"➡️  Next step set for DOM analysis: {self.next_step}")
        else:
            self.next_step = ""
        
        # 3. Check if task is complete
        if response.get("is_complete"):
            final_answer = response.get("final_answer", "Task completed")
            
            # Log completion with VLLM raw data
            self.execution_log.append({
                "round": round_num,
                "action": "completion",
                "final_answer": final_answer,
                "elapsed_time": time.time() - round_start_time,
                "vllm_raw_input": vllm_raw_input,
                "vllm_raw_output": vllm_raw_output
            })
            
            # Save execution log after completion
            self.save_execution_log()
            
            return {
                "is_complete": True,
                "final_answer": final_answer
            }
        
        # 4. Execute tool calls
        if response.get("error"):
            # VLLM returned an error (already handled retry in vllm_client)
            self.execution_log.append({
                "round": round_num,
                "error": response["error"],
                "raw_response": response.get("raw_response", ""),
                "elapsed_time": time.time() - round_start_time,
                "vllm_raw_input": vllm_raw_input,
                "vllm_raw_output": vllm_raw_output
            })
            
            # Save execution log after error
            self.save_execution_log()
            
            # Don't add error to history - let next round provide fresh context
            return {"error": response["error"], "is_complete": False}
        
        tool_calls = response.get("tool_calls", [])
        
        if not tool_calls:
            error_msg = "No tool calls found in VLLM response"
            self.execution_log.append({
                "round": round_num,
                "error": error_msg,
                "raw_response": response.get("raw_response", ""),
                "elapsed_time": time.time() - round_start_time,
                "vllm_raw_input": vllm_raw_input,
                "vllm_raw_output": vllm_raw_output
            })
            
            # Save execution log after error
            self.save_execution_log()
            
            return {"error": error_msg, "is_complete": False}
        
        # Execute each tool call
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            parameters = tool_call.get("params", {})
            
            # Check for repeated tool calls (same tool with same parameters)
            current_call_key = f"{tool_name}:{json.dumps(parameters, sort_keys=True)}"
            recent_same_calls = [call for call in self.recent_tool_calls if call.get("key") == current_call_key]
            repeat_count = len(recent_same_calls) + 1  # +1 for current call
            
            # Check if this is a file processing tool and if it's been called 3 times
            # If so, auto-complete the instruction to prevent infinite loop
            if tool_name in self.file_processing_tools and repeat_count >= self.file_processing_repeat_threshold:
                print(f"\n🚨 REPEATED FILE PROCESSING TOOL CALL DETECTED: {tool_name} called {repeat_count} times")
                print(f"   🎯 Auto-completing instruction to prevent infinite loop...")
                
                # Add assistant's tool call to history for logging
                assistant_tool_call = {
                    "thought": response.get("thought", ""),
                    "tool": tool_name,
                    "parameters": parameters
                }
                self.history.append({
                    "role": "assistant",
                    "content": json.dumps(assistant_tool_call, ensure_ascii=False, indent=2)
                })
                
                # Add auto-completion message to history
                auto_complete_msg = {
                    "role": "user",
                    "content": json.dumps({
                        "tool_execution": "auto_complete",
                        "result": f"⚠️ Instruction auto-completed: The file processing tool '{tool_name}' has been called {repeat_count} times with the same parameters. This indicates the task may be stuck in a loop. Current instruction has been ended."
                    }, ensure_ascii=False, indent=2)
                }
                self.history.append(auto_complete_msg)
                
                # Log execution
                self.execution_log.append({
                    "round": round_num,
                    "action": "auto_complete",
                    "reason": f"File processing tool '{tool_name}' repeated {repeat_count} times",
                    "tool": tool_name,
                    "parameters": parameters,
                    "elapsed_time": time.time() - round_start_time
                })
                self.save_execution_log()
                
                completion_msg = (
                    f"⚠️ Instruction auto-completed: The file processing tool '{tool_name}' has been called "
                    f"{repeat_count} times with the same parameters. This indicates the task may be stuck in a loop. "
                    f"Current instruction has been ended. Please provide the next instruction."
                )
                
                return {
                    "is_complete": True,
                    "final_answer": completion_msg
                }
            
            if len(recent_same_calls) >= 2:  # If same call appears 2+ times in recent history
                print(f"\n⚠️  DETECTED REPEATED TOOL CALL: {tool_name} with same parameters called {repeat_count} times")
                print(f"   This might indicate the VLLM is stuck. Adding intervention message...")
                
                # Add intervention message
                intervention_msg = {
                    "role": "user",
                    "content": f"⚠️ INTERVENTION: You have called '{tool_name}' with the same parameters {repeat_count} times. The result was already provided. You MUST proceed to the next step:\n"
                }
                
                # Provide specific guidance based on tool
                if tool_name == "pdf_extract_text":
                    intervention_msg["content"] += "- If you extracted text to find Figure 1, check the FIGURE LOCATIONS SUMMARY and proceed to extract images.\n"
                    intervention_msg["content"] += "- DO NOT extract text again - you already have the information you need!\n"
                elif tool_name == "pdf_extract_images":
                    intervention_msg["content"] += "- Images have been extracted. You MUST now save them using save_image or proceed to interpret them.\n"
                    intervention_msg["content"] += "- DO NOT extract images again!\n"
                
                self.history.append(intervention_msg)
                print(f"   ✅ Added intervention message to guide next action")
            
            # Track this tool call
            self.recent_tool_calls.append({
                "key": current_call_key,
                "tool": tool_name,
                "parameters": parameters,
                "round": round_num
            })
            # Keep only recent calls
            if len(self.recent_tool_calls) > self.max_recent_calls:
                self.recent_tool_calls.pop(0)
            
            # Check if this action is blocked
            original_tool_name = tool_name
            original_parameters = parameters.copy()
            if self.context_mode == "web_browsing" and tool_name in ["click", "type_text", "press_key"]:
                action_key = f"{tool_name}:{json.dumps(parameters, sort_keys=True)}"
                if action_key in self.blocked_actions:
                    failure_count = self.blocked_actions[action_key]
                    if failure_count >= self.force_dom_summary_threshold:
                        print(f"\n🚨 BLOCKED ACTION: '{action_key}' has failed {failure_count} times")
                        print(f"   🔍 Automatically replacing with dom_summary call...")
                        
                        # Replace blocked action with dom_summary
                        tool_name = "dom_summary"
                        parameters = {"max_elements": 150}
                        
                        # Add blocking message to history BEFORE assistant's tool call
                        blocking_msg = {
                            "role": "user",
                            "content": f"🚨 ACTION BLOCKED: Your requested action '{original_tool_name}' with parameters {json.dumps(original_parameters)} has been blocked because it has failed {failure_count} times. The system has automatically replaced it with a dom_summary call. You MUST use the selectors from the DOM summary result. DO NOT attempt the blocked action again!"
                        }
                        self.history.append(blocking_msg)
            
            print(f"🔧 Executing: {tool_name}({json.dumps(parameters, indent=2)})")
            
            # First, add assistant's tool call decision to history
            assistant_tool_call = {
                "thought": response.get("thought", ""),
                "tool": tool_name,
                "parameters": parameters,
                "next": self.next_step
            }
            self.history.append({
                "role": "assistant",
                "content": json.dumps(assistant_tool_call, ensure_ascii=False, indent=2)
            })
            
            # Execute with timeout
            try:
                result = self.execute_tool(tool_name, parameters)
                print(f"   {result}")
            except Exception as e:
                result = f"❌ Tool execution error: {e}"
                print(f"   {result}")
            
            # Track failed actions to detect loops
            is_failure = "❌" in str(result) or "Failed" in str(result) or "error" in str(result).lower()
            # Also track ineffective clicks (URL unchanged for submit buttons)
            is_ineffective_click = (
                tool_name == "click" and 
                "Page URL unchanged" in str(result) and 
                ("INEFFECTIVE CLICK" in str(result) or "search" in str(parameters.get("text", "")).lower() or "submit" in str(parameters.get("text", "")).lower())
            )
            repeated_failure_detected = False
            same_failures_count = 0
            
            if is_failure or is_ineffective_click:
                failure_key = f"{tool_name}:{json.dumps(parameters, sort_keys=True)}"
                self.recent_failures.append({
                    "key": failure_key,
                    "tool": tool_name,
                    "parameters": parameters,
                    "result": result,
                    "round": round_num,
                    "is_ineffective": is_ineffective_click
                })
                
                # If it's an ineffective click, add a suggestion to use press_key("Enter")
                if is_ineffective_click:
                    print(f"\n⚠️  INEFFECTIVE CLICK DETECTED: Click on '{parameters.get('text', 'button')}' did not change URL")
                    print(f"   💡 Suggestion: Use press_key(\"Enter\") in the input field instead of clicking the button")
                # Keep only recent failures
                if len(self.recent_failures) > self.max_failure_history:
                    self.recent_failures = self.recent_failures[-self.max_failure_history:]
                
                # Check for repeated failures
                same_failures = [f for f in self.recent_failures if f["key"] == failure_key]
                same_failures_count = len(same_failures)
                
                # Update blocked actions
                if self.context_mode == "web_browsing" and tool_name in ["click", "type_text", "press_key"]:
                    self.blocked_actions[failure_key] = same_failures_count
                
                if same_failures_count >= self.repeated_failure_threshold:
                    repeated_failure_detected = True
                    print(f"\n⚠️  DETECTED REPEATED FAILURE: {tool_name} failed {same_failures_count} times with same parameters")
                    
                    # Force DOM summary if in web browsing mode and it's a browser interaction tool
                    if self.context_mode == "web_browsing" and tool_name in ["click", "type_text", "press_key"]:
                        if same_failures_count >= self.force_dom_summary_threshold:
                            print(f"   🚨 CRITICAL: Action will be BLOCKED and replaced with dom_summary on next attempt")
                        else:
                            print(f"   🔍 Forcing DOM summary check to find correct selector...")
                            # Add a special message to history to force VLLM to check DOM
                            intervention_msg = {
                                "role": "user",
                                "content": f"⚠️ INTERVENTION: The action '{tool_name}' with parameters {json.dumps(parameters)} has failed {same_failures_count} times. You MUST call 'dom_summary' tool to find the correct selector before trying again. DO NOT repeat the same failed action! If this action fails {self.force_dom_summary_threshold} times, it will be automatically blocked."
                            }
                            self.history.append(intervention_msg)
                            print(f"   ✅ Added intervention message to force DOM summary check")
            
            # Track extracted images for VLLM visualization
            if tool_name == "pdf_extract_images" and "✅" in str(result):
                # Parse extracted image paths from result
                # Result format: "✅ Extracted N images to dir:\n  - path1\n  - path2..."
                lines = str(result).split('\n')
                new_images = []
                for line in lines:
                    line = line.strip()
                    if line.startswith('- '):
                        img_path = line[2:].strip()  # Remove "- " prefix
                        # Clean up path (remove any extra whitespace or quotes)
                        img_path = img_path.strip('"\'')
                        if img_path and img_path not in self.extracted_images:
                            self.extracted_images.append(img_path)
                            new_images.append(img_path)
                if new_images:
                    print(f"   📸 Tracked {len(new_images)} new extracted images for VLLM visualization")
                    print(f"      Total tracked images: {len(self.extracted_images)}")
            
            # Add tool execution result as user message to history
            # If there was a repeated failure, make it more prominent
            tool_result = {
                "tool_execution": tool_name,
                "result": result
            }
            if repeated_failure_detected:
                tool_result["⚠️ CRITICAL"] = f"This action has failed {same_failures_count} times. You MUST call 'dom_summary' tool NOW to find the correct selector. DO NOT repeat this action!"
            
            # Add context switch notification for PDF downloads
            if tool_name == "download_pdf" and "✅" in str(result):
                file_name = parameters.get("file_name")
                context_notification = {
                    "tool_execution": tool_name,
                    "result": result,
                    "context_switch": {
                        "mode": "local_file_processing",
                        "message": f"PDF file '{file_name}' has been successfully downloaded to local artifacts directory. You should now use local file processing tools (pdf_extract_text, pdf_extract_images, ocr_image_to_text) to process this file. These tools work on local files and do NOT require web browser operations. Ignore any screenshot/DOM information when processing local files.\n\n**IMPORTANT - For tasks requiring specific figures (e.g., 'interpret Figure 1'):**\n1. FIRST extract text from PDF (pdf_extract_text without page_num) to search for 'Figure 1' in the text and find which page it's on\n2. THEN extract images ONLY from that specific page (use page_num parameter)\n3. DO NOT extract images from page 1 or all pages before finding where Figure 1 is located!",
                        "available_local_files": [file_name]
                    }
                }
                self.history.append({
                    "role": "user",
                    "content": json.dumps(context_notification, ensure_ascii=False, indent=2)
                })
            else:
                self.history.append({
                    "role": "user",
                    "content": json.dumps(tool_result, ensure_ascii=False, indent=2)
                })
            
            # Log execution with VLLM raw data
            self.execution_log.append({
                "round": round_num,
                "tool": tool_name,
                "parameters": parameters,
                "result": result,
                "elapsed_time": time.time() - round_start_time,
                "vllm_raw_input": vllm_raw_input,
                "vllm_raw_output": vllm_raw_output
            })
            
            # Save execution log after each tool execution
            self.save_execution_log()
        
        return {"is_complete": False}
    
    def summary_history(self):
        """Generate a summary of the conversation history if one task is finished"""
        summary = ""
        for msg in self.history:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            summary += f"{role}:\n{content}\n\n"
        # use llm to summarize
        self.history.append({
            "role": "user",
            "content": f"Please provide a concise summary of the following conversation history:\n\n{summary}\n\nSummary:"
        })
        try:
            summary = self.vllm.plan_next_action(
                self.history,
                {"instruction": "Summarize the conversation history concisely."},
                []
            )
            while summary['is_complete'] is False:
                # keep summarizing until complete
                summary = self.vllm.plan_next_action(
                    self.history,
                    {"instruction": "Summarize the conversation history concisely."},
                    []
                )
            final_answer = summary.get("final_answer", "")
        except Exception as e:
            print(f"   ⚠️  Failed to summarize history: {e}")
        return final_answer
    
    def save_execution_log(self):
        """Save execution log to JSON file"""
        log_path = self.artifacts_dir / f"execution_log_{self.session_id}.json"
        
        log_data = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "history": self.history,
            "execution_log": self.execution_log,
            "total_rounds": len(self.execution_log)
        }
        
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        print(f"📝 Execution log updated: {log_path}")
    
    def close_session(self):
        """
        Close the session, generate final interpretation, and clean up resources.
        This should be called at the end of a session.
        """
        print("\n" + "="*80)
        print("🔚 Closing session...")
        print("="*80)
        
        try:
            # Generate final interpretation
            from .tools.file_operations import generate_final_interpretation
            result = generate_final_interpretation()
            print(f"   {result}")
        except Exception as e:
            print(f"   ⚠️  Failed to generate final interpretation: {e}")
        
        # Clean up browser
        try:
            registry = self.get_tool_registry()
            close_browser_func = registry.get_tool("close_browser")
            if close_browser_func:
                close_browser_func()
        except Exception as e:
            print(f"   ⚠️  Error closing browser: {e}")
        
        print("   ✅ Session closed")


if __name__ == "__main__":
    print("Web Agent Controller")
    print("Use this module via main.py to execute tasks")

