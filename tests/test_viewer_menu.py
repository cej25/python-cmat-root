"""Same-port ROOT histogram menu routing and mounted 3D popup checks."""
import json
import sys
import threading
import unittest
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from root_http import list_http_histograms
from cmat_webviewer import CMATSession, CMATWebHandler
from live_root_demo import histogram_payload
from test_root_cube import payload


class MenuTests(unittest.TestCase):
    def test_th1_th2_th3_navigation_and_popup_mount(self):
        h3=payload(np.ones((4,3,2)))
        h1=histogram_payload(np.ones(5),'energy')
        h2=histogram_payload(np.ones((3,5)),'coincidences')
        state={'fail':False}
        class ROOTServer(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path.startswith('/h.json'):
                    data={'_childs':[{'_name':'Histograms','_childs':[
                        {'_name':name,'_kind':'ROOT.'+hist['_typename']} for name,hist in [('energy',h1),('matrix',h2),('cube',h3)]]}]}
                elif '/cube/' in self.path:
                    if state['fail']:self.send_error(503);return
                    data=h3
                elif '/matrix/' in self.path:data=h2
                else:data=h1
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(data).encode())
        root=HTTPServer(('127.0.0.1',0),ROOTServer);rt=threading.Thread(target=root.serve_forever,daemon=True);rt.start()
        session=CMATSession({});old_session=CMATWebHandler.session
        CMATWebHandler.session=session;CMATWebHandler.sync_class_attrs()
        viewer=HTTPServer(('127.0.0.1',0),CMATWebHandler);vt=threading.Thread(target=viewer.serve_forever,daemon=True);vt.start()
        root_url=f'http://127.0.0.1:{root.server_port}';base=f'http://127.0.0.1:{viewer.server_port}'
        def post(path,data):
            return json.load(urlopen(Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})))
        try:
            entries=list_http_histograms(root_url);self.assertEqual({e['type'] for e in entries},{'TH1F','TH2F','TH3F'})
            bytype={e['type']:e for e in entries}
            def select(kind,route='/api/live_connect'):
                entry=bytype[kind]
                return post(route,{'url':entry['url'],'type':kind,'server_url':root_url,'interval':2})
            r=select('TH1F');self.assertTrue(r['metadata']['is_1d']);self.assertEqual(r['metadata']['source_format'],'ROOT')
            r=select('TH3F');self.assertEqual(r['viewer_url'],'/cube/')
            metadata=json.load(urlopen(base+'/cube/api/metadata'))
            self.assertTrue(metadata['mounted_browser']);self.assertTrue(metadata['root_cube'])
            body=urlopen(base+'/cube/').read().decode();self.assertIn('const prefix = "/cube"',body)
            self.assertIn('backToHistogramBrowser',body)
            for route in ('/cube/halflife_popup.html','/cube/isotope_search'):
                body=urlopen(base+route).read().decode();self.assertIn('const prefix = "/cube"',body)
            r=post('/cube/api/halflife/fit',{'x':[0,1,2,3,4,5],'y':[80,40,20,10,5,2.5],
                   'model':'exponential','t12':1,'centroid':0,'scale':80,'bg':0,
                   'x_label':'Time [ns]','x_unit':'ns','freepars':[True,False,False,False,False]})
            self.assertEqual(r['model'],'exponential');self.assertEqual(r['x_unit'],'ns')
            self.assertEqual(len(json.load(urlopen(base+'/cube/api/live_histograms?url='+root_url))['details']),3)
            tile=urlopen(base+'/cube/api/tile?plane=0-1');self.assertEqual(tile.headers['X-Data-Type'],'float64')
            self.assertEqual(np.frombuffer(tile.read(),dtype=np.float64).sum(),24)
            self.assertEqual(json.load(urlopen(base+'/cube/api/live_refresh'))['live']['generation'],1)
            select('TH3F');self.assertEqual(len(session.cube_session.matrices),1)
            state['fail']=True
            with self.assertRaises(Exception):select('TH3F')
            self.assertEqual(session.cube_session.get_active_matrix()['total_counts'],24)
            state['fail']=False
            r=select('TH2F','/cube/api/live_connect');self.assertEqual(r['viewer_url'],'/')
            self.assertFalse(r['metadata']['is_1d']);self.assertEqual(r['metadata']['shape'],[5,3])
            # Returning to TH1 keeps the same catalog and server address.
            r=select('TH1F');self.assertTrue(r['metadata']['is_1d']);self.assertEqual(r['metadata']['live_browser_url'],root_url)
        finally:
            viewer.shutdown();viewer.server_close();vt.join()
            root.shutdown();root.server_close();rt.join()
            CMATWebHandler.session=old_session
            if old_session is not None:CMATWebHandler.sync_class_attrs()

if __name__=='__main__':unittest.main()
