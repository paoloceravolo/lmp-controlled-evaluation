from __future__ import annotations

import hashlib
import itertools
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "experiments.json"


def load_config(path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if config.get("schema_version") != 1:
        raise ValueError(f"Unsupported config schema: {config.get('schema_version')!r}")
    return config


def data_root(config: dict[str, Any]) -> Path:
    override = os.environ.get("LMP_VEXG_DATA_ROOT")
    return Path(override or config["paths"]["vexg_data_root"]).expanduser().resolve()


def dataset_path(config: dict[str, Any], dataset: dict[str, Any]) -> Path:
    return data_root(config) / dataset["path"]


def find_dataset(config: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    for dataset in config["datasets"]:
        if dataset["id"] == dataset_id:
            return dataset
    raise KeyError(f"Unknown dataset: {dataset_id}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_id(prefix: str, value: Any, length: int = 12) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest}"


def grid_product(grid: dict[str, list[Any]]) -> Iterator[dict[str, Any]]:
    if not grid:
        yield {}
        return
    keys = sorted(grid)
    for values in itertools.product(*(grid[key] for key in keys)):
        yield dict(zip(keys, values))


def atomic_write_json(path: Path | str, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_jsonl(path: Path | str, rows: Iterable[dict[str, Any]]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    count = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(canonical_json(row) + "\n")
                count += 1
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return count


def read_jsonl(path: Path | str) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc


def find_job(manifest: Path | str, job_id: str) -> dict[str, Any]:
    for job in read_jsonl(manifest):
        if job["job_id"] == job_id:
            return job
    raise KeyError(f"Job {job_id!r} not found in {manifest}")
