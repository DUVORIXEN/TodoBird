#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import hashlib
from pathlib import Path


SUMMARY_RE = re.compile(
    r"(?P<count>\d+)\s+"
    r"(?P<kind>passed|failed|error|errors|skipped|xfailed|xpassed)"
)
RSS_RE = re.compile(r"Maximum resident set size \(kbytes\):\s*(?P<rss>\d+)")


def _parse_counts(output: str) -> dict[str, int]:
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
    }
    for match in SUMMARY_RE.finditer(output):
        kind = match.group("kind")
        if kind == "error":
            kind = "errors"
        counts[kind] += int(match.group("count"))
    return counts


def _parse_rss(output: str) -> int:
    matches = list(RSS_RE.finditer(output))
    return int(matches[-1].group("rss")) if matches else 0

def _hash_file(path: Path) -> str:
    """Returns SHA256 hash of a file or '<missing>' if it doesn't exist."""
    if not path.exists():
        return "<missing>"
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def _get_protected_hashes(root: Path) -> dict[Path, str]:
    db_path = root / "todo_bird_app" / "data" / "todo_bird.db"
    config_path = root / "todo_bird_app" / "config" / "config.json"
    return {
        db_path: _hash_file(db_path),
        config_path: _hash_file(config_path)
    }


def _test_files(root: Path, requested: list[str]) -> list[Path]:
    if requested:
        return [Path(item).resolve() if Path(item).is_absolute() else root / item for item in requested]
    return sorted((root / "todo_bird_app" / "tests").glob("test_*.py"))


def _command(timeout_seconds: int, rel_path: Path) -> list[str]:
    timeout_bin = shutil.which("timeout")
    time_bin = "/usr/bin/time" if Path("/usr/bin/time").exists() else shutil.which("time")
    pytest_cmd = [
        sys.executable,
        "-X",
        "faulthandler",
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        str(rel_path),
    ]
    if timeout_bin:
        pytest_cmd = [timeout_bin, str(timeout_seconds), *pytest_cmd]
    if time_bin:
        pytest_cmd = [time_bin, "-v", *pytest_cmd]
    return pytest_cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Todo Bird pytest files in fresh subprocesses with per-file RSS reporting."
    )
    parser.add_argument("tests", nargs="*", help="Optional test files. Defaults to all todo_bird_app/tests/test_*.py.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--timeout", type=int, default=140, help="Per-file timeout in seconds.")
    parser.add_argument(
        "--summary",
        default="build/test_reports/isolated_pytest_summary.json",
        help="Summary JSON path, relative to --root unless absolute.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files = _test_files(root, args.tests)
    summary_path = Path(args.summary)
    if not summary_path.is_absolute():
        summary_path = root / summary_path
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    totals = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
    }
    results = []
    peak_rss = 0
    started = time.time()

    print(f"isolated pytest files={len(files)} timeout={args.timeout}s", flush=True)
    for index, path in enumerate(files, start=1):
        rel_path = path.relative_to(root) if path.is_absolute() else path
        print(f"[{index}/{len(files)}] {rel_path}", flush=True)
        
        pre_hashes = _get_protected_hashes(root)
        
        file_started = time.time()
        try:
            proc = subprocess.run(
                _command(args.timeout, rel_path),
                cwd=str(root),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=args.timeout + 15,
            )
            returncode = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            returncode = 124
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            
        elapsed = time.time() - file_started
        combined = f"{stdout}\n{stderr}"
        counts = _parse_counts(combined)
        rss = _parse_rss(combined)
        peak_rss = max(peak_rss, rss)
        for key, value in counts.items():
            totals[key] += value

        # Check protected files
        post_hashes = _get_protected_hashes(root)
        protected_changed = False
        for p, pre_hash in pre_hashes.items():
            post_hash = post_hashes[p]
            if pre_hash != post_hash:
                protected_changed = True
                print(f"CRITICAL: Protected file mutated: {p}", flush=True)
                print(f"  Before: {pre_hash}", flush=True)
                print(f"  After:  {post_hash}", flush=True)
                
        if protected_changed:
            returncode = 1
            status = "failed_mutation"
        else:
            status = "passed" if returncode == 0 else "timeout" if returncode == 124 else "failed"
            
        result = {
            "file": str(rel_path),
            "status": status,
            "returncode": returncode,
            "elapsed_seconds": round(elapsed, 3),
            "max_rss_kb": rss,
            "counts": counts,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
        }
        results.append(result)
        print(
            f"  {status} rc={returncode} passed={counts['passed']} "
            f"failed={counts['failed']} errors={counts['errors']} "
            f"skipped={counts['skipped']} rss_kb={rss} elapsed={elapsed:.1f}s",
            flush=True,
        )

        if returncode != 0:
            print(stdout[-4000:], flush=True)
            print(stderr[-4000:], flush=True)
            break

    passed = len(results) == len(files) and all(item["returncode"] == 0 for item in results)
    summary = {
        "root": str(root),
        "file_count": len(files),
        "completed_files": len(results),
        "status": "passed" if passed else "failed",
        "elapsed_seconds": round(time.time() - started, 3),
        "peak_rss_kb": peak_rss,
        "totals": totals,
        "results": results,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"summary={summary_path}", flush=True)
    print(
        f"TOTAL status={summary['status']} files={summary['completed_files']}/{summary['file_count']} "
        f"passed={totals['passed']} failed={totals['failed']} errors={totals['errors']} "
        f"skipped={totals['skipped']} xfailed={totals['xfailed']} xpassed={totals['xpassed']} "
        f"peak_rss_kb={peak_rss} elapsed={summary['elapsed_seconds']}s",
        flush=True,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
