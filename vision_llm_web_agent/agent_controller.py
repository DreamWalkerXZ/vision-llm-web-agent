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
        # Use settings.ARTIFACTS_DIR if not provided
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else ARTIFACTS_DIR
        
        self.history: List[Dict[str, Any]] = []
        self.execution_log: List[Dict[str, Any]] = []
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_active = False
        self.round_counter = 0
        
        # Create artifacts directory
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        print("🤖 Web Agent initialized")
        print(f"   Session ID: {self.session_id}")
        print(f"   Max rounds: {max_rounds}")
        print(f"   Timeout per round: {timeout_per_round}s")
        print(f"   Artifacts dir: {artifacts_dir}")
    
    def _start_new_session(self, instruction: str):
        """Initialize a new agent session with the first instruction."""
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.history = [{
            "role": "user",
            "content": instruction
        }]
        self.execution_log = []
        self.round_counter = 0
        self.session_active = True
        
        self._log_instruction(instruction, is_new_session=True)
    
    def _log_instruction(self, instruction: str, is_new_session: bool = False):
        """Record the user instruction in the execution log."""
        entry = {
            "round": self.round_counter,
            "action": "instruction",
            "instruction": instruction,
            "is_new_session": is_new_session,
            "timestamp": datetime.now().isoformat()
        }
        self.execution_log.append(entry)
        self.save_execution_log()
    
    def end_session(self):
        """Manually end the current session and clean up browser resources."""
        registry = self.get_tool_registry()
        close_browser_func = registry.get_tool("close_browser")
        if close_browser_func:
            close_browser_func()
        self.session_active = False
        self.round_counter = 0
        print("👋 Session ended and browser closed.")
    
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
            result = tool_func(**parameters)
            return str(result)
        except TypeError as e:
            return f"❌ Invalid parameters for {tool_name}: {e}"
        except Exception as e:
            return f"❌ Tool execution failed: {e}"
    
    def execute(
        self,
        instruction: str,
        continue_session: bool = False,
        close_browser: Optional[bool] = None
    ) -> str:
        """
        Execute a user instruction through multi-round interaction.
        
        Args:
            instruction: Natural language instruction from user
            continue_session: Whether to continue from an existing session
            close_browser: Whether to close the browser after execution. Defaults
                to False for continued sessions and True otherwise.
        
        Returns:
            Final answer or error message
        """
        if close_browser is None:
            close_browser = not continue_session
        
        if continue_session and not self.session_active:
            print("⚠️  No active session found. Starting a new session instead.")
            continue_session = False
        
        print(f"\n{'='*80}")
        if continue_session:
            print(f"🔁 Follow-up Task: {instruction}")
        else:
            print(f"🎯 Task: {instruction}")
        print(f"{'='*80}\n")
        
        if continue_session:
            self.history.append({
                "role": "user",
                "content": instruction
            })
            self._log_instruction(instruction, is_new_session=False)
        else:
            if self.session_active and close_browser:
                print("ℹ️  Ending previous session and starting a new one.")
            self._start_new_session(instruction)
        
        start_time = time.time()
        
        if not continue_session:
            # Open browser to DuckDuckGo before first round
            # User-Agent is set in browser initialization to avoid detection
            print("🌐 Opening browser to DuckDuckGo...")
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
        else:
            print("🌐 Continuing with existing browser session...")
        
        final_result = None
        final_status = None
        
        try:
            for _ in range(self.max_rounds):
                current_round = self.round_counter
                print(f"\n{'─'*80}")
                print(f"🔄 Round {current_round + 1}/{self.max_rounds}")
                print(f"{'─'*80}")
                
                # Execute one round
                result = self.execute_round(current_round)
                self.round_counter += 1
                
                if result["is_complete"]:
                    elapsed = time.time() - start_time
                    print(f"\n{'='*80}")
                    print(f"✅ Task completed in {elapsed:.1f}s ({current_round + 1} rounds total)")
                    print(f"{'='*80}")
                    print(f"\n{result['final_answer']}")
                    
                    final_result = result["final_answer"]
                    final_status = "completed"
                    break
                
                # Check for errors
                if result.get("error"):
                    print(f"⚠️  Error in round {current_round + 1}: {result['error']}")
                    # Continue to next round to let VLLM recover
            
            # Max rounds reached
            if final_result is None:
                print(f"\n{'='*80}")
                print(f"⚠️  Max rounds ({self.max_rounds}) reached")
                print(f"{'='*80}")
                
                final_result = f"Task incomplete after {self.max_rounds} rounds. Last state saved to artifacts."
                final_status = "incomplete"
        
        except Exception as e:
            print(f"\n❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            
            final_result = f"Fatal error: {str(e)}"
            final_status = "error"
        
        finally:
            # Generate and save final interpretation before cleanup
            if final_result is not None:
                self.generate_final_interpretation(instruction, final_result, final_status or "unknown")
            
            # Clean up browser
            if close_browser:
                registry = self.get_tool_registry()
                close_browser_func = registry.get_tool("close_browser")
                if close_browser_func:
                    close_browser_func()
                self.session_active = False
                self.round_counter = 0
        
        return final_result or "Task execution ended unexpectedly."
    
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
        screenshot_filename = f"{self.session_id}_step_{round_num:03d}.png"
        screenshot_path = str(self.artifacts_dir / screenshot_filename)
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
        
        try:
            registry = self.get_tool_registry()
            dom_func = registry.get_tool("dom_summary")
            if dom_func:
                dom = dom_func(max_elements=150)  # Increased to capture more elements
                print(f"   ✅ DOM extracted ({len(dom)} chars)")
            else:
                dom = "DOM tool not available"
                print("   ⚠️  DOM tool not available")
        except Exception as e:
            dom = "Failed to extract DOM"
            print(f"   ⚠️  DOM extraction failed: {e}")
        
        # 2. VLLM decides next action
        print("🤔 VLLM planning next action...")
        state_info = {
            "screenshot": screenshot_path if screenshot_available else None,
            "dom": dom[:2000],  # Limit DOM length
            "round": round_num,
            "screenshot_available": screenshot_available
        }
        
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
            
            print(f"🔧 Executing: {tool_name}({json.dumps(parameters, indent=2)})")
            
            # First, add assistant's tool call decision to history
            assistant_tool_call = {
                "thought": response.get("thought", ""),
                "tool": tool_name,
                "parameters": parameters
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
            
            # Add tool execution result as user message to history
            tool_result = {
                "tool_execution": tool_name,
                "result": result
            }
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
    
    def save_execution_log(self):
        """Save execution log to JSON file"""
        log_path = self.artifacts_dir / f"execution_log_{self.session_id}.json"
        
        log_data = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "history": self.history,
            "execution_log": self.execution_log,
            "total_rounds": self.round_counter
        }
        
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        print(f"📝 Execution log updated: {log_path}")
    
    def generate_final_interpretation(self, instruction: str, final_result: str, status: str) -> str:
        """
        Generate final interpretation using LLM and save to file.
        
        Args:
            instruction: Original user instruction
            final_result: Final result message
            status: Status of task completion ("completed", "failed", "incomplete", "error")
        
        Returns:
            Path to saved interpretation file
        """
        try:
            print("\n📝 Generating final interpretation...")
            
            # Prepare tool execution history for prompt context
            tool_history_entries = [
                {
                    "round": entry.get("round"),
                    "tool": entry.get("tool"),
                    "parameters": entry.get("parameters"),
                    "result": entry.get("result")
                }
                for entry in self.execution_log
                if entry.get("tool")
            ]
            
            max_history_entries = 25
            total_tool_entries = len(tool_history_entries)
            if total_tool_entries > max_history_entries:
                tool_history_note = f"(showing latest {max_history_entries} of {total_tool_entries} tool executions)"
                tool_history_entries = tool_history_entries[-max_history_entries:]
            else:
                tool_history_note = "(showing all tool executions)"
            
            tool_history_json = json.dumps(tool_history_entries, ensure_ascii=False, indent=2) if tool_history_entries else "[]"
            
            # Build prompt for final interpretation
            interpretation_prompt = f"""You are analyzing the execution of a web automation task. Please provide a comprehensive final interpretation of what happened.

**Original Task:**
{instruction}

**Final Status:**
{status}

**Final Result:**
{final_result}

**Execution Summary:**
- Total rounds executed: {len(self.execution_log)}
- Session ID: {self.session_id}

**Tool Execution History {tool_history_note}:**
```json
{tool_history_json}
```

Please provide a detailed interpretation that includes:
1. What the task was trying to accomplish
2. What actions were taken during execution
3. Whether the task was completed successfully or not, and why
4. Key findings or results
5. Any issues or limitations encountered
6. Overall assessment of the execution

Write in a clear, structured format suitable for documentation."""

            # Call VLLM to generate interpretation
            messages = [
                {"role": "system", "content": "You are a helpful assistant that provides clear, structured interpretations of task execution results."},
                {"role": "user", "content": interpretation_prompt}
            ]
            
            try:
                response = self.vllm.client.chat.completions.create(
                    model=self.vllm.model,
                    messages=messages,
                    max_tokens=self.vllm.max_tokens,
                    temperature=0.7
                )
                
                interpretation = response.choices[0].message.content
                
                # Save to file using write_text_to_file tool
                file_name = f"final_interpretation_{self.session_id}.txt"
                result = self.execute_tool("write_text", {
                    "content": interpretation,
                    "file_name": file_name
                })
                
                print(f"   ✅ {result}")
                return file_name
                
            except Exception as e:
                print(f"   ⚠️  Failed to generate interpretation: {e}")
                # Fallback: save a simple interpretation
                fallback_content = f"""Final Interpretation
{'='*80}

Task: {instruction}
Status: {status}
Result: {final_result}

Execution Summary:
- Total rounds: {len(self.execution_log)}
- Session ID: {self.session_id}

Note: Automatic interpretation generation failed. This is a fallback summary.
"""
                file_name = f"final_interpretation_{self.session_id}.txt"
                result = self.execute_tool("write_text", {
                    "content": fallback_content,
                    "file_name": file_name
                })
                print(f"   ✅ Saved fallback interpretation: {result}")
                return file_name
                
        except Exception as e:
            print(f"   ⚠️  Error generating final interpretation: {e}")
            return ""


if __name__ == "__main__":
    print("Web Agent Controller")
    print("Use this module via main.py to execute tasks")

