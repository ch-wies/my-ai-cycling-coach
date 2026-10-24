"""Export an activity to the interval-detection bench's neutral format.

This is the *only* data-source-aware piece of the interval-detection
workflow: it dumps an activity to a stripped ``t,power`` CSV that the
(app-independent) bench and detector consume. Keeps the dependency arrow
app -> package.

Usage:
    python -m scripts.export_for_bench <activity_id> [<activity_id> ...]

Writes the (t, power) trace to bench/activities/<id>.csv and seeds the
annotation file bench/labels/<id>.json with auto-derived meta (indoor /
sport_type). Interval ground truth is added later with the label tool.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.intervals_api import IntervalsClient

_BENCH_DIR = Path(__file__).resolve().parents[1] / "interval_detection" / "bench"
BENCH_ACTIVITIES_DIR = _BENCH_DIR / "activities"

# Reuse the bench's annotation IO so the schema lives in one place.
sys.path.insert(0, str(_BENCH_DIR))
import labelio  # noqa: E402


def export_activity(
    activity_id: str,
    client: IntervalsClient | None = None,
    out_dir: Path = BENCH_ACTIVITIES_DIR,
) -> Path:
    client = client or IntervalsClient()
    metadata = client._get_activity_detail(activity_id)
    activity = client.download_activity(activity_id)

    power = activity.get_time_series("power")
    if power is None or len(power) == 0:
        raise ValueError(f"Activity {activity_id} has no power data; skipping.")

    time_s = activity.get_time_array()
    n = min(len(time_s), len(power))
    df = pd.DataFrame({"t": np.asarray(time_s)[:n], "power": np.asarray(power)[:n]})

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{activity_id}.csv"
    df.to_csv(out_path, index=False)

    # Seed annotation meta (preserves any existing labels via save_meta merge).
    sport_type = metadata.get("sport_type") or metadata.get("type")
    indoor = bool(metadata.get("trainer")) or sport_type == "VirtualRide"
    labelio.save_meta(activity_id, indoor=indoor, sport_type=sport_type)

    return out_path


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    client = IntervalsClient()
    for activity_id in argv:
        try:
            path = export_activity(activity_id, client=client)
            print(f"wrote {path}")
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"activity {activity_id}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
