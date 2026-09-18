from __future__ import annotations

import hashlib
import math
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any

import pandas as pd
import pm4py


Trace = tuple[str, ...]


def load_event_table(path: Path, dataset: dict[str, Any]) -> pd.DataFrame:
    if path.name.endswith((".xes", ".xes.gz")):
        # XES is the canonical input because it preserves source types and
        # avoids CSV NA/timestamp inference problems.
        frame = pm4py.read_xes(str(path), return_legacy_log_object=False)
    else:
        # `keep_default_na=False` is essential: Sepsis contains a legitimate
        # case identifier equal to the literal string "NA".
        frame = pd.read_csv(path, keep_default_na=False)
    case_id = dataset["case_id"]
    activity = dataset["activity"]
    timestamp = dataset.get("timestamp")
    missing = {case_id, activity}.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing columns {sorted(missing)} in {path}")

    valid = frame[case_id].astype(str).str.strip().ne("") & frame[activity].astype(str).str.strip().ne("")
    frame = frame.loc[valid].copy()
    frame[case_id] = frame[case_id].astype(str)
    frame[activity] = frame[activity].astype(str)
    frame["@@source_order"] = range(len(frame))
    sort_columns = [case_id]
    if timestamp and timestamp in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[timestamp]):
            frame[timestamp] = pd.to_datetime(frame[timestamp], errors="coerce", utc=True)
        else:
            # Pandas 2.x otherwise infers one timestamp shape for the whole
            # column and coerces valid mixed-fractional timestamps to NaT.
            frame[timestamp] = pd.to_datetime(frame[timestamp], format="mixed", errors="coerce", utc=True)
        sort_columns.append(timestamp)
    sort_columns.append("@@source_order")
    return frame.sort_values(sort_columns, kind="stable").reset_index(drop=True)


def variant_counts(frame: pd.DataFrame, dataset: dict[str, Any]) -> Counter[Trace]:
    case_id = dataset["case_id"]
    activity = dataset["activity"]
    counts: Counter[Trace] = Counter()
    for _, case_frame in frame.groupby(case_id, sort=False):
        counts[tuple(case_frame[activity].tolist())] += 1
    return counts


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def profile_event_table(frame: pd.DataFrame, dataset: dict[str, Any], source: Path) -> dict[str, Any]:
    counts = variant_counts(frame, dataset)
    case_lengths = [len(trace) for trace, frequency in counts.items() for _ in range(frequency)]
    variant_lengths = [len(trace) for trace in counts]
    activities = sorted(frame[dataset["activity"]].unique().tolist())
    timestamp = dataset.get("timestamp")
    return {
        "dataset_id": dataset["id"],
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "events": int(len(frame)),
        "cases": int(sum(counts.values())),
        "activities": len(activities),
        "activity_labels": activities,
        "lifecycle_policy": dataset.get("lifecycle_policy"),
        "timestamp_parse_failures": int(frame[timestamp].isna().sum()) if timestamp and timestamp in frame else None,
        "variants": len(counts),
        "case_length_min": min(case_lengths),
        "case_length_median": float(median(case_lengths)),
        "case_length_mean": float(mean(case_lengths)),
        "case_length_p95": _percentile(case_lengths, 0.95),
        "case_length_max": max(case_lengths),
        "variant_length_min": min(variant_lengths),
        "variant_length_median": float(median(variant_lengths)),
        "variant_length_mean": float(mean(variant_lengths)),
        "variant_length_p95": _percentile(variant_lengths, 0.95),
        "variant_length_max": max(variant_lengths),
    }
