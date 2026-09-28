"""Read ROOT TH1/TH2 histograms into the viewer's matrix interface."""

from pathlib import Path

import numpy as np


def split_matrix_spec(spec):
    """Return (filesystem path, optional ROOT object name)."""
    value = str(spec)
    marker = value.lower().find(".root::")
    if marker < 0:
        return Path(value).expanduser(), None
    return Path(value[:marker + 5]).expanduser(), value[marker + 7:]


def matrix_spec(path, object_name=None):
    path = Path(path).expanduser().resolve()
    return f"{path}::{object_name}" if object_name else str(path)


def _open_root(path):
    try:
        import uproot
    except ImportError as exc:
        raise ImportError("ROOT input requires uproot: pip install uproot") from exc
    return uproot.open(path)


def list_root_histograms(path):
    """List supported TH1/TH2 objects, including subdirectories."""
    with _open_root(path) as root_file:
        return sorted(k for k, cls in root_file.classnames(recursive=True, cycle=False).items()
                      if (cls.startswith("TH1") or cls.startswith("TH2"))
                      and not cls.startswith("TH2Poly"))


def _linear_calibration(edges, axis):
    widths = np.diff(edges)
    if len(widths) == 0 or not np.all(np.isfinite(edges)) or not np.allclose(widths, widths[0]):
        raise ValueError(f"ROOT histogram {axis} axis must have uniform finite bin widths")
    # Viewer bin centers are evaluated at channel + 0.5.
    return [float(edges[0]), float(widths[0]), 0.0]


class ROOTMatrixReader:
    """Adapter for ROOT histograms; TH1 uses a single-row matrix."""

    def __init__(self, filename, object_name=None):
        self.filename = Path(filename).expanduser().resolve()
        if object_name is None:
            names = list_root_histograms(self.filename)
            if len(names) != 1:
                raise ValueError(
                    f"{self.filename.name} has {len(names)} TH1/TH2 histograms; select one with "
                    "'file.root::directory/histogram'. Available: " + ", ".join(names[:30])
                )
            object_name = names[0]
        self.object_name = object_name
        with _open_root(self.filename) as root_file:
            try:
                hist = root_file[object_name]
            except KeyError as exc:
                raise ValueError(f"ROOT histogram {object_name!r} not found in {self.filename}") from exc
            if hist.classname.startswith("TH1"):
                values, x_edges = hist.to_numpy(flow=False)
                self.ndim = 1
                self.cal = {0: _linear_calibration(x_edges, "X")}
                self._matrix = np.asarray(values)[np.newaxis, :]
            elif hist.classname.startswith("TH2") and not hist.classname.startswith("TH2Poly"):
                values, x_edges, y_edges = hist.to_numpy(flow=False)
                self.ndim = 2
                self.cal = {0: _linear_calibration(x_edges, "X"),
                            1: _linear_calibration(y_edges, "Y")}
                # Uproot indexes TH2 values [X, Y]; the viewer uses [Y, X].
                self._matrix = np.asarray(values.T)
            else:
                raise ValueError(f"{object_name!r} is {hist.classname}, expected TH1 or TH2")
        self.res2, self.res1 = self._matrix.shape
        self.is_symmetric = (self.ndim == 2 and self.res1 == self.res2 and
                             np.array_equal(self._matrix, self._matrix.T))

    def to_numpy(self):
        return self._matrix

    def get_projection(self, axis=0):
        return np.sum(self._matrix, axis=0 if axis == 0 else 1, dtype=np.float64)

    def get_info(self):
        return {"filename": str(self.filename), "dimensions": self.ndim,
                "shape": (self.res1, self.res2), "shape_yx": (self.res2, self.res1),
                "matrix_mode": "Symmetric" if self.is_symmetric else "Normal",
                "root_histogram": self.object_name}
