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
        
        finally:
            # Clean up browser
            if close_browser:
                registry = self.get_tool_registry()
                close_browser_func = registry.get_tool("close_browser")
                if close_browser_func:
                    close_browser_func()
                self.session_active = False
                self.round_counter = 0
    
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


if __name__ == "__main__":
    print("Web Agent Controller")
    print("Use this module via main.py to execute tasks")

