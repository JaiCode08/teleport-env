#!/bin/bash
set -e

echo "======================================"
echo " Setting up Teleport-Env Testbed"
echo "======================================"

echo "1. Cleaning up old container..."
sudo docker rm -f teleport-testbed 2>/dev/null || true

echo "2. Building Docker image..."
sudo docker build -t teleport-testbed-image -f Dockerfile.testbed .

echo "3. Starting privileged container..."
sudo docker run --init -d --name teleport-testbed --privileged \
    --cap-add=SYS_ADMIN --cap-add=CHECKPOINT_RESTORE \
    -v $(pwd):/src teleport-testbed-image sleep infinity

echo "4. Initializing native sandbox mount..."
sudo docker exec teleport-testbed mkdir -p /tmp/sandbox

echo "✅ Setup Complete. You can now run the benchmarks."
