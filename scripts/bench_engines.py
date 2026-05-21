"""Benchmark fiona vs pyogrio as read backends for rasterstats.

Generates N random point features inside the extent of tests/data/slope.tif,
writes them to a temporary GeoJSON file, then times how long each engine takes
to iterate over every feature via ``read_features``.

Usage
-----
    uv run python scripts/bench_engines.py
"""

import json
import random
import sys
import tempfile
import time
from pathlib import Path

import rasterio

# Resolve the repo root so the script works from any cwd
REPO_ROOT = Path(__file__).parent.parent
SLOPE_TIF = REPO_ROOT / "tests" / "data" / "slope.tif"
DEFAULT_N = 100_000


def generate_geojson(path: Path, n: int) -> None:
    with rasterio.open(SLOPE_TIF) as src:
        left, bottom, right, top = src.bounds

    features = [
        {
            "type": "Feature",
            "properties": {"id": i},
            "geometry": {
                "type": "Point",
                "coordinates": [
                    random.uniform(left, right),
                    random.uniform(bottom, top),
                ],
            },
        }
        for i in range(n)
    ]
    fc = {"type": "FeatureCollection", "features": features}
    with open(path, "w") as f:
        json.dump(fc, f)


def time_engine(path: Path, engine: str, n: int) -> float:
    # Import here so the benchmark reflects real-world import cost only once
    from rasterstats.io import read_features

    t0 = time.perf_counter()
    count = sum(1 for _ in read_features(str(path), engine=engine))
    elapsed = time.perf_counter() - t0
    assert count == n, f"Expected {n} features, got {count}"
    return elapsed


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N

    print(f"Generating {n:,} random point features over {SLOPE_TIF.name} …")
    with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        generate_geojson(tmp_path, n)
        file_mb = tmp_path.stat().st_size / 1024 / 1024
        print(f"Wrote {file_mb:.1f} MB → {tmp_path}\n")

        fiona_secs = time_engine(tmp_path, "fiona", n)
        print(f"fiona  : {fiona_secs:.3f}s  ({n / fiona_secs:,.0f} feat/s)")

        try:
            import pyogrio  # noqa: F401

            pyogrio_secs = time_engine(tmp_path, "pyogrio", n)
            print(f"pyogrio: {pyogrio_secs:.3f}s  ({n / pyogrio_secs:,.0f} feat/s)")
            ratio = fiona_secs / pyogrio_secs
            faster = "pyogrio" if ratio > 1 else "fiona"
            print(f"\n{faster} is {max(ratio, 1/ratio):.2f}x faster")
        except ImportError:
            print("pyogrio not installed - skipping pyogrio benchmark")
            print("Install with: pip install rasterstats[pyogrio]")
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
