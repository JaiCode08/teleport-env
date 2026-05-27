# Teleport-Env

An ultra-fast, OS-level snapshot and rollback sandbox designed for autonomous coding agents, Monte Carlo Tree Search (MCTS), and reinforcement learning.

## 1. The Problem
Coding agents need environments to test generated bash commands and scripts. However, standard Docker containers take **3 to 5 seconds** to restart when an agent inevitably destroys the filesystem or corrupts a background process. This high latency makes it impossible to run high-throughput MCTS search loops or deep reinforcement learning across thousands of branches.

## 2. Inspiration
`Teleport-Env` is directly inspired by **DeltaBox** (*"DeltaBox: A Fast File-System Rollback Facility for Destructive Agentic Testing"*). DeltaBox proposed a sub-millisecond rollback mechanism using a customized kernel module. We bring that exact architecture to standard Linux distributions entirely in userspace using `overlayfs` and `CRIU`.

## 3. How it Works
We utilize a **Cold Layer Switch** architecture to bypass naive file copying completely:
1. **The Sandbox (OverlayFS)**: The agent's workspace runs inside an `overlayfs` mount with a read-only `lowerdir` and a volatile `upperdir`.
2. **The Checkpoint (CRIU)**: When taking a snapshot, we use Checkpoint/Restore In Userspace (CRIU) to dump the exact memory state, file descriptors, and PID tree of the running Python application into a binary image, while rotating the `upperdir` into the read-only stack.
3. **The Rollback**: If an agent corrupts the environment, we instantly SIGKILL the process, wipe the volatile `upperdir`, and inject the CRIU memory image back into the kernel. The application resumes from the exact millisecond the snapshot was taken, with a pristine filesystem.

*(Note: Because CRIU requires specific kernel capabilities like `CONFIG_CHECKPOINT_RESTORE`, `teleport-env` uses Canonical Multipass to run on a native Ubuntu kernel, bypassing Windows WSL2 limitations).*

## 4. Project Structure
```text
teleport-env/
├── teleport_env/            # Core library
│   └── core.py              # TeleportSandbox & CRIU/OverlayFS orchestrator
├── tests/                   # Testing Suite
│   ├── counter_server.py    # Background Python app for memory snapshots
│   ├── test_benchmark.py    # Destructive rollback latency benchmark
│   └── test_mcts_agent.py   # Autonomous OpenRouter + Qwen agent loop
├── logs/                    # Automated testing output
├── setup.sh                 # Docker image build & Multipass container init
├── run_benchmarks.sh        # Automated sandbox wipe & test runner
├── Dockerfile.testbed       # Container configured with bleeding-edge CRIU
└── .env                     # Local environment keys (e.g. OPENROUTER_KEY)
```

## 5. Setup & Environment

Because CRIU requires advanced kernel capabilities (specifically `CONFIG_CHECKPOINT_RESTORE` and `PTRACE_O_SUSPEND_SECCOMP`), the execution environment dictates the setup process.

### Native Linux (Ubuntu/Debian)
If you are running natively on a Linux host that supports these kernel features, you do not need virtualization. You can execute the testbed directly using Docker:

1. Clone the repository and configure your OpenRouter key:
   ```bash
   echo 'OPENROUTER_KEY="sk-or-v1-..."' > .env
   ```
2. Initialize the Docker sandbox and build the CRIU binaries:
   ```bash
   sudo bash setup.sh
   ```
3. Run the benchmarking and MCTS test suites:
   ```bash
   sudo bash run_benchmarks.sh
   ```

### Windows / macOS (Virtualization Required)
**Standard Windows WSL2 and Docker Desktop environments will fail** because they strip the necessary CRIU kernel capabilities. To bypass this, `teleport-env` must be tested within a native Ubuntu environment using **Canonical Multipass**.

1. Install Multipass:
   ```powershell
   # Windows
   winget install Canonical.Multipass
   
   # macOS
   brew install --cask multipass
   ```
2. Launch a native Ubuntu VM:
   ```powershell
   multipass launch 24.04 --name teleport-vm --cpus 4 --memory 8G --disk 20G
   ```
3. Mount this project directory into the VM:
   ```powershell
   multipass mount . teleport-vm:/home/ubuntu/teleport-env
   ```
4. Execute the automated scripts directly from your host machine via `multipass exec`:
   ```powershell
   # 1. Install Docker, build the testbed, and initialize the sandbox mounts
   multipass exec teleport-vm -- bash /home/ubuntu/teleport-env/setup.sh
   
   # 2. Run the benchmarking and MCTS test suites
   multipass exec teleport-vm -- bash /home/ubuntu/teleport-env/run_benchmarks.sh
   ```

## 6. Results
By executing tests completely natively inside the container (eliminating Docker networking overhead), `teleport-env` consistently achieves **< 500ms** full-state recovery (Filesystem + Memory), effectively running **~10x faster** than a standard container reboot. 

During our live MCTS testing with the `qwen-2.5-coder-32b-instruct` model, the environment correctly intercepted destructive `sed` globbing commands, evaluated the negative reward, and perfectly restored the corrupted environment in **466.33 ms** to allow the agent to succeed on its next branch.

## License
MIT License
