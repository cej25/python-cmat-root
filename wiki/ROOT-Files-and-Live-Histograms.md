# ROOT Files & Live Histograms

The python-cmat web viewers can go beyond the native `.cmat` format: they load TH1 and TH2 histograms from local ROOT files through [uproot](https://uproot.readthedocs.io/), and stream live TH1, TH2 and TH3 histograms from the ROOT `THttpServer` REST interface (including c4Root online setups). No PyROOT binding and no local ROOT installation are required on the viewer side, and the complete analysis toolkit — 1D gates, background windows, polygon Banana ROIs, peak fitting, half-life fitting, and vector PDF export — works identically on ROOT and CMAT data.

The page heading and browser tab show **ROOT visualiser** for ROOT inputs and **GASP visualiser** for CMAT inputs.

---

## Supported Inputs

| Source | Histogram types | How to launch |
|---|---|---|
| Local ROOT file | TH1, TH2 | `./pycmat file.root` (pick a histogram in the browser) or `./pycmat 'file.root::folder/histogram_name'` |
| Live ROOT `THttpServer` / c4Root | TH1, TH2, TH3 | `./pycmat --live-server http://SERVER:PORT` |
| Specific live histogram URL | TH1, TH2 | `./pycmat --live 'http://SERVER:PORT/path/root.json'` (repeatable) |
| Direct live TH3 URL | TH3 | `./pycmat --live-th3 'http://SERVER:PORT/path/root.json.gz?compact=23'` |
| Saved TH3 JSON snapshot | TH3 | `./pycmat --snapshot-th3 path/to/snapshot.json.gz` |

The `pycmat` unified launcher routes ROOT file and live inputs automatically: `--live-th3` and `--snapshot-th3` open the 3D viewer, everything else opens the 1D/2D viewer.

---

## ROOT Files (TH1 / TH2)

```bash
# Open a ROOT file and choose a TH1 or TH2 from the searchable histogram browser
./pycmat your_file.root --host 127.0.0.1 --port 8080

# Select a histogram directly, including its directory path
./pycmat 'your_file.root::folder/histogram_name' --host 127.0.0.1 --port 8080
```

ROOT file input uses `uproot`, included in `requirements.txt`. Multiple ROOT files can be opened like multiple `.cmat` files, and the histogram browser lists every candidate histogram in the file.

---

## Live ROOT / c4Root Histograms

With your ROOT `THttpServer` (or c4Root online macro) already running, start the viewer:

```bash
./pycmat --live-server http://127.0.0.1:1111 --host 127.0.0.1 --port 8080
```

- Port `1111` belongs to the ROOT server and port `8080` to the viewer; replace `127.0.0.1` with the c4Root hostname or IP if it runs on another computer (an SSH-forwarded port also works).
- The **Live histograms** folder tree and search box list all TH1, TH2 and TH3 objects together; the active histogram is highlighted and **Refresh list** discovers new objects.
- The server address is remembered separately from the selected histogram and restored on page reload within the same Python session.
- Histograms refresh as data accumulate (every 2 s by default in the 2D viewer, adjustable with the refresh selector or `--live-interval 0.5`–`300`), with gates and projections recalculated while preserving gate definitions and zoom.
- **Pause updates** freezes the display for analysis, **Refresh now** fetches one new snapshot while paused, and optional **Refit peaks after updates** keeps persistent peak fits current.
- If a request fails, the viewer retains the last good snapshot, shows a connection error, and retries automatically. Restarted sources and histogram resets are handled.

You can also paste a complete `root.json` URL into **Live ROOT / c4Root server** and click **Connect**, or start directly with one or more known histogram paths:

```bash
python3 pycmat --live 'http://localhost:1111/Histograms/LISA_FAST/SlowToT/h1_lisafast_slowToT_1/root.json' --port 8080
python3 pycmat --live 'http://localhost:1111/Histograms/LISA_FAST/Fast_Vs._Slow/h2_lisafast_fast_v_slow_ToT_1/root.json' --port 8080
```

---

## Live TH3 Gating and Time Spectra

The 3D viewer can display any of the three orthogonal planes of a live TH3 (e.g. an energy–energy–time cube from c4Root):

```bash
./pycmat --live-server http://127.0.0.1:1111 --host 127.0.0.1 --port 8080   # then select a TH3
./pycmat --live-th3 'http://127.0.0.1:1111/Histograms/LISA_FAST/LaBr/Energy_Spectra/h3_E1_vs_E2_vs_dt_all_labr/root.json.gz?compact=23' --port 8081
```

Selecting a TH3 in the browser opens the 3D viewer at `/cube/` on the same server and port; its **Histogram browser** header link returns to the shared menu without restarting Python. TH3 refresh defaults to 5 s and supports pause, resume, refresh now, and an interval selector (`--live-interval 10`).

### Plane selection

| Plane | Horizontal axis | Vertical axis | Remaining axis (spectra) |
|---|---|---|---|
| **0-1** | Energy 1 | Energy 2 | Time |
| **0-2** | Energy 1 | Time | Energy 2 |
| **1-2** | Energy 2 | Time | Energy 1 |

### Double-gate workflow (energy–energy–time example)

1. Select plane **0-1** to display Energy 1 versus Energy 2.
2. Apply separate **W** peak gates on the two energy spectra — both must be satisfied — and optionally **X** background gates. Existing polygon cuts are also supported.
3. Axis 3 shows the resulting time spectrum, which can be fitted for half-life with the popup when that axis represents time (leave its calibrated-coordinate selection active to fit in nanoseconds, with either model).

**Shift+G** draws a peak polygon on the displayed matrix and **Shift+B** a background polygon. Applied peak polygons have solid yellow borders; background polygons have dashed pink borders, both with contrasting outlines and labels that remain visible during live refresh. Channel ranges stay in internal gate coordinates, while calibrated labels, bin centres, and half-life input use the ROOT physical values and units.

Zooming the third spectrum limits that axis in the 2D display. Fits are snapshots and do not refit automatically — pause updates while analysing. Fit-derived Gamba cuts hold automatic refresh until cleared; **Refresh now** clears such a cut and updates the snapshot.

An offline example snapshot (500 × 500 × 1000 cube) is included for testing:

```bash
./pycmat --snapshot-th3 examples/sample_th3.json.gz --host 127.0.0.1 --port 8081
```

Compact sparse TH3 data can be projected without expanding the entire cube. Memory use and refresh time still increase with histogram occupancy and transfer size.

---

## Offline Demo Without c4Root

The included simulator mimics a ROOT HTTP source, useful to try the live workflow before connecting to real hardware:

```bash
# Terminal 1: simulated ROOT source (counts increase once per second)
python3 live_root_demo.py --port 1111

# Terminal 2: the viewer
python3 pycmat --live-server http://127.0.0.1:1111 --host 127.0.0.1 --port 8080
```

The **Live histograms** tree offers `Histograms/Demo/h1_energy` and `Histograms/Demo/h2_coincidences`. Set a gate around X = 300–344 keV to watch the Y peak grow as data accumulate, then try **Pause updates**, fit a peak, and **Resume updates**. Stopping the demo with Ctrl+C and restarting it also exercises disconnect/reconnect and histogram-reset handling.

The demo 2D histogram is rectangular (256 X bins × 192 Y bins) with 4 keV X bins and 8 keV Y bins, and its simulated peak sits near X = 322 keV, Y = 804 keV. Both demo histograms remain in the tree, so you can switch between them without reconnecting or restarting; the display refreshes every 2 s by default (change it with the refresh selector), and the counts restart from zero when the demo is relaunched.

---

## Technical Notes and Limitations

- The adapter uses the documented ROOT `h.json` hierarchy and `root.json` histogram formats, including `compact=23`; it requires no changes to c4Root, no installed ROOT in Python, and no intermediate ROOT files.
- Uniform axis binning is required; flow bins are excluded. Bin contents remain floating point. `TProfile3D` and `THnSparse` are not supported, and weighted-histogram `Sumw2` uncertainties are not imported (existing uncertainty handling uses count statistics).
- Live updates download complete immutable snapshots, and only the active histogram polls — slow downloads or expensive fits can delay the shared request server.
- Safety limits: at most 10 million decoded populated bins, 10 million pixels per cached plane, and 256 MiB per JSON response. If a limit is reached, the last good live snapshot remains visible with an error; coarser binning or projections computed in c4Root are the next solution.
- Changed binning, axis ranges or titles require selecting the histogram again in the browser, or restarting a standalone TH3 viewer.
- Uniform binning, unauthenticated HTTP/HTTPS, and rectangular orientation/calibration are supported.

---

## Validation

Automated Python and JavaScript check suites validated ordinary, compact, base64 and gzip JSON; rectangular orientation/calibration; a 1000 × 2000 matrix; live gates and peak fits; pause/manual refresh; disconnect, reconnect, axis changes, histogram resets, and remembered server addresses; all three TH3 plane orientations; single/double gates and background subtraction; polygon and fit-derived cuts; and an exponential fit recovering a known 5 ns half-life. Full visual browser QA and end-to-end runs against a production c4Root server remain to be verified on the target setup.

---

## See Also

- [Interactive Web Viewer](Interactive-Web-Viewer) — 2D viewer internals
- [3D Matrix Analysis & Web Viewer](3D-Matrix-Analysis-and-Web-Viewer) — 3D viewer internals
- [Keyboard Shortcuts & Controls](Keyboard-Shortcuts-and-Navigation) — gate and polygon shortcuts