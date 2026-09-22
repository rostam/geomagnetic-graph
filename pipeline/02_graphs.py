"""Pass 2: turn 20 magnetometer series into a time-varying correlation graph.

The physics: a geomagnetic storm is a *global* driver. On a quiet day each
observatory mostly sees its own local diurnal variation and the stations decouple;
when a storm hits, the ring current pushes every station the same way at once and
the network suddenly synchronises. So a storm should be visible as a change in the
*structure* of the correlation graph — not just as a big number at one station.

For every window we emit the full correlation matrix (quantised to int8) plus the
graph-theoretic summary, and let the site threshold it interactively.
"""
import base64, json, os, sys

import numpy as np
import pandas as pd
import networkx as nx

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOURLY = os.path.join(ROOT, "data", "hourly")
SITE = os.path.join(ROOT, "site", "data")
os.makedirs(SITE, exist_ok=True)

# Geodetic positions. Twelve come from the IAGA2002 headers in the raw archive,
# the rest from the published INTERMAGNET station list.
STATIONS = {
    "AAE": ("Addis Ababa",   "Ethiopia",      9.035,  38.766),
    "ABG": ("Alibag",        "India",        18.620,  72.870),
    "BSL": ("Stennis",       "United States", 30.350, -89.641),
    "CLF": ("Chambon-la-Forêt", "France",    48.025,   2.260),
    "CYG": ("Cheongyang",    "South Korea",  36.370, 126.853),
    "DOU": ("Dourbes",       "Belgium",      50.100,   4.595),
    "DUR": ("Duronia",       "Italy",        41.390,  14.280),
    "EBR": ("Ebro",          "Spain",        40.957,   0.333),
    "HAD": ("Hartland",      "United Kingdom", 50.995, -4.482),
    "HBK": ("Hartebeesthoek", "South Africa", -25.883, 27.707),
    "HER": ("Hermanus",      "South Africa", -34.425,  19.225),
    "HYB": ("Hyderabad",     "India",        17.417,  78.550),
    "IRT": ("Irkutsk",       "Russia",       52.170, 104.450),
    "KNY": ("Kanoya",        "Japan",        31.424, 130.880),
    "MAB": ("Manhay",        "Belgium",      50.297,   5.681),
    "NVS": ("Novosibirsk",   "Russia",       54.850,  83.235),
    "PEG": ("Pedeli",        "Greece",       38.100,  23.900),
    "TAN": ("Antananarivo",  "Madagascar",  -18.917,  47.552),
    "VSS": ("Vassouras",     "Brazil",      -22.400, -43.652),
    "WMQ": ("Urumqi",        "China",        43.800,  87.700),
}

START, END = "2010-01-01", "2023-01-01"
WINDOW_H = 24          # one day of hourly samples per correlation window
MIN_STATIONS = 6       # below this a window has too little of the network to score
MIN_OVERLAP = 18       # hours two stations must share before we trust their r


def load_panel():
    """Hourly H for every station on one common index, as a disturbance field."""
    series = {}
    for code in STATIONS:
        path = os.path.join(HOURLY, f"{code}.csv")
        if not os.path.exists(path):
            print(f"  missing {code}", flush=True)
            continue
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        s = pd.to_numeric(df["H"], errors="coerce")
        s = s[(s.index >= START) & (s.index < END)]
        if s.notna().sum() < 24 * 365:
            print(f"  {code}: only {s.notna().sum()} hours in range, dropped", flush=True)
            continue
        series[code] = s
    panel = pd.DataFrame(series).sort_index()
    panel = panel.reindex(pd.date_range(START, END, freq="1h", inclusive="left"))
    print(f"panel: {panel.shape[0]:,} hours x {panel.shape[1]} stations", flush=True)

    # Absolute field strength differs by 20,000 nT between stations and drifts
    # secularly, so neither is informative. Subtract a 30-day rolling median to
    # get the disturbance field, which is what storms actually move.
    baseline = panel.rolling("30D", min_periods=24 * 5, center=True).median()
    dist = panel - baseline
    # Guard against spikes from bad minutes that survived the hourly mean.
    dist = dist.where(dist.abs() < 2000)
    return panel, dist


def analyse(dist):
    codes = list(dist.columns)
    N = len(codes)
    pairs = [(i, j) for i in range(N) for j in range(i + 1, N)]
    times = dist.index
    starts = range(0, len(times) - WINDOW_H + 1, WINDOW_H)

    rows, mats = [], []
    for s in starts:
        blk = dist.iloc[s:s + WINDOW_H]
        present = [c for c in codes if blk[c].notna().sum() >= MIN_OVERLAP]
        if len(present) < MIN_STATIONS:
            continue
        C = blk.corr(min_periods=MIN_OVERLAP)

        tri = np.full(len(pairs), -128, dtype=np.int8)   # -128 = no data
        for k, (i, j) in enumerate(pairs):
            v = C.iloc[i, j]
            if pd.notna(v):
                tri[k] = int(round(max(-1.0, min(1.0, float(v))) * 100))
        mats.append(tri)

        # graph-theoretic summary at the reference threshold
        G = nx.Graph()
        G.add_nodes_from(present)
        rs = []
        for i in range(N):
            for j in range(i + 1, N):
                v = C.iloc[i, j]
                if pd.notna(v):
                    rs.append(abs(float(v)))
                    if abs(float(v)) >= 0.6:
                        G.add_edge(codes[i], codes[j], w=abs(float(v)))
        n = G.number_of_nodes()
        m = G.number_of_edges()
        dens = 2 * m / (n * (n - 1)) if n > 1 else 0.0

        if m and n > 1:
            L = nx.normalized_laplacian_matrix(G).todense()
            ev = np.sort(np.linalg.eigvalsh(L))
            alg = float(ev[1])
            comp = nx.number_connected_components(G)
            try:
                communities = nx.community.greedy_modularity_communities(G)
                mod = float(nx.community.modularity(G, communities))
                ncom = len(communities)
            except Exception:
                mod, ncom = 0.0, 1
            gcc = len(max(nx.connected_components(G), key=len))
        else:
            alg, comp, mod, ncom, gcc = 0.0, n, 0.0, n, 1

        amp = float(np.nanmax(blk.max() - blk.min())) if blk.notna().any().any() else 0.0
        rows.append({
            "t": blk.index[0].strftime("%Y-%m-%d"),
            "stations": n,
            "edges": m,
            "density": round(dens, 4),
            "mean_r": round(float(np.mean(rs)), 4) if rs else 0.0,
            "alg_conn": round(alg, 4),
            "components": comp,
            "modularity": round(mod, 4),
            "communities": ncom,
            "giant": gcc,
            "amplitude": round(amp, 1),
        })
        if len(rows) % 500 == 0:
            print(f"  {len(rows)} windows ({rows[-1]['t']})", flush=True)

    return codes, pairs, rows, np.array(mats, dtype=np.int8)


if __name__ == "__main__":
    panel, dist = load_panel()
    codes, pairs, rows, mats = analyse(dist)
    print(f"analysed {len(rows)} windows, matrix block {mats.shape}", flush=True)

    json.dump({
        "stations": [{"code": c, "name": STATIONS[c][0], "country": STATIONS[c][1],
                      "lat": STATIONS[c][2], "lon": STATIONS[c][3]} for c in codes],
        "pairs": pairs,
        "window_hours": WINDOW_H,
        "threshold_reference": 0.6,
        "start": START, "end": END,
        "windows": rows,
    }, open(os.path.join(SITE, "network.json"), "w"), separators=(",", ":"))

    with open(os.path.join(SITE, "corr.b64"), "w") as fh:
        fh.write(base64.b64encode(mats.tobytes()).decode())

    for f in ("network.json", "corr.b64"):
        p = os.path.join(SITE, f)
        print(f"wrote {f}: {os.path.getsize(p)/1e6:.2f} MB", flush=True)
