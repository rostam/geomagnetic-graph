"""Annotate the windows with published storm dates, and with what the network itself says.

The storm list is a reference overlay, not ground truth for the detector: the point of
the site is to let you compare "days the network synchronised" against "days a storm is
known to have happened" and see how well they line up.
"""
import json, os
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SITE = os.path.join(ROOT, "site", "data")

# Major geomagnetic storms 2010-2022 with their approximate Dst minimum (nT),
# from published storm catalogues. Dates are the storm main phase.
STORMS = [
    ("2011-08-06", -115, "Coronal mass ejection, August 2011"),
    ("2011-09-26", -118, "September 2011 storm"),
    ("2011-10-25", -147, "October 2011 storm"),
    ("2012-03-09", -145, "March 2012 storm"),
    ("2012-04-24", -120, "April 2012 storm"),
    ("2012-10-01", -122, "October 2012 storm"),
    ("2013-03-17", -132, "St Patrick's Day storm, 2013"),
    ("2013-06-01", -119, "June 2013 storm"),
    ("2015-03-17", -223, "St Patrick's Day storm, 2015 — the largest of solar cycle 24"),
    ("2015-06-23", -204, "June 2015 storm"),
    ("2015-10-07", -124, "October 2015 storm"),
    ("2015-12-20", -155, "December 2015 storm"),
    ("2016-10-13", -104, "October 2016 storm"),
    ("2017-05-28", -125, "May 2017 storm"),
    ("2017-09-08", -142, "September 2017 storm"),
    ("2018-08-26", -174, "August 2018 storm"),
    ("2021-11-04", -105, "November 2021 storm"),
]


def main():
    d = json.load(open(os.path.join(SITE, "network.json")))
    w = d["windows"]
    idx = {r["t"]: i for i, r in enumerate(w)}

    mr = np.array([r["mean_r"] for r in w])
    mu, sd = mr.mean(), mr.std()

    marked = 0
    for t, dst, note in STORMS:
        i = idx.get(t)
        if i is None:
            continue
        w[i]["storm"] = {"dst": dst, "note": note, "z": round(float((mr[i] - mu) / sd), 2)}
        marked += 1

    # what the network itself flags, independent of the catalogue
    z = (mr - mu) / sd
    for i, r in enumerate(w):
        r["z"] = round(float(z[i]), 2)

    d["baseline"] = {"mean_r_mean": round(float(mu), 4), "mean_r_sd": round(float(sd), 4)}
    d["storms"] = [{"t": t, "dst": dst, "note": n} for t, dst, n in STORMS if t in idx]

    json.dump(d, open(os.path.join(SITE, "network.json"), "w"), separators=(",", ":"))

    zs = [w[idx[t]]["z"] for t, _, _ in STORMS if t in idx]
    print(f"marked {marked} storms")
    print(f"baseline mean_r = {mu:.3f} +/- {sd:.3f}")
    print(f"mean z on storm days: {np.mean(zs):+.2f}")
    print(f"storms above +1 sigma: {sum(1 for x in zs if x > 1)}/{len(zs)}")

    top = np.argsort(mr)[-15:][::-1]
    hits = sum(1 for i in top if "storm" in w[i])
    print(f"of the 15 most synchronised days, {hits} are in the storm catalogue")


if __name__ == "__main__":
    main()
