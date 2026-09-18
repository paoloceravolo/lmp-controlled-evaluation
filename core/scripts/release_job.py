#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT, atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Release an infrastructure-failed claim for a controlled retry.")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    claim = PROJECT_ROOT / "work" / "claims" / args.stage / f"{args.job_id}.json"
    completion = PROJECT_ROOT / "work" / "completed" / args.stage / f"{args.job_id}.json"
    if not claim.exists():
        raise SystemExit(f"No claim exists for {args.job_id}")
    with claim.open(encoding="utf-8") as handle:
        claim_record = json.load(handle)
    if claim_record.get("worker_id") != args.worker_id:
        raise SystemExit(f"Claim belongs to {claim_record.get('worker_id')!r}, not {args.worker_id!r}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    history = PROJECT_ROOT / "work" / "history" / args.stage / f"{args.job_id}-{stamp}"
    history.mkdir(parents=True, exist_ok=False)
    claim.replace(history / "claim.json")
    if completion.exists():
        completion.replace(history / "completion.json")
    atomic_write_json(
        history / "release.json",
        {
            "job_id": args.job_id,
            "stage": args.stage,
            "worker_id": args.worker_id,
            "reason": args.reason,
            "released_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(history)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
