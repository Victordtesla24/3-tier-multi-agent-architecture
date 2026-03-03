import os
import sys
from pathlib import Path

# Ensure the src directory is in the path for standalone execution
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from engine.crew_orchestrator import CrewAIThreeTierOrchestrator

def main():
    """
    A standalone example of executing the 3-Tier Multi-Agent Architecture
    without using the Antigravity CLI.
    """
    # 1. Define the workspace directory where logs and temporary files will be stored.
    workspace_dir = str(Path(__file__).parent.parent.parent.resolve())
    
    # 2. Check if API keys are set (At least Google Gemini and OpenAI are required)
    if not os.environ.get("GOOGLE_API_KEY") or not os.environ.get("OPENAI_API_KEY"):
        print("Error: GOOGLE_API_KEY and OPENAI_API_KEY must be set in the environment or .env file.")
        print("Please configure them in the .env file in the repository root.")
        return
        
    print("Initializing CrewAI 3-Tier Orchestrator...")
    orchestrator = CrewAIThreeTierOrchestrator(workspace_dir=workspace_dir, verbose=True)
    
    # 3. Define the objective
    objective = """
    <input_data>
    Create a standalone Python script that fetches the current time from a public API, 
    parses the JSON response, and prints the result gracefully. Ensure the code handles 
    rate limits and network errors properly.
    </input_data>
    """
    
    print("\n--- Phase 1: Reconstructing Prompt ---")
    reconstructed = orchestrator.reconstruct_prompt(objective)
    
    print("\n--- Phase 2: Orchestrating Research & Execution ---")
    # Generate technical constraints using the analytical agents
    research_ctx = orchestrator.run_research(reconstructed)
    
    # Delegate to the full 3-tier hierarchy
    final_output = orchestrator.execute(reconstructed, research_ctx)
    
    print("\n\n================= FINAL EXECUTED PAYLOAD =================")
    print(final_output)

if __name__ == "__main__":
    main()
