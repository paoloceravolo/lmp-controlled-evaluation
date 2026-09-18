#!/usr/bin/env bash
# Fetches the three public event logs used in the paper's real-log evaluation
# and checks them against checksums.sha256. Safe to re-run.
set -euo pipefail

TARGET_ROOT="${1:-raw}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$TARGET_ROOT/road_fines" "$TARGET_ROOT/sepsis" "$TARGET_ROOT/bpi_2012"

fetch() {
  local doi="$1" out="$2"
  if [ -f "$out" ]; then
    echo "already present: $out"
    return
  fi
  echo "fetching $doi -> $out"
  curl -L --fail "https://doi.org/${doi}" -o "$out"
}

fetch "10.4121/uuid:270fd440-1057-4fb9-89a9-b699b47990f5" \
  "$TARGET_ROOT/road_fines/Road_Traffic_Fine_Management_Process.xes.gz"

fetch "10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460" \
  "$TARGET_ROOT/sepsis/Sepsis Cases - Event Log.xes.gz"

fetch "10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f" \
  "$TARGET_ROOT/bpi_2012/RequestForPayment.xes.gz"

echo
echo "verifying checksums..."
( cd "$HERE" && sed "s#raw/#${TARGET_ROOT}/#" checksums.sha256 | sha256sum -c - )

echo "done. If a DOI redirect above returned a landing page instead of the"
echo "file itself, download it by hand from the DOI and re-run this script"
echo "to verify the checksum."
