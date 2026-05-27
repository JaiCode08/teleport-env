#!/bin/bash
set -e

echo "======================================"
echo " Running Teleport-Env Benchmarks"
echo "======================================"

# Create the logs directory on the host if it doesn't exist
mkdir -p /home/ubuntu/teleport-env/logs

echo "--------------------------------------"
echo "[1/2] Running Benchmark Latency Test"
echo "--------------------------------------"
# Safely wipe sandbox by killing dangling apps and unmounting first
sudo docker exec teleport-testbed pkill -9 -f python || true
sudo docker exec teleport-testbed umount /tmp/sandbox/merged 2>/dev/null || true
sudo docker exec teleport-testbed rm -rf /tmp/sandbox 2>/dev/null || true
sudo docker exec teleport-testbed mkdir -p /tmp/sandbox

sudo docker exec -e PYTHONPATH=/src teleport-testbed python3 /src/tests/test_benchmark.py > /home/ubuntu/teleport-env/logs/benchmark.log 2>&1
echo "✅ Benchmark complete. Log saved to logs/benchmark.log"

echo "--------------------------------------"
echo "[2/2] Running Autonomous MCTS Test"
echo "--------------------------------------"
# Safely wipe sandbox by killing dangling apps and unmounting first
sudo docker exec teleport-testbed pkill -9 -f python || true
sudo docker exec teleport-testbed umount /tmp/sandbox/merged 2>/dev/null || true
sudo docker exec teleport-testbed rm -rf /tmp/sandbox 2>/dev/null || true
sudo docker exec teleport-testbed mkdir -p /tmp/sandbox

sudo docker exec -e PYTHONPATH=/src teleport-testbed python3 /src/tests/test_mcts_agent.py > /home/ubuntu/teleport-env/logs/mcts_agent.log 2>&1
echo "✅ MCTS test complete. Log saved to logs/mcts_agent.log"

echo "======================================"
echo " All tests finished!"
echo "======================================"
