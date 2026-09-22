# Geomagnetic Network

Twenty magnetic observatories treated as one graph, rewired every day from 2010 to 2022.

**[Open the instrument →](https://rostam.github.io/geomagnetic-graph/)**

A geomagnetic storm is a *global* driver. On a quiet day each observatory mostly sees
its own local diurnal variation and the stations are largely independent. When a storm
arrives, the ring current pushes every station the same way at once and the network
suddenly synchronises. So a storm should be visible as a change in the **structure** of
the correlation graph — not just as a large number at one station.

It is.

| | quiet day (2013-10-20) | St Patrick's Day storm (2015-03-17) |
| --- | ---: | ---: |
| Mean pairwise correlation | 0.448 | **0.908** |
| Edges at r ≥ 0.6 | 29 | **120** (complete) |
| Modularity | 0.477 | **0.000** |
| Largest field swing | 119 nT | **424 nT** |

Modularity going to zero is the whole story in one number: on a quiet day the network
splits into communities that look a lot like geography, and during a storm those
communities stop existing.

## How well does it actually work

Honestly reported, because this matters more than the headline:

- **Sensitivity is good.** 13 of the 17 catalogued storms in the window sit more than
  1σ above the network's usual synchronisation. The mean across all 17 is **+2.14σ**.
- **Specificity is poor.** Of the 15 most synchronised days in thirteen years, only 3
  are catalogued storms. The metric detects global coherence, and storms are not the
  only thing that produces it — a shared quiet-day signature surviving the baseline
  subtraction will do it too.

So this is a good storm *indicator* and not a storm *detector*, and the page shows the
catalogued storms as markers on the timeline so you can judge the overlap yourself
rather than take a claim on faith.

## What was computed

12 GB of minute-resolution INTERMAGNET data from
[observatory-data-storage](https://github.com/rostam/observatory-data-storage), streamed
in chunks down to hourly means, then:

1. **Disturbance field.** Absolute field strength differs by 20,000 nT between stations
   and drifts secularly, so neither is informative. Subtract a 30-day centred rolling
   median; what is left is what storms move.
2. **Daily windows.** 4,748 windows of 24 hourly samples, 19 stations with enough
   coverage in range.
3. **Correlation graph.** Pearson correlation between every pair with at least 18 shared
   hours. The full matrix is kept — quantised to int8 — so the page can re-threshold
   live instead of being stuck with the one the pipeline chose.
4. **Graph measures.** Edge density, algebraic connectivity of the normalised Laplacian,
   greedy-modularity communities, giant component, and the largest field swing.

## Running it

```bash
pip install numpy pandas scipy networkx
python pipeline/01_downsample.py   # 12 GB of minute data -> hourly  (~15 min)
python pipeline/02_graphs.py       # correlation graphs + measures   (~1 min)
python pipeline/03_storms.py       # annotate with the storm catalogue
python -m http.server -d docs 8805
```

`01_downsample.py` expects `observatory-data-storage` checked out as a sibling, or
`MAG_SRC` pointing at the station CSVs.

## Layout

```
pipeline/
  01_downsample.py  minute -> hourly, streamed per station
  02_graphs.py      disturbance field, windows, correlation, graph measures
  03_storms.py      storm catalogue overlay + z-scores
docs/
  js/app.js         map, timeline, live re-thresholding
  data/network.json 4,748 daily windows with their measures
  data/corr.b64     every window's full correlation matrix, int8
```

## Caveats

- Stations are not evenly distributed: Europe is dense, the Pacific is empty. A "global"
  measure over this network is really a measure over Europe, Africa and a handful of
  others.
- Pearson correlation over 24 hourly samples is noisy. The window is short enough to
  localise a storm and short enough that individual r values should not be over-read.
- The storm list is a published reference overlay with approximate Dst minima, not
  ground truth produced by this pipeline.
- TAN (Antananarivo) has no data in the 2010–2022 window and is dropped, leaving 19.
