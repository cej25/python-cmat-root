#!/usr/bin/env python3
"""Local simulated ROOT HTTP source, for exercising the viewer without c4Root.

This imitates documented ROOT HTTP/JSON formats; it is not a ROOT/FairRoot
process and does not test event building or real server scheduling.
"""
import argparse
import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

import numpy as np


def compressed_array(values):
    """ROOT compact=23 compatible sparse blocks (no repeated-value runs needed)."""
    values = np.asarray(values).ravel()
    encoded = {"$arr": "Float32", "len": int(values.size)}
    indices = np.flatnonzero(values)
    if not indices.size:
        return encoded
    groups = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
    for i, group in enumerate(groups):
        suffix = "" if i == 0 else str(i)
        encoded["p" + suffix] = int(group[0])
        block = values[group[0]:group[-1] + 1].tolist()
        encoded["v" + suffix] = block if len(block) > 1 else block[0]
    return encoded


def histogram_payload(matrix, name, x_range=(0, 1024), y_range=(0, 1536)):
    matrix = np.asarray(matrix)
    ndim = matrix.ndim
    nx = matrix.shape[-1]
    ny = matrix.shape[0] if ndim == 2 else 0
    flow = np.pad(matrix, 1)
    return {"_typename": "TH2F" if ndim == 2 else "TH1F", "fName": name,
            "fTitle": "SIMULATED live data — " + name, "fNcells": int(flow.size),
            "fEntries": float(matrix.sum()), "fArray": compressed_array(flow),
            "fXaxis": {"fNbins": nx, "fXmin": x_range[0], "fXmax": x_range[1],
                       "fTitle": "Energy X [keV]", "fXbins": []},
            "fYaxis": {"fNbins": ny, "fXmin": y_range[0], "fXmax": y_range[1],
                       "fTitle": "Energy Y [keV]", "fXbins": []}}


class DemoState:
    def __init__(self):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.spectrum = np.zeros(256)
        self.matrix = np.zeros((192, 256))
        x = np.arange(256)
        y = np.arange(192)
        self.spectrum_rate = 0.1 + 80 * np.exp(-0.5 * ((x - 80) / 2.5) ** 2) + 40 * np.exp(-0.5 * ((x - 170) / 3) ** 2)
        self.matrix_rate = (12 * np.exp(-0.5 * ((x[None, :] - 80) / 2.5) ** 2 - 0.5 * ((y[:, None] - 100) / 3) ** 2)
                            + 6 * np.exp(-0.5 * ((x[None, :] - 170) / 3) ** 2 - 0.5 * ((y[:, None] - 50) / 2) ** 2))
        self.rng = np.random.default_rng(42)
        self.fill()

    def fill(self):
        with self.lock:
            self.spectrum += self.rng.poisson(self.spectrum_rate)
            self.matrix += self.rng.poisson(self.matrix_rate)

    def run(self):
        while not self.stop.wait(1):
            self.fill()


class DemoHandler(BaseHTTPRequestHandler):
    state = None

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path in ("/h.json", "/h.json.gz"):
            payload = {"_name": "ROOT", "_childs": [{"_name": "Histograms", "_kind": "ROOT.TFolder",
                "_childs": [{"_name": "Demo", "_kind": "ROOT.TDirectory", "_childs": [
                    {"_name": "h1_energy", "_kind": "ROOT.TH1F"},
                    {"_name": "h2_coincidences", "_kind": "ROOT.TH2F"}]}]}]}
        elif path.startswith("/Histograms/Demo/") and path.endswith(("/root.json", "/root.json.gz")):
            name = path.split("/")[-2]
            with self.state.lock:
                if name == "h1_energy":
                    payload = histogram_payload(self.state.spectrum, name)
                elif name == "h2_coincidences":
                    payload = histogram_payload(self.state.matrix, name)
                else:
                    self.send_error(404)
                    return
        else:
            self.send_error(404)
            return
        body = json.dumps(payload, separators=(",", ":")).encode()
        if path.endswith(".gz"):
            body = gzip.compress(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=1111)
    args = parser.parse_args()
    state = DemoState()
    DemoHandler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
    threading.Thread(target=state.run, daemon=True).start()
    print(f"SIMULATED ROOT source: http://127.0.0.1:{args.port}", flush=True)
    print("Open viewer with: ./pycmat --live-server http://127.0.0.1:" + str(args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
