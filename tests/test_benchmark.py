import os
import time
import sys

# Ensure teleport_env is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from teleport_env.core import TeleportSandbox

def test_mcts_rollback():
    sandbox = TeleportSandbox(base_dir="/tmp/sandbox", container_name=None)
    
    print("Starting Sandbox App...")
    sandbox.start_app(os.path.abspath(os.path.join(os.path.dirname(__file__), "counter_server.py")))
    
    time.sleep(2) # Wait for it to initialize and create file
    
    print("Taking Checkpoint...")
    sandbox.checkpoint("snap_1")
    
    print("Executing Destructive Action (rm)...")
    sandbox._exec(["rm", "-f", f"{sandbox.base_dir}/merged/count.txt"])
    
    time.sleep(1.5) # Let the server encounter the error
    
    print("Rolling back...")
    t0 = time.perf_counter()
    sandbox.rollback("snap_1")
    t1 = time.perf_counter()
    
    latency_ms = (t1 - t0) * 1000
    print(f"Rollback latency: {latency_ms:.2f} ms")
    
    time.sleep(1.5) # Let the server recover and print count again
    
    # Verify state rolled back
    res = sandbox._exec(["cat", f"{sandbox.base_dir}/merged/app.log"])
    log_content = res.stdout
    
    print("\n--- App Log ---")
    print(log_content)
    print("---------------")
    
    assert "Count: 3" in log_content, "Server did not resume counting"
    assert "Count: 4" in log_content, "Server did not continue counting after rollback"
    
    print(f"SUCCESS! Teleport-env rollback completed in {latency_ms:.2f} ms and verified.")
    
    # Write benchmark results
    with open("benchmark_results.txt", "w") as f:
        f.write("Teleport-Env Benchmark Results\n")
        f.write("==============================\n")
        f.write(f"Rollback Latency: {latency_ms:.2f} ms\n")
        f.write("Status: SUCCESS\n")
        f.write("Note: Standard Docker restart latency is typically > 3000 ms.\n")

if __name__ == "__main__":
    test_mcts_rollback()
