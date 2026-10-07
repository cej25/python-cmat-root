"""Sparse ROOT TH3 snapshots implementing the CMAT3D projection interface.

ROOT global bins are X-fastest, then Y, then Z, including flow bins.
Only populated regular bins are retained; no dense cube is allocated.
"""
import base64
import gzip
import json
from pathlib import Path
import numpy as np
from cmat3d import CMAT3DReader
from root_http import read_json, histogram_url, MAX_BYTES
from root_matrix import _axis_unit, _linear_calibration

MAX_POPULATED = 10_000_000


def sparse_array(value, expected):
    if isinstance(value, dict) and 'fArray' in value:
        value = value['fArray']
    indices, values = [], []
    populated = 0
    def append(start, block):
        nonlocal populated
        block = np.asarray(block, dtype=np.float64).reshape(-1)
        if start < 0 or start + block.size > expected or not np.all(np.isfinite(block)):
            raise ValueError('Invalid ROOT TH3 bin block')
        keep = np.flatnonzero(block)
        populated += keep.size
        if populated > MAX_POPULATED:
            raise ValueError('TH3 exceeds 10 million populated bins; use coarser binning or server-side projections')
        indices.append(keep.astype(np.int64) + start)
        values.append(block[keep])
    if isinstance(value, list):
        if len(value) != expected:
            raise ValueError('TH3 array length does not match axes')
        append(0, value)
    elif isinstance(value, dict) and '$arr' in value:
        if int(value.get('len', -1)) != expected:
            raise ValueError('TH3 array length does not match axes')
        if 'b' in value:
            types = {'Float32':'<f4', 'Float64':'<f8', 'Int32':'<i4', 'Int16':'<i2', 'Int8':'i1',
                     'Uint8':'u1', 'Uint16':'<u2', 'Uint32':'<u4', 'Int64':'<i8', 'Uint64':'<u8'}
            dtype = np.dtype(types[value['$arr']])
            offset = int(value.get('o', 0))
            if offset < 0 or offset % dtype.itemsize:
                raise ValueError('Invalid TH3 base64 offset')
            append(offset // dtype.itemsize, np.frombuffer(base64.b64decode(value['b'], validate=True), dtype=dtype))
        else:
            cursor, i = 0, 0
            while True:
                suffix = '' if i == 0 else str(i)
                if 'v' + suffix not in value:
                    break
                start = int(value.get('p' + suffix, cursor))
                block = value['v' + suffix]
                count = len(block) if isinstance(block, list) else int(value.get('n' + suffix, 1))
                if start < cursor or count < 1 or start + count > expected:
                    raise ValueError('Invalid compact TH3 block')
                if isinstance(block, list):
                    append(start, block)
                elif float(block) != 0:
                    if count > MAX_POPULATED - populated:
                        raise ValueError('TH3 exceeds populated-bin limit')
                    append(start, np.full(count, block))
                elif not np.isfinite(float(block)):
                    raise ValueError('Non-finite TH3 bins')
                cursor = start + count
                i += 1
    else:
        raise ValueError('Unsupported TH3 array encoding')
    return (np.concatenate(indices) if indices else np.empty(0, dtype=np.int64),
            np.concatenate(values) if values else np.empty(0, dtype=np.float64))


class ROOTCubeReader(CMAT3DReader):
    def __init__(self, source, payload=None):
        self.source = str(source)
        self.is_live = self.source.startswith(('http://', 'https://'))
        if payload is None:
            if self.is_live:
                payload = read_json(histogram_url(source), timeout=15)
            else:
                opener = gzip.open if self.source.endswith('.gz') else open
                with opener(source, 'rt') as stream:
                    text = stream.read(MAX_BYTES + 1)
                if len(text) > MAX_BYTES:
                    raise ValueError('TH3 JSON exceeds 256 MiB')
                payload = json.loads(text)
        if payload.get('_typename') not in ('TH3C', 'TH3S', 'TH3I', 'TH3F', 'TH3D', 'TH3L'):
            raise ValueError('Expected a regular ROOT TH3 histogram')
        self.object_name = payload.get('fName', 'TH3')
        self.filename = Path(self.object_name if self.is_live else source)
        self.ndim = 3
        sizes_xyz, self.cal, self.axis_labels = [], {}, {}
        self.axis_edges = []
        for axis, name in enumerate('XYZ'):
            a = payload['f' + name + 'axis']
            size = int(a['fNbins'])
            if size < 1 or size > 100_000:
                raise ValueError('Invalid TH3 axis bin count')
            variable = a.get('fXbins', [])
            if isinstance(variable, dict):
                variable = variable.get('fArray', variable.get('len', 0))
            if variable:
                raise ValueError('TH3 currently requires uniform bins')
            edges = np.linspace(float(a['fXmin']), float(a['fXmax']), size + 1)
            coeff = _linear_calibration(edges, name)
            if coeff[1] <= 0:
                raise ValueError('TH3 axes must increase')
            self.cal[axis] = coeff
            self.axis_labels[axis] = a.get('fTitle') or 'ROOT ' + name + ' coordinate'
            self.axis_edges.append((size, float(edges[0]), float(edges[-1])))
            sizes_xyz.append(size)
        self.res1, self.res2, self.res3 = sizes_xyz
        self.axis_units = {ax: ("keV" if "kev" in label.lower() else "MeV" if "mev" in label.lower() else _axis_unit(label)) for ax, label in self.axis_labels.items()}
        sizes = np.asarray(self.shape, dtype=np.int64) + 2
        expected = int(np.prod(sizes))
        if int(payload.get('fNcells', -1)) != expected:
            raise ValueError('TH3 cell count does not match axes')
        idx, vals = sparse_array(payload['fArray'], expected)
        coords = np.column_stack((idx % sizes[0], (idx // sizes[0]) % sizes[1], idx // (sizes[0]*sizes[1]))) - 1
        keep = np.all((coords >= 0) & (coords < np.asarray(self.shape)), axis=1)
        self.coords, self.values = coords[keep], vals[keep]
        self.coords.flags.writeable = self.values.flags.writeable = False
        self._total_counts = float(self.values.sum())
        self._max_count = float(self.values.max()) if len(self.values) else 0.0
        self._nonzero_voxels = len(self.values)
        self.step1 = self.step2 = self.step3 = 1
        self.ndiv1, self.ndiv2, self.ndiv3 = self.shape
        self.is_sparse_mode = True
        self.memmap_3d = None
        self.proj_2d = {plane: self.get_2d_plane(plane) for plane in ('0-1', '0-2', '1-2')}

    @staticmethod
    def plane_axes(plane):
        return {'0-1': (0,1,2), '0-2': (0,2,1), '1-2': (1,2,0)}[plane]

    def project_masks(self, target_axis, masks):
        keep = np.ones(len(self.values), dtype=bool)
        for axis, mask in masks.items():
            keep &= np.asarray(mask, dtype=bool)[self.coords[:, axis]]
        return np.bincount(self.coords[keep, target_axis], weights=self.values[keep], minlength=self.shape[target_axis])

    def get_projection(self, axis=0):
        return self.project_masks(axis, {})

    def _range_masks(self, axis_ranges):
        masks = {}
        for ax, ranges in axis_ranges.items():
            mask = np.zeros(self.shape[ax], dtype=bool)
            for lo, hi in ranges:
                mask[max(0, int(lo)):min(self.shape[ax], int(hi))] = True
            masks[ax] = mask
        return masks

    def _sum_projection_region(self, axis, axis_ranges):
        return self.project_masks(axis, self._range_masks(axis_ranges))

    def get_projection_for_region(self, axis, plane='0-1', x0=0, x1=None, y0=0, y1=None,
                                  gate_3rd=None, gates_3rd=None):
        ax, ay, az = self.plane_axes(plane)
        ranges = {ax: [(x0, self.shape[ax] if x1 is None else x1)],
                  ay: [(y0, self.shape[ay] if y1 is None else y1)]}
        # The displayed axes project across their full own range.
        if axis in (ax, ay):
            ranges.pop(axis)
        gates = ([gate_3rd] if gate_3rd is not None else []) + list(gates_3rd or [])
        if gates and axis != az:
            ranges[az] = [(min(lo, hi), max(lo, hi)+1) for lo, hi in gates]
        return self._sum_projection_region(axis, ranges)

    def get_2d_plane(self, plane='0-1', gate_3rd=None, gates_3rd=None, x0=None, x1=None, y0=None, y1=None):
        ax, ay, az = self.plane_axes(plane)
        x0, y0 = max(0, int(x0 or 0)), max(0, int(y0 or 0))
        x1 = min(self.shape[ax], int(x1 if x1 is not None else self.shape[ax]))
        y1 = min(self.shape[ay], int(y1 if y1 is not None else self.shape[ay]))
        if x1 <= x0 or y1 <= y0:
            raise ValueError('Empty TH3 display region')
        if (x1-x0)*(y1-y0) > 10_000_000:
            raise ValueError('TH3 plane exceeds 10 million pixels')
        c = self.coords
        keep = (c[:,ax]>=x0)&(c[:,ax]<x1)&(c[:,ay]>=y0)&(c[:,ay]<y1)
        gates = ([gate_3rd] if gate_3rd is not None else []) + list(gates_3rd or [])
        if gates:
            selected = np.zeros(len(c), dtype=bool)
            for lo, hi in gates:
                selected |= (c[:,az]>=min(lo,hi)) & (c[:,az]<=max(lo,hi))
            keep &= selected
        flat = (c[keep,ay]-y0)*(x1-x0) + c[keep,ax]-x0
        return np.bincount(flat, weights=self.values[keep], minlength=(x1-x0)*(y1-y0)).reshape(y1-y0,x1-x0)

    def project_polygon_mask(self, plane, mask, x_min, y_min):
        ax, ay, az = self.plane_axes(plane)
        x, y = self.coords[:,ax]-x_min, self.coords[:,ay]-y_min
        keep = (x>=0)&(x<mask.shape[1])&(y>=0)&(y<mask.shape[0])
        ids = np.flatnonzero(keep)
        ids = ids[mask[y[ids],x[ids]]]
        return np.bincount(self.coords[ids,az], weights=self.values[ids], minlength=self.shape[az])
