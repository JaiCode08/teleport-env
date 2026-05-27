import os
import subprocess
import json
import time

class TeleportSandbox:
    def __init__(self, container_name="teleport-testbed", base_dir="/sandbox"):
        self.container_name = container_name
        self.base_dir = base_dir
        self.ledger_file = "ledger.json"
        self.ledger = {"snapshots": [], "lowerdirs": [f"{self.base_dir}/base_lower"]}
        self.pid = None

    def _exec(self, cmd_list, check=True, bg=False):
        if self.container_name:
            full_cmd = ["docker", "exec"]
            if bg:
                full_cmd.append("-d")
            full_cmd += [self.container_name] + cmd_list
        else:
            full_cmd = cmd_list
            
        result = subprocess.run(full_cmd, capture_output=not bg, text=True)
        if check and result.returncode != 0:
            raise RuntimeError(f"Command failed: {full_cmd}\nStdout: {result.stdout}\nStderr: {result.stderr}")
        return result

    def _save_ledger(self):
        with open(self.ledger_file, "w") as f:
            json.dump(self.ledger, f, indent=2)

    def _load_ledger(self):
        if os.path.exists(self.ledger_file):
            with open(self.ledger_file, "r") as f:
                self.ledger = json.load(f)

    def setup_overlayfs(self):
        # unmount if mounted (ignore errors if not mounted)
        self._exec(["umount", f"{self.base_dir}/merged"], check=False)
        
        # Ensure base_dir is a tmpfs to allow overlayfs upperdir (since Docker root is overlayfs)
        res = self._exec(["mount"], check=False)
        if f"on {self.base_dir} type tmpfs" not in res.stdout:
            self._exec(["mount", "-t", "tmpfs", "tmpfs", self.base_dir], check=False)
        
        # wipe and recreate directories
        dirs_to_clean = ["upperdir", "workdir", "merged", "base_lower", "snapshots"]
        for d in dirs_to_clean:
            self._exec(["rm", "-rf", f"{self.base_dir}/{d}"])
            self._exec(["mkdir", "-p", f"{self.base_dir}/{d}"])
            
        self.ledger = {"snapshots": [], "lowerdirs": [f"{self.base_dir}/base_lower"]}
        self._save_ledger()

    def _mount_overlay(self):
        lower_str = ":".join(self.ledger["lowerdirs"])
        self._exec([
            "mount", "-t", "overlay", "overlay", 
            "-o", f"lowerdir={lower_str},upperdir={self.base_dir}/upperdir,workdir={self.base_dir}/workdir", 
            f"{self.base_dir}/merged"
        ])

    def start_app(self, script_path_on_host):
        """Starts a python script inside the sandbox"""
        self.setup_overlayfs()
        filename = os.path.basename(script_path_on_host)
        
        # Copy script into container base layer
        if self.container_name:
            subprocess.run(["docker", "cp", script_path_on_host, f"{self.container_name}:/tmp/{filename}"], check=True)
            self._exec(["mv", f"/tmp/{filename}", f"{self.base_dir}/base_lower/{filename}"])
        else:
            self._exec(["cp", script_path_on_host, f"{self.base_dir}/base_lower/{filename}"])
        
        # Copy the script to base_dir so it is outside the overlayfs
        self._exec(["cp", f"{self.base_dir}/base_lower/{filename}", f"{self.base_dir}/app.py"])
        
        # Mount overlay after copying to lowerdir
        self._mount_overlay()
        
        # Start the app as a detached session, redirecting output
        self._exec(["sh", "-c", f"cd {self.base_dir}/merged && (setsid python3 {self.base_dir}/app.py > {self.base_dir}/merged/app.log 2>&1 &)"])
        time.sleep(1) # wait for process to start
        
        # Retrieve its PID
        res = self._exec(["pgrep", "-f", f"python3 {self.base_dir}/app.py"])
        self.pid = res.stdout.strip().split("\n")[0]
        if not self.pid:
            raise RuntimeError("Failed to start app or retrieve its PID")
        print(f"App started with PID: {self.pid}")

    def checkpoint(self, snap_id):
        img_dir = f"{self.base_dir}/snapshots/{snap_id}"
        archive_upper = f"{self.base_dir}/upperdir_{snap_id}"
        
        self._exec(["mkdir", "-p", img_dir])
        
        # 1. Freeze
        self._exec(["sh", "-c", f"cd {self.base_dir} && criu dump --tree {self.pid} --images-dir {img_dir} --shell-job --ext-unix-sk"])
        
        # 2. Rotate Layers
        self._exec(["umount", f"{self.base_dir}/merged"])
        self._exec(["mv", f"{self.base_dir}/upperdir", archive_upper])
        self._exec(["mkdir", "-p", f"{self.base_dir}/upperdir", f"{self.base_dir}/workdir"])
        self.ledger["lowerdirs"].insert(0, archive_upper)
        self._mount_overlay()
        
        self.ledger["snapshots"].append({
            "id": snap_id,
            "image_dir": img_dir,
            "archive_upperdir": archive_upper
        })
        self._save_ledger()
        
        # 4. Resume
        self._exec(["sh", "-c", f"cd {self.base_dir} && criu restore --images-dir {img_dir} --shell-job --ext-unix-sk -d"])
        return snap_id

    def rollback(self, snap_id):
        # Find snapshot index
        idx = next((i for i, s in enumerate(self.ledger["snapshots"]) if s["id"] == snap_id), None)
        if idx is None:
            raise ValueError(f"Snapshot {snap_id} not found")
            
        snap = self.ledger["snapshots"][idx]
        
        # 1. Kill current process
        self._exec(["kill", "-9", str(self.pid)], check=False)
        time.sleep(0.1) # Let it die
        
        # Unmount overlayfs
        self._exec(["umount", f"{self.base_dir}/merged"], check=False)
        
        # Wipe current upperdir and workdir
        self._exec(["rm", "-rf", f"{self.base_dir}/upperdir", f"{self.base_dir}/workdir"])
        self._exec(["mkdir", "-p", f"{self.base_dir}/upperdir", f"{self.base_dir}/workdir"])
        
        # Reconstruct lowerdirs based on remaining snapshots
        self.ledger["snapshots"] = self.ledger["snapshots"][:idx+1]
        self.ledger["lowerdirs"] = [s["archive_upperdir"] for s in reversed(self.ledger["snapshots"])] + [f"{self.base_dir}/base_lower"]
        
        # Copy the archived upperdir content into the fresh upperdir to restore the EXACT active state
        self._exec(["cp", "-a", f"{snap['archive_upperdir']}/.", f"{self.base_dir}/upperdir/"])
        
        # Remount overlayfs
        self._mount_overlay()
        
        # 4. Resume
        self._exec(["sh", "-c", f"cd {self.base_dir} && criu restore --images-dir {snap['image_dir']} --shell-job --ext-unix-sk -d"])

        print(f"Successfully rolled back to {snap_id}")
