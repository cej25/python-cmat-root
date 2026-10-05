# ROOT TH3: live energy–energy–time cubes

The existing 3D viewer can now read regular ROOT TH3C/S/I/F/D/L snapshots from
THttpServer, or saved JSON/JSON.gz files. It retains populated regular bins and
calculates projections without allocating the full cube. No PyROOT is required.
The live histogram browser lists TH1, TH2 and TH3 together. Selecting a TH3
opens the 3D viewer on the same server and port. The heading and browser tab
say **ROOT visualiser** for ROOT sources and **GASP visualiser** for CMAT sources.

## Live c4Root

Keep your c4Root online macro running. From this package directory:

```bash
python3 pycmat --live-server http://127.0.0.1:1111 --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080 and select your TH3 in **Live histograms**.
The 3D view opens at `/cube/`. Use **Histogram browser** in its header to return
and select any TH1, TH2 or TH3 without restarting Python.

Alternatively, launch a particular TH3 directly:

```bash
python3 pycmat --live-th3 'http://127.0.0.1:1111/Histograms/LISA_FAST/LaBr/Energy_Spectra/h3_E1_vs_E2_vs_dt_all_labr/root.json.gz?compact=23' --host 127.0.0.1 --port 8081
```

Open http://127.0.0.1:8081. The TH1/TH2 viewer may keep running on port 8080.
`127.0.0.1` is resolved by Python; use the c4Root hostname/IP if it runs elsewhere.

Refresh defaults to five seconds. The **Live ROOT TH3** section provides pause,
resume, refresh now, and an interval selector. CLI: `--live-interval 10`.
Complete immutable snapshots replace the previous reader. Gates/zoom stay in
place; rectangular and polygon gates are recomputed. Failed requests retain the
last good snapshot and retry automatically. Reset counts are accepted. Changed
binning, axis ranges or titles require selecting the histogram again in the
browser, or restarting a standalone TH3 viewer.

## Plane and double-gate workflow

- Plane **0-1**: Energy 1 horizontally, Energy 2 vertically; time on Axis 3.
- Plane **0-2**: Energy 1 horizontally, time vertically; Energy 2 on Axis 2.
- Plane **1-2**: Energy 2 horizontally, time vertically; Energy 1 on Axis 1.

For a time spectrum, choose 0-1. Set a peak gate with the existing **W** controls
on each energy spectrum. Both gates must be satisfied; Axis 3 displays the
resulting time spectrum. Existing **X** background gates and polygon cuts are
also supported. Peak polygons have a solid yellow border; background polygons
have a dashed pink border. Both have contrasting outlines and labels that stay
visible after applying the gate and during live refresh. Channel ranges remain the internal gate coordinates; calibrated
labels show the ROOT physical values. The sample has 2 keV energy bins and
0.4 ns time bins. Bin centres, labels and half-life input use ROOT calibration.
Use the half-life popup for Axis 3 and leave its calibrated-coordinate selection
active to fit in nanoseconds, with either model.

Zooming the third spectrum limits that axis in the 2D display, using the existing
3D viewer controls. Fits are snapshots and do not refit automatically. Pause
updates while analysing. Fit-derived Gamba cuts hold automatic refresh until
cleared; **Refresh now** clears that fit-derived cut and updates the snapshot.

## Offline test with the uploaded sample

```bash
python3 pycmat --snapshot-th3 examples/sample_th3.json.gz --host 127.0.0.1 --port 8081
```

This is a fixed snapshot. It contains a 500 × 500 × 1000 cube, 5,378 populated
regular bins and 6,902 regular-bin counts. Stored sparse bins plus all three
cached planes occupy about 10.2 MB; parsing and Python overhead are additional.

## Validation and scope

Python checks cover all three plane orientations, flow-bin removal, fractional
contents, time calibration, single/double gates and background subtraction,
polygon and fit-derived cuts, reset/disconnect/axis-change handling, float64
HTTP tiles, and an exponential fit recovering a known 5 ns half-life. The user's
snapshot is included for reproducibility. JavaScript control-flow checks cover
calibrated popup input, refresh, pause/manual updates and polygon refresh.
Full visual browser QA and this TH3's actual c4Root streaming run remain to be
checked on the user's machine.

```bash
python3 -m unittest discover -s tests -v
node tests/test_root_cube_ui.cjs
node tests/test_viewer_brand.cjs
node tests/test_banana_overlay.cjs
```

Uniform binning is required. Flow bins are excluded. Bin contents remain
floating point. TProfile3D and THnSparse are not supported. Existing uncertainty
handling uses count statistics; weighted-histogram Sumw2 is not imported.

The adapter limits decoded populated bins to 10 million, each cached plane to
10 million pixels, and JSON responses to 256 MiB. Increasing occupancy increases
memory and transfer time, even with compact encoding. If those limits are
reached, the last good live snapshot remains visible with an error; coarser
binning or projections calculated in c4Root are the next solution.
