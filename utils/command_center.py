import os
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass(frozen=True)
class CommandDef:
    label: str
    cmd: List[str]
    timeout: int = 12

SERVICES: Dict[str, str] = {
    "hapitech": "hapitech",
    "spartanbricklaying": "spartanbricklaying",
    "rolandshandyman": "rolandshandyman",
    "gravemistakegames": "gravemistakegames",
}

SYSTEMCTL = "/bin/systemctl"
JOURNALCTL = "/bin/journalctl"
DU = "/usr/bin/du"
BASH = "/usr/bin/bash"

SAFE_ENV = os.environ.copy()
SAFE_ENV["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

def _systemctl(*args: str) -> List[str]:
    return [SYSTEMCTL, *args]

def _journalctl(service: str, lines: int = 120) -> List[str]:
    return [JOURNALCTL, "-u", service, "-n", str(lines), "--no-pager"]

COMMANDS: Dict[str, CommandDef] = {}

for key, svc in SERVICES.items():
    COMMANDS[f"status_{key}"] = CommandDef(
        label=f"Status: {svc}",
        cmd=_systemctl("status", svc, "--no-pager", "-l"),
        timeout=12,
    )
    COMMANDS[f"logs_{key}"] = CommandDef(
        label=f"Logs: {svc} (last 120)",
        cmd=_journalctl(svc, 120),
        timeout=12,
    )
    COMMANDS[f"restart_{key}"] = CommandDef(
        label=f"Restart: {svc}",
        cmd=_systemctl("restart", svc),
        timeout=20,
    )

COMMANDS["disk_var_www"] = CommandDef(
    label="Disk usage: /var/www",
    cmd=[DU, "-sh", "/var/www"],
    timeout=10,
)

COMMANDS["tree_hapitech_dirs"] = CommandDef(
    label="Project folders: /var/www/ (depth 10)",
    cmd=[BASH, "-c", "cd /var/www/ && find . -maxdepth 10 -type d | sort"],
    timeout=15,
)

def run_command(key: str) -> Tuple[str, int]:
    if key not in COMMANDS:
        return ("Command not allowed.", 127)

    definition = COMMANDS[key]
    try:
        r = subprocess.run(
            definition.cmd,
            capture_output=True,
            text=True,
            timeout=definition.timeout,
            check=False,
            env=SAFE_ENV,
        )
        out = (r.stdout or "")
        err = (r.stderr or "")
        combined = (out + ("\n" + err if err else "")).strip()
        if not combined:
            combined = "(no output)"

        if r.returncode != 0 and definition.cmd and definition.cmd[0].endswith("systemctl") and "restart" in definition.cmd:
            combined += (
                "\n\nNOTE: Restart failed due to permissions. "
                "This will work only if hapitech is running as root or "
                "you add a sudoers NOPASSWD rule for systemctl restart."
            )
        return (combined, r.returncode)
    except subprocess.TimeoutExpired:
        return ("Command timed out.", 124)
    except Exception as e:
        return (f"Error: {e}", 1)

def get_service_state(service_name: str) -> dict:
    """
    Returns a dict with ActiveState/SubState/Result plus a derived 'level':
    green / amber / red
    """
    cmd = [SYSTEMCTL, "show", "-p", "ActiveState", "-p", "SubState", "-p", "Result", service_name]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=6, check=False)

    data = {"service": service_name, "ActiveState": "unknown", "SubState": "unknown", "Result": "unknown"}
    for line in (r.stdout or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if k in data:
                data[k] = v

    active = data["ActiveState"]
    sub = data["SubState"]

    if active == "active" and sub == "running":
        level = "green"
    elif active in ("activating", "reloading") or (active == "active" and sub != "running"):
        level = "amber"
    else:
        level = "red"

    data["level"] = level
    return data
