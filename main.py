"""
Vision-LLM Web Agent - Main Entry Point
"""

from dotenv import load_dotenv

from vision_llm_web_agent.agent_controller import Agent
from vision_llm_web_agent.vllm_client import VLLMClient
from vision_llm_web_agent.config import (
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_LANGUAGE_MODEL,
    MAX_ROUNDS, TIMEOUT_PER_ROUND, ARTIFACTS_DIR
)

# Load environment variables from .env file
load_dotenv()


def main():
    """Main entry point"""
    
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                    Vision-LLM Web Agent                                   ║
║                  Autonomous Web Task Execution                            ║
╚═══════════════════════════════════════════════════════════════════════════╝
""")
    
    # Check for API configuration
    if not OPENAI_API_KEY or OPENAI_API_KEY in ["EMPTY", "test-key"]:
        print("⚠️  Warning: OPENAI_API_KEY not set or invalid")
        print("   Set environment variable or use example.env")
        print()
        
        # Ask if user wants to continue with a demo
        response = input("Continue anyway for demo? (y/n): ").strip().lower()
        if response != 'y':
            print("Exiting. Please set OPENAI_API_KEY and try again.")
            return
    
    # Initialize VLLM Client
    print("\n🔧 Initializing Vision LLM Client...")
    vllm = VLLMClient(
        base_url=OPENAI_BASE_URL,
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        language_model=OPENAI_LANGUAGE_MODEL
    )
    
    # Test connection (optional)
    print("\n🔗 Testing API connection...")
    connection_ok = vllm.test_connection()
    
    if not connection_ok:
        print("❌ API connection failed. Please check your configuration.")
        return
    
    # Initialize Agent
    print("\n🤖 Initializing Web Agent...")
    agent = Agent(
        vllm_client=vllm,
        max_rounds=MAX_ROUNDS,
        timeout_per_round=TIMEOUT_PER_ROUND,
        artifacts_dir=str(ARTIFACTS_DIR)
    )
    
    # Example tasks
    example_tasks = [
        "Go to example.com and take a screenshot",
        "Search for 'OpenAI GPT-4' on DuckDuckGo and screenshot the results",
        "Find the most recent technical report (PDF) about Qwen, download it, and interpret Figure 1",
    ]
    
    print("\n📋 Example tasks:")
    for i, task in enumerate(example_tasks, 1):
        print(f"   {i}. {task}")
    
    # Get user input
    print("\n" + "="*80)
    task = input("Enter your task (or press Enter for example 1): ").strip()
    
    if not task:
        task = example_tasks[0]
        print(f"Using example task: {task}")
    
    # Execute task with interactive session loop
    import time
    session_start_time = time.time()
    tasks_completed = 0
    
    try:
        # Execute first task (start new session)
        result = agent.execute(task, continue_session=False, close_browser=False)
        
        print("\n" + "="*80)
        print("📊 RESULT")
        print("="*80)
        print(result)
        print()
        tasks_completed += 1
        
        # Interactive loop for follow-up tasks
        while True:
            print("\n" + "="*80)
            next_task = input("Enter next task (or 'quit'/'exit' to end session): ").strip()
            
            if next_task.lower() in ['quit', 'exit', 'q']:
                print("Ending session...")
                break
            
            if not next_task:
                print("⚠️  Please enter a task or 'quit' to exit")
                continue
            
            # Execute follow-up task (continue session)
            result = agent.execute(next_task, continue_session=True, close_browser=False)
            
            print("\n" + "="*80)
            print("📊 RESULT")
            print("="*80)
            print(result)
            print()
            tasks_completed += 1
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Task interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up and show session statistics
        session_duration = time.time() - session_start_time
        
        print("\n" + "="*80)
        print("📊 SESSION SUMMARY")
        print("="*80)
        print(f"Session ID: {agent.session_id}")
        print(f"Tasks completed: {tasks_completed}")
        print(f"Total rounds: {agent.round_counter}")
        print(f"Session duration: {session_duration:.1f}s")
        
        # Show artifacts
        artifacts = list(ARTIFACTS_DIR.glob("*"))
        if artifacts:
            print(f"\nGenerated {len(artifacts)} artifacts in {ARTIFACTS_DIR}/")
            recent = sorted(artifacts, key=lambda p: p.stat().st_mtime, reverse=True)[:5]
            for artifact in recent:
                size = artifact.stat().st_size
                print(f"   - {artifact.name} ({size:,} bytes)")
        
        # End session and close browser
        agent.end_session()
    
    print("\n" + "="*80)
    print("👋 Thank you for using Vision-LLM Web Agent!")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
