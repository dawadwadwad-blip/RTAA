import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from atomic_output import write_json, write_text


RUNS = Path("reports/runs")
LEDGER = Path("DEV_STATE.md")
BEGIN = "<!-- richmond-run-history:begin -->"
END = "<!-- richmond-run-history:end -->"
LOCK = Path(".task-run.lock")
TASK_ID = re.compile(r"S[0-4]-(?:0[1-9]|[1-9][0-9])")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def run_lock():
    with LOCK.open("a+b") as file:
        if os.name == "nt":
            from msvcrt import LK_NBLCK, locking

            if file.seek(0, os.SEEK_END) == 0:
                file.write(b"\0")
                file.flush()
            while True:
                file.seek(0)
                try:
                    locking(file.fileno(), LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (13, 36):
                        raise
                    time.sleep(0.1)
        else:
            from fcntl import LOCK_EX, flock

            flock(file.fileno(), LOCK_EX)
        yield file.fileno()


def git_status():
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all", "--",
             ".", ":(exclude)DEV_STATE.md", ":(exclude)reports/runs"],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return None


def read_runs():
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(RUNS.glob("*.json"))]


def sync_ledger():
    records = read_runs()
    lines = ["## Current task status", ""]
    latest = {run["task"]: run for run in records}
    for task, run in sorted(latest.items()):
        lines.append(f'- **{task} · {run["status"]}** — {run["next_action"]}')

    lines.extend(["", "## Run history", ""])
    for run in records:
        run_id = run["run_id"]
        start = run["started_at"]
        end = run["finished_at"] or "in progress"
        lines.append(
            f'- `{run_id}` · {run["task"]} · **{run["status"]}** · '
            f'{start} → {end} · [run evidence](reports/runs/{run_id}.json)'
        )
    section = f"{BEGIN}\n" + "\n".join(lines) + f"\n{END}"
    old = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else "# Richmond Open World · Development state\n"
    if BEGIN in old or END in old:
        if old.count(BEGIN) != 1 or old.count(END) != 1:
            raise ValueError(f"Unbalanced generated-history markers in {LEDGER}.")
        prefix, tail = old.split(BEGIN)
        _, suffix = tail.split(END, 1)
        updated = prefix + section + suffix
    else:
        updated = old + ("\n" if old.endswith("\n") else "\n\n") + section + "\n"
    write_text(LEDGER, updated)


def save_run(run):
    write_json(RUNS / f'{run["run_id"]}.json', run)


def recover_interrupted():
    for run in read_runs():
        if run["status"] == "RUNNING":
            run.update(
                status="INTERRUPTED", finished_at=now(), exit_code=None,
                blocker="Previous runner ended without a terminal record.",
                next_action="Review the previous run output and retry the task.",
            )
            save_run(run)


def execute(command, log, lock_fd):
    spawn_options = {"pass_fds": (lock_fd,), "start_new_session": True} if os.name != "nt" else {}
    child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, **spawn_options)
    try:
        return child.wait(), False
    except KeyboardInterrupt:
        if child.poll() is None:
            if os.name == "nt":
                child.terminate()
            else:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        try:
            return child.wait(timeout=5), True
        except subprocess.TimeoutExpired:
            child.kill()
            return child.wait(), True


def run_locked(args, lock_fd):
    recover_interrupted()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    task = args[0] if args and TASK_ID.fullmatch(args[0]) else "invocation"
    command = args[2:] if len(args) >= 3 and args[1] == "--" else []
    if command and command[0] in ("python", "python3"):
        command[0] = sys.executable
    evidence = RUNS / f"{run_id}.log"
    before = git_status()
    run = {
        "task": task, "run_id": run_id, "started_at": now(), "finished_at": None,
        "command": command, "status": "RUNNING", "exit_code": None,
        "log": evidence.as_posix(), "blocker": None, "checks": [],
        "inputs": {option: command[index + 1] for index, option in enumerate(command[:-1])
                   if option in ("--bundle", "--html")},
        "changed_files": [],
        "next_action": "Wait for the command to finish.",
    }
    save_run(run)
    sync_ledger()

    code = 1
    status = "FAILED"
    with evidence.open("w+", encoding="utf-8") as log:
        try:
            if task == "invocation" or not command:
                raise ValueError("Usage: python tools/run_task.py S0-01 -- COMMAND [ARGS ...]")
            code, interrupted = execute(command, log, lock_fd)
            status = "INTERRUPTED" if interrupted else {0: "PASS", 3: "BLOCKED"}.get(code, "FAILED")
        except (OSError, ValueError) as exc:
            print(str(exc), file=log)
        log.seek(0)
        output = log.read()
    changed_files = [LEDGER.as_posix(), evidence.as_posix(), (RUNS / f"{run_id}.json").as_posix()]
    after = git_status()
    if before is not None and after is not None:
        changed_files.extend(line[3:] for line in after if line not in before)
    if status == "PASS" and len(command) >= 2 and "--bundle" in run["inputs"]:
        report_path = Path("reports/baseline.json")
        if report_path.is_file() and Path(command[1]).name == "baseline_inventory.py":
            report = json.loads(report_path.read_text(encoding="utf-8"))
            run["inputs"] = {"bundle": report["bundle"]["sha256"],
                             "html": report["html"]["sha256"] if report["html"] else None}
            changed_files.append(report_path.as_posix())
    checks = [line for line in output.splitlines() if line.startswith(("PASS:", "FAIL:", "Ran ", "OK"))]
    last_line = next((line for line in reversed(output.splitlines()) if line.strip()), None)
    next_action = (
        "Review the evidence and advance to the tasks whose prerequisites are met."
        if status == "PASS" else f"Review {evidence.as_posix()} and retry {shlex.join(command) or 'with a valid command'}."
    )
    run.update(
        status=status, exit_code=code, finished_at=now(), checks=checks,
        changed_files=sorted(set(changed_files)), next_action=next_action,
        blocker=None if status == "PASS" else (last_line or f"Command exited with code {code}."),
    )
    save_run(run)
    sync_ledger()
    print(output, end="")
    print(f"{task} {status} · {evidence.as_posix()}")
    return 130 if status == "INTERRUPTED" else code if code >= 0 else 128 - code


if __name__ == "__main__":
    with run_lock() as fd:
        sys.exit(run_locked(sys.argv[1:], fd))
