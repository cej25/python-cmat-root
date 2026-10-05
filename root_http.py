"""Read-only ROOT THttpServer adapter. No PyROOT installation is required.

Wire formats follow ROOT TBufferJSON and TRootSniffer, including compact=23
zero/repetition suppression. A refresh produces a new immutable snapshot.
"""
import base64
import gzip
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import numpy as np
from root_matrix import ROOTMatrixReader, _axis_unit, _linear_calibration

MAX_CELLS = 50_000_000
MAX_BYTES = 256 * 1024 * 1024


def normalize_url(url):
    parts = urlsplit(str(url).strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Enter an http:// or https:// ROOT server URL")
    if parts.username or parts.password:
        raise ValueError("Credentials in URLs are not supported")
    path = quote(unquote(parts.path), safe="/")
    return urlunsplit((parts.scheme, parts.netloc, path.rstrip("/"), "", ""))


def histogram_url(url):
    url = normalize_url(url)
    url = re.sub(r"/root\.json(?:\.gz)?$", "", url)
    return url + "/root.json?compact=23"


def infer_server_url(url):
    """Infer standard ROOT/FairRoot base paths from a direct histogram URL."""
    parts = urlsplit(normalize_url(url))
    path = parts.path
    for marker in ("/Objects/", "/Histograms/", "/Files/"):
        if marker in path:
            return urlunsplit((parts.scheme, parts.netloc, path.split(marker, 1)[0], "", ""))
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def read_json(url, timeout=4):
    req = Request(url, headers={"Accept": "application/json", "Cache-Control": "no-cache"})
    with urlopen(req, timeout=timeout) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("ROOT response exceeds 256 MiB")
    if body.startswith(b"\x1f\x8b"):
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
            body = stream.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("Uncompressed ROOT response exceeds 256 MiB")
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected a ROOT JSON object")
    return data


def decode_array(value, expected=None):
    """Decode ordinary arrays, TArray wrappers and ROOT $arr blocks."""
    if isinstance(value, dict) and "fArray" in value:
        value = value["fArray"]
    if isinstance(value, list):
        out = np.asarray(value, dtype=np.float64)
    elif isinstance(value, dict) and "$arr" in value:
        length = int(value["len"])
        if length < 0 or length > MAX_CELLS or (expected is not None and length != expected):
            raise ValueError("Invalid ROOT array length")
        out = np.zeros(length, dtype=np.float64)
        if "b" in value:
            types = {"Float32": "<f4", "Float64": "<f8", "Int32": "<i4",
                     "Int16": "<i2", "Int8": "i1", "Uint8": "u1",
                     "Uint16": "<u2", "Uint32": "<u4", "Int64": "<i8", "Uint64": "<u8"}
            dtype = np.dtype(types[value["$arr"]])
            offset = int(value.get("o", 0))
            if offset < 0 or offset % dtype.itemsize:
                raise ValueError("Invalid ROOT base64 offset")
            block = np.frombuffer(base64.b64decode(value["b"], validate=True), dtype=dtype)
            start = offset // dtype.itemsize
            if start + block.size > length:
                raise ValueError("ROOT base64 block exceeds array length")
            out[start:start + block.size] = block
        else:
            cursor, index = 0, 0
            while True:
                suffix = "" if index == 0 else str(index)
                if "v" + suffix not in value:
                    break
                start = int(value.get("p" + suffix, cursor))
                block = value["v" + suffix]
                if isinstance(block, list):
                    block = np.asarray(block, dtype=np.float64)
                    count = block.size
                else:
                    count = int(value.get("n" + suffix, 1))
                if start < cursor or count < 1 or start + count > length:
                    raise ValueError("Invalid ROOT compressed array block")
                out[start:start + count] = block
                cursor = start + count
                index += 1
    else:
        raise ValueError("Unsupported ROOT bin array encoding")
    if out.ndim != 1 or out.size > MAX_CELLS or (expected is not None and out.size != expected):
        raise ValueError("ROOT bin count does not match histogram axes")
    if not np.all(np.isfinite(out)):
        raise ValueError("ROOT bins contain non-finite values")
    return out


class ROOTHTTPReader(ROOTMatrixReader):
    def __init__(self, url, payload=None):
        self.url = histogram_url(url)
        h = read_json(self.url) if payload is None else payload
        cls = h.get("_typename", "")
        if not re.fullmatch(r"TH[123][CSIFDL]", cls):
            raise ValueError(f"Expected a regular TH1/TH2 histogram, received {cls or 'unknown object'}")
        self.ndim = 2 if cls.startswith("TH2") else 1
        self.object_name = h.get("fName", "histogram")
        # Existing fit reports/export names use filename.name/stem. This is a
        # display name only; the HTTP URL is kept separately and never opened.
        self.filename = Path(self.object_name)
        self.title = h.get("fTitle", self.object_name)
        self.entries = float(h.get("fEntries", 0))
        self.cal, self.axis_labels = {}, {}
        sizes = []
        for axis, label in enumerate(("X", "Y")[:self.ndim]):
            a = h[f"f{label}axis"]
            n = int(a["fNbins"])
            lo, hi = float(a["fXmin"]), float(a["fXmax"])
            if n < 1 or n > MAX_CELLS or not np.isfinite([lo, hi]).all() or hi <= lo:
                raise ValueError(f"Invalid {label} axis")
            edges = decode_array(a["fXbins"]) if "fXbins" in a else np.array([])
            if edges.size == 0:
                self.cal[axis] = [lo, (hi - lo) / n, 0.0]
            else:
                if edges.size != n + 1:
                    raise ValueError(f"Invalid {label} bin edges")
                self.cal[axis] = _linear_calibration(edges, label)
            self.axis_labels[axis] = str(a.get("fTitle", "")) or f"ROOT {label} coordinate"
            sizes.append(n)
        cells = (sizes[0] + 2) * (sizes[1] + 2 if self.ndim == 2 else 1)
        if cells > MAX_CELLS or int(h["fNcells"]) != cells:
            raise ValueError("ROOT cell count does not match histogram axes")
        values = decode_array(h["fArray"], cells)
        if self.ndim == 1:
            self._matrix = values[1:-1][np.newaxis, :].copy()
        else:
            # ROOT global bin indexing: X varies fastest, then Y. Strip flow bins.
            self._matrix = values.reshape(sizes[1] + 2, sizes[0] + 2)[1:-1, 1:-1].copy()
        self._matrix.setflags(write=False)
        self.res2, self.res1 = self._matrix.shape
        self.axis_units = {a: _axis_unit(label) for a, label in self.axis_labels.items()}
        self.is_symmetric = self.ndim == 2 and self.res1 == self.res2 and np.array_equal(self._matrix, self._matrix.T)

    def get_info(self):
        info = super().get_info()
        info.update(filename=self.url, source_url=self.url, root_entries=self.entries, histogram_title=self.title)
        return info


def list_http_histograms(server_url):
    """Traverse h.json hierarchy, including folders expanded lazily by ROOT."""
    base = normalize_url(server_url)
    result, visited = [], set()

    def walk(node, path, depth=0):
        if depth > 16 or len(visited) > 300:
            raise ValueError("ROOT hierarchy is too large; use a histogram URL directly")
        kind = str(node.get("_kind", ""))
        if kind.startswith("ROOT."):
            kind = kind[5:]
        if re.fullmatch(r"TH[123][CSIFDL]", kind):
            result.append({"name": path, "type": kind, "url": histogram_url(base + "/" + path)})
            return
        children = node.get("_childs", [])
        if not children and (node.get("_more") or kind in ("TFolder", "TDirectory", "TDirectoryFile")) and path not in visited:
            visited.add(path)
            expanded = read_json(normalize_url(base + "/" + path) + "/h.json?compact=3")
            children = expanded.get("_childs", [])
        for child in children:
            name = str(child.get("_name", ""))
            if name:
                walk(child, "/".join(p for p in (path, name) if p), depth + 1)

    walk(read_json(base + "/h.json?compact=3"), "")
    return sorted(result, key=lambda entry: entry["name"].lower())
