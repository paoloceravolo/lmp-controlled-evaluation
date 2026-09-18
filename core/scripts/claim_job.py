#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT, atomic_write_json, read_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Atomically claim one ready experiment job.")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--job-id")
    args = parser.parse_args()

    manifest = PROJECT_ROOT / "work" / "manifests" / f"{args.stage}.jsonl"
    claim_dir = PROJECT_ROOT / "work" / "claims" / args.stage
    completed_dir = PROJECT_ROOT / "work" / "completed" / args.stage
    claim_dir.mkdir(parents=True, exist_ok=True)
    completed_dir.mkdir(parents=True, exist_ok=True)

    for job in read_jsonl(manifest):
        if args.job_id and job["job_id"] != args.job_id:
            continue
        if not job.get("ready", True):
            continue
        if (completed_dir / f"{job['job_id']}.json").exists():
            continue
        claim_path = claim_dir / f"{job['job_id']}.json"
        claim = {
            "job_id": job["job_id"],
            "stage": args.stage,
            "worker_id": args.worker_id,
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            descriptor = os.open(claim_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(claim, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(json.dumps(job, sort_keys=True))
        return 0

    if args.job_id:
        raise SystemExit(f"Job is absent, blocked, completed, or already claimed: {args.job_id}")
    print("NO_READY_UNCLAIMED_JOB")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
