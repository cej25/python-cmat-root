# Live c4Root connection — first test version

This package includes all previous ROOT-file, 1D spectrum, and half-life changes,
plus the new read-only live ROOT HTTP connection. Extract it into a fresh folder
and run it there, so your existing installation stays available for comparison.
Install dependencies in the Python environment you use for the viewer:

```bash
cd python-cmat-live
python3 -m pip install -r requirements.txt
```

## Try it now, without c4Root

Terminal 1, inside this directory:

```bash
python3 live_root_demo.py --port 1111
```

Terminal 2, inside the same directory:

```bash
python3 pycmat --live-server http://127.0.0.1:1111 --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080 if a browser does not open automatically. The histogram
sidebar's **Live histograms** tree offers `Histograms/Demo/h1_energy` and
`Histograms/Demo/h2_coincidences`. Click either; both remain accessible in the
tree, so you can switch back and forth without reconnecting or restarting.
Use the search box to find histograms by name, folder, or type; the active
histogram is highlighted. **Refresh list** discovers new objects. The server
address is remembered separately from the selected histogram and restored on
a page reload within the same Python session.
Counts increase once per second. The display updates every two
seconds by default, and the refresh selector changes that interval.

The matrix is rectangular (256 X bins × 192 Y bins), with X bins 4 keV wide
and Y bins 8 keV wide. One simulated peak is near X=322 keV, Y=804 keV.
Set a gate around X=300–344 keV to see the Y peak grow as data accumulate.
Existing viewer gate controls and fitting tools are available. Try
**Pause updates**, fit a peak, then **Resume updates**. **Refresh now** fetches
one new snapshot while paused. Optional **Refit peaks after updates** updates
persistent peak fits; half-life fits and polygon integrations run on request.

Stop the simulated source with Ctrl+C. The viewer retains the last good snapshot,
shows a connection error, and retries. Restart the source with the same command;
the viewer recovers automatically. The demo restarts its counts from zero, which
also exercises histogram-reset handling.

## When your c4Root connection is available

Leave your c4Root online macro running and start:

```bash
python3 pycmat --live-server http://localhost:1111 --host 127.0.0.1 --port 8080
```

Choose a TH1, TH2 or TH3 histogram in the browser. TH3 opens the 3D viewer
on the same port; use its **Histogram browser** header link to switch to
another histogram without restarting. See [TH3_QUICKSTART.md](TH3_QUICKSTART.md)
for double gates and time fits. You can also paste a complete `root.json`
URL into **Live ROOT / c4Root server** and click **Connect**, or start
directly with either known LISA path:

```bash
python3 pycmat --live 'http://localhost:1111/Histograms/LISA_FAST/SlowToT/h1_lisafast_slowToT_1/root.json' --port 8080
python3 pycmat --live 'http://localhost:1111/Histograms/LISA_FAST/Fast_Vs._Slow/h2_lisafast_fast_v_slow_ToT_1/root.json' --port 8080
```

`localhost:1111` is resolved by the Python process. If c4Root is on another
machine, replace `localhost` with that machine's hostname or use an SSH-forwarded
port. The browser can run elsewhere; it talks to the viewer, which talks to ROOT.

## What has been checked

- 17 Python checks cover ordinary, compact, base64, and gzip JSON; flow-bin
  removal; rectangular orientation/calibration; a 1000 × 2000 matrix; live
  gates and peak fits; fractional tiles; pause/manual refresh; disconnect,
  reconnect, axis changes, histogram resets, and remembered server addresses.
- DOM checks cover the persistent tree, one-click TH1/TH2 selection, active
  highlighting, name/folder/type search, list refresh, and failed-list retention.
  The earlier live-update JavaScript control flow was also checked against the
  simulated HTTP servers with rendering stubs. JavaScript syntax checks passed.
- Your existing 3072 × 3072 CMAT sample still loads and projects correctly.
- A full visual browser check could not be performed in the development
  environment because the headless browser download was unavailable.
- Your actual c4Root server has not yet been tested end to end. Its folder
  hierarchy and JSON encodings are the first things to verify when connected.

The adapter uses ROOT's documented `h.json` hierarchy and `root.json` histogram
formats, including `compact=23`. It requires no changes to c4Root, no installed
ROOT in Python, and no intermediate ROOT files. Uniform axis binning and
unauthenticated HTTP/HTTPS are supported. Full snapshots are downloaded and only
the active histogram polls; slow downloads or expensive fits can delay the shared
request server. See README.md for details.

Run the checks with:

```bash
python3 -m unittest discover -s tests -v
```
