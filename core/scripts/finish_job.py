#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT, atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark a claimed job completed or failed.")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--status", choices=["completed", "failed"], required=True)
    parser.add_argument("--artifact")
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    claim = PROJECT_ROOT / "work" / "claims" / args.stage / f"{args.job_id}.json"
    if not claim.exists():
        raise SystemExit(f"No claim exists for {args.job_id}")
    result = {
        "job_id": args.job_id,
        "stage": args.stage,
        "worker_id": args.worker_id,
        "status": args.status,
        "artifact": args.artifact,
        "message": args.message,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    destination = PROJECT_ROOT / "work" / "completed" / args.stage / f"{args.job_id}.json"
    atomic_write_json(destination, result)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
