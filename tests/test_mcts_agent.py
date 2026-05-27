import os
import time
from openai import OpenAI
import subprocess
import sys

from dotenv import load_dotenv

# Ensure teleport_env is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from teleport_env.core import TeleportSandbox 

# Load environment variables from /src/.env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Initialize OpenRouter Client
api_key = os.environ.get("OPENROUTER_KEY")
if not api_key:
    api_key = os.environ.get("OPENROUTER_API_KEY")

if not api_key:
    raise ValueError("OPENROUTER_KEY environment variable not set!")

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=api_key,
)
MODEL = "qwen/qwen-2.5-coder-32b-instruct"

def generate_n_solutions(prompt: str, n: int = 3) -> list[str]:
    print(f"🧠 Generating {n} candidate actions via OpenRouter...")
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a coding agent executing inside a Linux terminal. Return ONLY valid bash commands to execute. Do not use markdown blocks, backticks, or explanations. Just the raw command text."},
            {"role": "user", "content": prompt}
        ],
        n=n,
        temperature=0.7 
    )
    return [choice.message.content.strip().replace("```bash", "").replace("```", "") for choice in response.choices]

def evaluate_state(sandbox) -> bool:
    # Check 1: Did config1.json get updated to v2?
    res1 = sandbox._exec(["sh", "-c", f"cd {sandbox.base_dir}/merged && grep -q '\"api_version\": \"v2\"' config1.json"], check=False)
    
    # Check 2: Was ignore_me.txt left completely untouched (still v1)?
    res2 = sandbox._exec(["sh", "-c", f"cd {sandbox.base_dir}/merged && grep -q '\"api_version\": \"v1\"' ignore_me.txt"], check=False)
    
    # Check 3: Did the agent accidentally delete the file contents with a bad sed redirect?
    res3 = sandbox._exec(["sh", "-c", f"cd {sandbox.base_dir}/merged && cat config1.json"], check=False)
    
    if res1.returncode == 0 and res2.returncode == 0 and "name" in res3.stdout:
        return True
    return False

def run_mcts_loop():
    print("🚀 Booting MCTS Agent with Teleport-Env...")
    
    # We run natively inside the container to get true millisecond latency
    sandbox = TeleportSandbox(base_dir="/tmp/sandbox", container_name=None)
    
    print("Starting background process for CRIU state...")
    sandbox.start_app(os.path.abspath(os.path.join(os.path.dirname(__file__), "counter_server.py")))
    time.sleep(2)
    
    print("📦 Setting up the 'sed' trap state...")
    setup_cmd = """
    echo '{"api_version": "v1", "name": "A"}' > config1.json && \
    echo '{"api_version": "v1", "name": "B"}' > config2.json && \
    echo '{"api_version": "v1", "name": "C"}' > ignore_me.txt
    """
    sandbox._exec(["sh", "-c", f"cd {sandbox.base_dir}/merged && {setup_cmd}"])

    print("⏱️ Taking Checkpoint...")
    checkpoint_id = sandbox.checkpoint("mcts_base")
    
    task_prompt = "Use a single bash command (like find and sed) to change '\"api_version\": \"v1\"' to '\"api_version\": \"v2\"' ONLY in the .json files in the current directory. Do not modify any .txt files. Return ONLY the raw bash command, no explanations."
    
    candidates = generate_n_solutions(task_prompt, n=3)
    
    # Inject a guaranteed failure as the first branch to demonstrate rollback capabilities
    candidates.insert(0, "sed -i 's/v1/v2/g' *")
    
    success = False
    for i, action in enumerate(candidates):
        print(f"\n--- 🌿 Branch {i+1} ---")
        print(f"Executing: {action}")
        
        sandbox._exec(["sh", "-c", f"cd {sandbox.base_dir}/merged && {action}"], check=False)
        
        if evaluate_state(sandbox):
            print("✅ Reward: Positive. Action succeeded!")
            success = True
            break 
        else:
            print("❌ Reward: Negative. State corrupted.")
            print(f"⏪ Rolling back to {checkpoint_id}...")
            start_time = time.perf_counter()
            sandbox.rollback(checkpoint_id)
            end_time = time.perf_counter()
            print(f"⚡ Rollback completed in {(end_time - start_time) * 1000:.2f} ms")

    if success:
        print("\n🏆 Target Reached. Final state is clean.")
    else:
        print("\n💀 All branches failed.")

if __name__ == "__main__":
    run_mcts_loop()
