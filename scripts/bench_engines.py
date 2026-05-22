"""Benchmark fiona vs pyogrio as read backends for rasterstats.

Generates N random point features inside the extent of tests/data/slope.tif,
writes them to a temporary GeoJSON file, converts it to GeoPackage, Shapefile,
and other formats via ogr2ogr, then times how long each engine takes to iterate over
every feature via ``read_features``.

Usage
-----
    uv run python scripts/bench_engines.py
"""

import json
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import rasterio

from rasterstats.io import read_features
from rasterstats.main import gen_zonal_stats

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


GPKG_LAYER = "features"
SHP_LAYER = "features"


def generate_gpkg(geojson_path: Path, gpkg_path: Path) -> None:
    """Convert an existing GeoJSON file to GeoPackage using ogr2ogr."""
    subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "GPKG",
            "-nln",
            GPKG_LAYER,
            str(gpkg_path),
            str(geojson_path),
        ],
        check=True,
        capture_output=True,
    )


def generate_shp(geojson_path: Path, shp_dir: Path) -> None:
    """Convert an existing GeoJSON file to ESRI Shapefile using ogr2ogr.

    ogr2ogr writes a directory of sidecar files (.shp, .dbf, .shx, .prj)
    so ``shp_dir`` must be a directory path that does not yet exist.
    """
    subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "ESRI Shapefile",
            "-nln",
            SHP_LAYER,
            str(shp_dir),
            str(geojson_path),
        ],
        check=True,
        capture_output=True,
    )


def generate_flatgeobuf(geojson_path: Path, fgb_path: Path) -> None:
    """Convert an existing GeoJSON file to FlatGeobuf using ogr2ogr."""
    subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "FlatGeobuf",
            str(fgb_path),
            str(geojson_path),
        ],
        check=True,
        capture_output=True,
    )


def generate_parquet(geojson_path: Path, parquet_path: Path) -> None:
    """Convert an existing GeoJSON file to Parquet using ogr2ogr."""
    subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "Parquet",
            str(parquet_path),
            str(geojson_path),
        ],
        check=True,
        capture_output=True,
    )


def time_engine(path: Path, engine: str, n: int, layer=0) -> float:
    "Times how long each engine takes to iterate through all features"
    t0 = time.perf_counter()
    count = sum(1 for _ in read_features(str(path), layer=layer, engine=engine))
    elapsed = time.perf_counter() - t0
    assert count == n, f"Expected {n} features, got {count}"
    return elapsed


def time_zonal_stats(path: Path, engine: str, n: int, layer=0) -> float:
    """Full e2e test running all stats againts the geotiff.
    Typically 100x slower than just reading the features and discarding them.
    IOW this is NOT typically IO bound for local files.
    """
    t0 = time.perf_counter()
    count = sum(
        1
        for _ in gen_zonal_stats(str(path), str(SLOPE_TIF), layer=layer, engine=engine)
    )
    elapsed = time.perf_counter() - t0
    assert count == n, f"Expected {n} features, got {count}"
    return elapsed


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N

    print(f"Generating {n:,} random point features over {SLOPE_TIF.name} …")
    with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    gpkg_path = Path(tempfile.mktemp(suffix=".gpkg"))
    shp_dir = Path(tempfile.mkdtemp())
    fgb_path = Path(tempfile.mktemp(suffix=".fgb"))
    # parquet_path = Path(tempfile.mktemp(suffix=".parquet"))

    try:
        generate_geojson(tmp_path, n)
        file_mb = tmp_path.stat().st_size / 1024 / 1024
        print(f"Wrote GeoJSON    {file_mb:.1f} MB → {tmp_path}")

        print("Converting to GeoPackage via ogr2ogr …")
        generate_gpkg(tmp_path, gpkg_path)
        gpkg_mb = gpkg_path.stat().st_size / 1024 / 1024
        print(f"Wrote GeoPackage {gpkg_mb:.1f} MB → {gpkg_path}")

        print("Converting to Shapefile via ogr2ogr …")
        generate_shp(tmp_path, shp_dir)
        shp_mb = (
            sum(f.stat().st_size for f in shp_dir.rglob("*") if f.is_file())
            / 1024
            / 1024
        )
        print(f"Wrote Shapefile  {shp_mb:.1f} MB → {shp_dir}")

        print("Converting to FlatGeobuf via ogr2ogr …")
        generate_flatgeobuf(tmp_path, fgb_path)
        fgb_mb = fgb_path.stat().st_size / 1024 / 1024
        print(f"Wrote FlatGeobuf {fgb_mb:.1f} MB → {fgb_path}")

        # print("Converting to Parquet via ogr2ogr …")
        # generate_parquet(tmp_path, parquet_path)
        # parquet_mb = parquet_path.stat().st_size / 1024 / 1024
        # print(f"Wrote Parquet    {parquet_mb:.1f} MB → {parquet_path}\n")

        print("=== GeoJSON ===")
        fiona_secs = time_engine(tmp_path, "fiona", n)
        print(f"fiona  : {fiona_secs:.3f}s  ({n / fiona_secs:,.0f} feat/s)")

        pyogrio_secs = time_engine(tmp_path, "pyogrio", n)
        print(f"pyogrio: {pyogrio_secs:.3f}s  ({n / pyogrio_secs:,.0f} feat/s)")
        ratio = fiona_secs / pyogrio_secs
        faster = "pyogrio" if ratio > 1 else "fiona"
        print(f"\n{faster} is {max(ratio, 1 / ratio):.2f}x faster (GeoJSON)")

        print("\n=== GeoPackage ===")
        fiona_gpkg_secs = time_engine(gpkg_path, "fiona", n, layer=GPKG_LAYER)
        print(f"fiona  : {fiona_gpkg_secs:.3f}s  ({n / fiona_gpkg_secs:,.0f} feat/s)")

        pyogrio_gpkg_secs = time_engine(gpkg_path, "pyogrio", n, layer=GPKG_LAYER)
        print(
            f"pyogrio: {pyogrio_gpkg_secs:.3f}s  ({n / pyogrio_gpkg_secs:,.0f} feat/s)"
        )
        ratio = fiona_gpkg_secs / pyogrio_gpkg_secs
        faster = "pyogrio" if ratio > 1 else "fiona"
        print(f"\n{faster} is {max(ratio, 1 / ratio):.2f}x faster (GeoPackage)")

        print("\n=== Shapefile ===")
        shp_path = shp_dir / (SHP_LAYER + ".shp")
        fiona_shp_secs = time_engine(shp_path, "fiona", n, layer=SHP_LAYER)
        print(f"fiona  : {fiona_shp_secs:.3f}s  ({n / fiona_shp_secs:,.0f} feat/s)")

        pyogrio_shp_secs = time_engine(shp_path, "pyogrio", n, layer=SHP_LAYER)
        print(f"pyogrio: {pyogrio_shp_secs:.3f}s  ({n / pyogrio_shp_secs:,.0f} feat/s)")
        ratio = fiona_shp_secs / pyogrio_shp_secs
        faster = "pyogrio" if ratio > 1 else "fiona"
        print(f"\n{faster} is {max(ratio, 1 / ratio):.2f}x faster (Shapefile)")

        print("\n=== FlatGeobuf ===")
        print("fiona  : skip")  # fiona wheels not necessarily built with flatgeobuf
        # fiona_fgb_secs = time_engine(fgb_path, "fiona", n, layer=None)
        # print(f"fiona  : {fiona_fgb_secs:.3f}s  ({n / fiona_fgb_secs:,.0f} feat/s)")

        pyogrio_fgb_secs = time_engine(fgb_path, "pyogrio", n, layer=None)
        print(f"pyogrio: {pyogrio_fgb_secs:.3f}s  ({n / pyogrio_fgb_secs:,.0f} feat/s)")

        # The pyogrio binary wheels don't support parquet yet
        # print(pyogrio.list_drivers())
        # print("\n=== Parquet ===")
        # fiona_parquet_secs = time_engine(parquet_path, "fiona", n, layer=0)
        # print(
        #     f"fiona  : {fiona_parquet_secs:.3f}s  ({n / fiona_parquet_secs:,.0f} feat/s)"
        # )
        #
        # pyogrio_parquet_secs = time_engine(parquet_path, "pyogrio", n, layer=0)
        # print(
        #     f"pyogrio: {pyogrio_parquet_secs:.3f}s  ({n / pyogrio_parquet_secs:,.0f} feat/s)"
        # )
        # ratio = fiona_parquet_secs / pyogrio_parquet_secs
        # faster = "pyogrio" if ratio > 1 else "fiona"
        # print(f"\n{faster} is {max(ratio, 1 / ratio):.2f}x faster (Parquet)")

    finally:
        tmp_path.unlink(missing_ok=True)
        gpkg_path.unlink(missing_ok=True)
        shutil.rmtree(shp_dir, ignore_errors=True)
        fgb_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
