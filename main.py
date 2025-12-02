"""
Vision-LLM Web Agent - Main Entry Point
"""

from dotenv import load_dotenv

from vision_llm_web_agent.agent_controller import Agent
from vision_llm_web_agent.vllm_client import VLLMClient
from vision_llm_web_agent.config import (
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
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
        model=OPENAI_MODEL
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
    
    # Execute first task
    is_first_task = True
    try:
        while True:
            try:
                result = agent.execute(task, is_followup=not is_first_task)
                
                print("\n" + "="*80)
                print("📊 RESULT")
                print("="*80)
                print(result)
                print()
                
                # Show artifacts
                artifacts = list(ARTIFACTS_DIR.glob("*"))
                if artifacts:
                    print(f"\n📁 Generated {len(artifacts)} artifacts in {ARTIFACTS_DIR}/")
                    recent = sorted(artifacts, key=lambda p: p.stat().st_mtime, reverse=True)[:5]
                    for artifact in recent:
                        size = artifact.stat().st_size
                        print(f"   - {artifact.name} ({size} bytes)")
                
                # Ask for follow-up task
                print("\n" + "="*80)
                print("💬 You can continue with a follow-up task in this session")
                print("   (Type 'exit', 'quit', or 'q' to end the session)")
                print("="*80)
                followup = input("\nEnter follow-up task (or 'exit' to end): ").strip()
                
                if not followup or followup.lower() in ['exit', 'quit', 'q']:
                    print("\n👋 Ending session...")
                    break
                
                task = followup
                is_first_task = False
                
            except KeyboardInterrupt:
                print("\n\n⚠️  Task interrupted by user")
                break
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Always generate final interpretation and close session
        try:
            agent.close_session()
        except Exception as e:
            print(f"⚠️  Error during session close: {e}")
    
    print("\n" + "="*80)
    print("👋 Thank you for using Vision-LLM Web Agent!")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
