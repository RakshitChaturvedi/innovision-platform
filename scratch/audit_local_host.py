import os
import sys
import json
import shutil
import socket
import subprocess
import hashlib
import psutil

audit_results = {}

# 1. GIT STATUS
def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return res.stdout.strip(), res.stderr.strip(), res.returncode
    except Exception as e:
        return "", str(e), -1

branch, _, _ = run_cmd(["git", "branch", "--show-current"])
commit_hash, _, _ = run_cmd(["git", "rev-parse", "HEAD"])
commit_log, _, _ = run_cmd(["git", "log", "-n", "3", "--oneline"])
status_out, _, _ = run_cmd(["git", "status", "--porcelain"])
remote_out, _, _ = run_cmd(["git", "remote", "-v"])
status_verbose, _, _ = run_cmd(["git", "status"])

audit_results["git"] = {
    "branch": branch,
    "head_commit": commit_hash,
    "recent_commits": commit_log.splitlines(),
    "is_clean": len(status_out.strip()) == 0,
    "uncommitted_files": status_out.splitlines(),
    "remote": remote_out.splitlines(),
    "status_summary": status_verbose.splitlines()[:5],
}

# 2. RUNTIME BINARIES & SYSTEM
def get_version(cmd):
    out, err, code = run_cmd(cmd)
    return out if code == 0 else err

audit_results["binaries"] = {
    "python": sys.version,
    "node": get_version(["node", "--version"]),
    "npm": get_version(["npm", "--version"]),
    "docker_path": shutil.which("docker"),
    "docker_version": get_version(["docker", "--version"]),
    "psql_path": shutil.which("psql"),
    "redis_server_path": shutil.which("redis-server"),
}

# Check Docker Daemon
docker_info_out, docker_info_err, docker_code = run_cmd(["docker", "info"])
audit_results["docker_daemon"] = {
    "running": docker_code == 0,
    "error": docker_info_err if docker_code != 0 else "None",
}

# 3. NETWORK PORTS CHECK
target_ports = {
    8020: "Ingestion / Stream Gateway",
    8021: "UC1 Intrusion Detection",
    8022: "UC2 Fire/Sparks Detection",
    8023: "UC3 PPE Compliance",
    8024: "UC4 Traffic & ANPR",
    5173: "Vite Dashboard Frontend",
    5432: "PostgreSQL Standard Port",
    5433: "PostgreSQL Innovision Compose Port",
    6379: "Redis Streams Broker",
    9000: "MinIO S3 Storage",
    8554: "MediaMTX RTSP Server",
}

ports_status = {}
for port, desc in target_ports.items():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.4)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()
    ports_status[port] = {
        "description": desc,
        "is_open": result == 0,
    }
audit_results["ports"] = ports_status

# 4. ACTIVE PROCESSES
active_app_procs = []
for p in psutil.process_iter(["pid", "name", "cmdline"]):
    try:
        cmdline = " ".join(p.info.get("cmdline") or [])
        name = p.info.get("name") or ""
        if any(k in cmdline.lower() or k in name.lower() for k in ["uvicorn", "vite", "innovision", "python", "node", "postgres", "redis", "docker"]):
            # filter out unrelated system python if any
            if "innovision" in cmdline.lower() or "5173" in cmdline or any(str(pt) in cmdline for pt in [8020, 8021, 8022, 8023, 8024]):
                active_app_procs.append({
                    "pid": p.info["pid"],
                    "name": name,
                    "cmdline": cmdline[:150],
                })
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
audit_results["active_processes"] = active_app_procs

# 5. MODEL WEIGHTS & ASSETS VERIFICATION
models_to_check = [
    ("yolov8n.pt", "UC1 / Base Checkpoint"),
    ("stubs/uc2_stub/cv_engine/models/best.pt", "UC2 Fire/Sparks Checkpoint"),
    ("services/uc3/models/best.pt", "UC3 PPE Compliance Checkpoint"),
    ("yolo11n.pt", "UC4 Vehicle Checkpoint"),
]

model_status = {}
for rel_path, desc in models_to_check:
    full_path = os.path.abspath(rel_path)
    exists = os.path.exists(full_path)
    file_size = os.path.getsize(full_path) if exists else 0
    sha256 = ""
    if exists:
        h = hashlib.sha256()
        with open(full_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        sha256 = h.hexdigest()[:16]
    model_status[rel_path] = {
        "description": desc,
        "exists": exists,
        "size_bytes": file_size,
        "sha256_short": sha256,
    }
audit_results["models"] = model_status

# 6. TEST MEDIA VERIFICATION
test_media_to_check = [
    "test_data/videos/uc2.mp4",
    "test_data/videos/uc4.mp4",
    "services/uc3/sample_worker.jpg",
    "services/dashboard/public/test_media/uc1.jpg",
    "services/dashboard/public/test_media/uc2_portrait.jpg",
    "services/dashboard/public/test_media/uc3.jpg",
    "services/dashboard/public/test_media/uc4_landscape.jpg",
    "services/dashboard/public/test_media/blank.jpg",
]

media_status = {}
for m in test_media_to_check:
    full = os.path.abspath(m)
    exists = os.path.exists(full)
    size = os.path.getsize(full) if exists else 0
    media_status[m] = {"exists": exists, "size_bytes": size}
audit_results["test_media"] = media_status

with open("scratch/local_host_audit_summary.json", "w") as f:
    json.dump(audit_results, f, indent=2)

print("AUDIT BASELINE COMPLETE: scratch/local_host_audit_summary.json written.")
