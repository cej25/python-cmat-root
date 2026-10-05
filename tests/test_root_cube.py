"""Sparse TH3 orientation, gating, calibration and live snapshot checks."""
import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from root_cube import ROOTCubeReader, sparse_array
from cmat3d import compute_3d_gate, compute_2d_banana_gate


def payload(cube):
    nz, ny, nx = cube.shape
    flow = np.full((nz+2, ny+2, nx+2), 999.)
    flow[1:-1,1:-1,1:-1] = cube
    return {'_typename':'TH3F', 'fName':'cube', 'fNcells':flow.size,
            'fXaxis':{'fNbins':nx,'fXmin':0,'fXmax':nx*2,'fTitle':'E1 [keV]'},
            'fYaxis':{'fNbins':ny,'fXmin':10,'fXmax':10+ny*3,'fTitle':'E2 [keV]'},
            'fZaxis':{'fNbins':nz,'fXmin':-5,'fXmax':-5+nz*.4,'fTitle':'dT [ns]'},
            'fArray':flow.ravel().tolist()}


class CubeTests(unittest.TestCase):
    def setUp(self):
        self.cube = (np.arange(4*3*2).reshape(4,3,2)+.25)
        self.h = payload(self.cube)
        self.r = ROOTCubeReader('sample.json', self.h)

    def test_planes_flow_and_calibration(self):
        for plane, axis in [('0-1',0),('0-2',1),('1-2',2)]:
            np.testing.assert_allclose(self.r.get_2d_plane(plane), self.cube.sum(axis=axis))
        self.assertEqual(self.r._total_counts, self.cube.sum())
        self.assertEqual(self.r.cal[2][0], -5)
        self.assertAlmostEqual(self.r.cal[2][0]+self.r.cal[2][1]*.5, -4.8)
        self.assertEqual(self.r.axis_units[2], 'ns')

    def test_time_window_and_regions(self):
        np.testing.assert_allclose(self.r.get_2d_plane('0-1', gate_3rd=(1,2)), self.cube[1:3].sum(axis=0))
        np.testing.assert_allclose(self.r.get_projection_for_region(2,'0-1',0,1,1,3), self.cube[:,1:3,0].sum(axis=1))
        np.testing.assert_allclose(self.r.get_projection_for_region(0,'0-1',0,1,1,3), self.cube[:,1:3,:].sum(axis=(0,1)))
        np.testing.assert_allclose(self.r.get_2d_plane('0-2',gate_3rd=(1,1)),self.cube[:,1,:])
        np.testing.assert_allclose(self.r.get_2d_plane('1-2',gate_3rd=(0,0)),self.cube[:,:,0])

    def test_double_gates_all_targets_and_background(self):
        for target in range(3):
            others = [ax for ax in range(3) if ax != target]
            specs = {ax:{'w':[[0,0]],'b':[[1,1]]} for ax in others}
            g = compute_3d_gate(self.r,target,specs)
            def region(a,b):
                slices = [slice(None)]*3
                slices[2-others[0]]=a; slices[2-others[1]]=b
                return self.cube[tuple(slices)]
            expected=region(0,0)-region(1,0)-region(0,1)+region(1,1)
            np.testing.assert_allclose(g['net_spec'],expected)
            np.testing.assert_allclose(g['raw_spec'],region(0,0))

    def test_single_gate_fractional(self):
        g=compute_3d_gate(self.r,2,{0:{'w':[[0,0]],'b':[]}})
        np.testing.assert_allclose(g['net_spec'],self.cube[:,:,0].sum(axis=1))

    def test_polygon_sparse_projection(self):
        g=compute_2d_banana_gate(self.r,'0-1',polygon_peak=[[0,0],[1,0],[1,3],[0,3]])
        np.testing.assert_allclose(g['net_spec'],self.cube[:,:,0].sum(axis=1))

    def test_fit_derived_cut_matches_dense_reference(self):
        from cmat3d import compute_2d_gamba_gate
        # Compare the new sparse path with the original dense operation.
        class Dense:
            res1, res2, res3 = self.r.shape
            def get_subvolume(inner, xr, yr, zr):
                return self.cube[zr[0]:zr[1], yr[0]:yr[1], xr[0]:xr[1]]
        for plane in ('0-1', '0-2', '1-2'):
            fit = {'success': True, 'centroid_x_ch': .5, 'centroid_y_ch': 1.5,
                   'fwhm_x_ch': 1, 'fwhm_y_ch': 1,
                   'roi_x_min': 0, 'roi_x_max': 1, 'roi_y_min': 0, 'roi_y_max': 2}
            sparse = compute_2d_gamba_gate(self.r, plane, fit)
            dense = compute_2d_gamba_gate(Dense(), plane, fit)
            np.testing.assert_allclose(sparse['net_spec'], dense['net_spec'])

    def test_compact_repetitions_and_rejections(self):
        idx,val=sparse_array({'$arr':'Float32','len':100,'p':5,'v':[.5,0,2],'p1':90,'v1':3,'n1':2},100)
        np.testing.assert_array_equal(idx,[5,7,90,91]);np.testing.assert_allclose(val,[.5,2,3,3])
        for a in [{'$arr':'Float32','len':100,'p':99,'v':1,'n':2}, {'$arr':'Float32','len':100,'v':float('nan')}]:
            with self.assertRaises(ValueError): sparse_array(a,100)

    def test_real_sample_if_present(self):
        sample=Path(__file__).resolve().parents[1]/'examples/sample_th3.json.gz'
        if not sample.exists():sample=Path(__file__).resolve().parents[2]/'upload/sample_th3.json.gz'
        if not sample.exists():self.skipTest('User sample not included in package')
        r=ROOTCubeReader(sample)
        self.assertEqual(r.shape,(500,500,1000));self.assertEqual(r._total_counts,6902)
        self.assertEqual(r._nonzero_voxels,5378)
        self.assertLess(r.coords.nbytes+r.values.nbytes+sum(a.nbytes for a in r.proj_2d.values()),11_000_000)
        for ax in range(3):self.assertEqual(r.get_projection(ax).sum(),6902)

    def test_viewer_http_tiles_and_time_fit(self):
        import urllib.request
        from cmat3d_webviewer import MatrixSession3D, CMAT3DWebHandler
        sess=MatrixSession3D({})
        entry={'reader':self.r,'name':'cube','filename':'cube','path':'sample.json',
               'shape':list(self.r.shape),'step':[1,1,1],'cal':self.r.cal,
               'total_counts':self.r._total_counts,'max_count':self.r._max_count,
               'nonzero_voxels':self.r._nonzero_voxels}
        sess.matrices.append(entry);CMAT3DWebHandler.session=sess
        server=HTTPServer(('127.0.0.1',0),CMAT3DWebHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            response=urllib.request.urlopen(url+'/api/tile?plane=0-2')
            self.assertEqual(response.headers['X-Data-Type'],'float64')
            self.assertEqual(np.frombuffer(response.read(),dtype=np.float64).sum(),self.cube.sum())
            active=json.load(urllib.request.urlopen(url+'/api/halflife/active_spectrum?axis=2'))
            self.assertEqual(active['x_unit'],'ns');self.assertAlmostEqual(active['x_energy'][0],-4.8)
            x=np.arange(100)*.4+.2
            data={'x':x.tolist(),'y':(400*np.exp(-np.log(2)*x/5)+3).tolist(),
                  'model':'exponential','x_unit':'ns','x_label':'dT [ns]',
                  't12':5,'centroid':0,'scale':400,'bg':3,'freepars':[True,False,False,True,True]}
            request=urllib.request.Request(url+'/api/halflife/fit',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
            fit=json.load(urllib.request.urlopen(request))
            self.assertEqual(fit['model'],'exponential');self.assertEqual(fit['x_unit'],'ns')
            self.assertAlmostEqual(fit['t12'],5,places=2)
        finally:server.shutdown();server.server_close();thread.join()

    def test_live_http_pause_failure_axis_change_reset(self):
        from cmat3d_webviewer import MatrixSession3D
        state={'h':self.h,'fail':False}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if state['fail']:self.send_error(503);return
                body=json.dumps(state['h']).encode();self.send_response(200);self.end_headers();self.wfile.write(body)
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            sess=MatrixSession3D({});sess.add_root_cube(f'http://127.0.0.1:{server.server_port}/h/root.json.gz')
            m=sess.get_active_matrix();m['live']['paused']=True
            state['h']=payload(self.cube*2);sess.refresh_root_cube();self.assertEqual(m['live']['generation'],0)
            sess.refresh_root_cube(force=True);self.assertEqual(m['total_counts'],self.cube.sum()*2)
            good=m['reader'];state['fail']=True;sess.refresh_root_cube(force=True)
            self.assertIs(m['reader'],good);self.assertTrue(m['live']['error'])
            state['fail']=False;state['h']=copy.deepcopy(self.h);state['h']['fZaxis']['fXmax']+=1
            sess.refresh_root_cube(force=True);self.assertIs(m['reader'],good)
            state['h']=payload(self.cube*0);sess.refresh_root_cube(force=True)
            self.assertEqual(m['total_counts'],0);self.assertIsNone(m['live']['error'])
        finally:server.shutdown();server.server_close();thread.join()

if __name__ == '__main__':unittest.main()
