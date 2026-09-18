#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from lmp_real.common import DEFAULT_CONFIG, PROJECT_ROOT, data_root, dataset_path, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the LMP real-log experiment environment.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = load_config(args.config)
    checks: list[dict[str, object]] = []

    for module in ["pm4py", "pandas", "scipy", "numpy", "psutil"]:
        try:
            loaded = importlib.import_module(module)
            checks.append({"check": f"python:{module}", "ok": True, "version": getattr(loaded, "__version__", "unknown")})
        except Exception as exc:
            checks.append({"check": f"python:{module}", "ok": False, "detail": str(exc)})

    checks.append({"check": "executable:java", "ok": shutil.which("java") is not None, "required_now": False})
    checks.append({"check": "data_root", "ok": data_root(config).is_dir(), "path": str(data_root(config))})
    for dataset in config["datasets"]:
        path = dataset_path(config, dataset)
        checks.append({"check": f"dataset:{dataset['id']}", "ok": path.is_file(), "path": str(path)})

    entropia = PROJECT_ROOT / config["paths"]["entropia_jar"]
    split_miner = PROJECT_ROOT / config["paths"]["split_miner_adapter"]
    checks.append({"check": "external:entropia", "ok": entropia.is_file(), "path": str(entropia), "required_now": False})
    checks.append({"check": "external:split_miner", "ok": split_miner.is_file(), "path": str(split_miner), "required_now": False})

    print(json.dumps(checks, indent=2))
    required_failures = [item for item in checks if not item["ok"] and item.get("required_now", True)]
    return 1 if required_failures else 0


if __name__ == "__main__":
    sys.exit(main())
