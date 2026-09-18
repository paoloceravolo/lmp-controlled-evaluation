#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from lmp_real.common import DEFAULT_CONFIG, PROJECT_ROOT, atomic_write_json, dataset_path, find_dataset, load_config
from lmp_real.logs import load_event_table, profile_event_table


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile one configured real-life event log.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = load_config(args.config)
    dataset = find_dataset(config, args.dataset)
    source = dataset_path(config, dataset)
    frame = load_event_table(source, dataset)
    profile = profile_event_table(frame, dataset, source)
    output = PROJECT_ROOT / "results" / "raw" / "profiles" / f"{dataset['id']}.json"
    atomic_write_json(output, profile)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
