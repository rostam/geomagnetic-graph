"""Pass 1: minute-resolution INTERMAGNET CSVs -> hourly means, one file per station.

The source CSVs live in ../observatory-data-storage/Data and total ~12 GB, so each
station is streamed in chunks and reduced to hourly means of H, D, Z before anything
is held in memory.
"""
import os, sys, glob
import pandas as pd

SRC = os.environ.get("MAG_SRC", "/home/rostam/kara/observatory-data-storage/Data")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "hourly")
CHUNK = 2_000_000

os.makedirs(OUT, exist_ok=True)


def downsample(path):
    code = os.path.basename(path)[:-4]
    dest = os.path.join(OUT, f"{code}.csv")
    if os.path.exists(dest):
        print(f"{code}: already done", flush=True)
        return
    parts = []
    rows = 0
    for chunk in pd.read_csv(path, chunksize=CHUNK, parse_dates=["Date"],
                             usecols=["Date", "H", "D", "Z"]):
        rows += len(chunk)
        chunk = chunk.set_index("Date")
        for c in ("H", "D", "Z"):
            chunk[c] = pd.to_numeric(chunk[c], errors="coerce")
        parts.append(chunk.resample("1h").mean())
        print(f"  {code}: {rows:,} rows", flush=True)
    if not parts:
        return
    hourly = pd.concat(parts)
    # chunk boundaries can split an hour -> collapse duplicates
    hourly = hourly.groupby(level=0).mean().sort_index()
    hourly.index.name = "Date"
    hourly.to_csv(dest, float_format="%.4f")
    print(f"{code}: {rows:,} minute rows -> {len(hourly):,} hourly rows", flush=True)


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(SRC, "*.csv")))
    files = [f for f in files if not f.endswith("data_details.csv")]
    for f in files:
        try:
            downsample(f)
        except Exception as e:
            print(f"FAILED {f}: {e}", file=sys.stderr, flush=True)
    print("done", flush=True)
