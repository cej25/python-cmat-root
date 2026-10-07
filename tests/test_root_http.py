"""ROOT wire-format and real HTTP integration checks; no live c4Root needed."""
import base64
import json
import sys
import threading
import unittest
from http.server import HTTPServer, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from root_http import ROOTHTTPReader, decode_array, histogram_url, list_http_histograms, read_json, infer_server_url
from live_root_demo import DemoHandler, DemoState, histogram_payload
from cmat_webviewer import CMATSession, CMATWebHandler, DEFAULT_CONFIG


class ArrayTests(unittest.TestCase):
    def test_compact_runs_and_implicit_cursor(self):
        encoded = {"$arr":"Float32", "len":14, "p":2, "v":1.25, "n":3,
                   "v1":[2, 3], "p2":10, "v2":-0.5}
        np.testing.assert_array_equal(decode_array(encoded), [0,0,1.25,1.25,1.25,2,3,0,0,0,-0.5,0,0,0])

    def test_base64_offset(self):
        block = np.array([1.25, 2.5], dtype="<f4").tobytes()
        np.testing.assert_array_equal(decode_array({"$arr":"Float32", "len":5, "o":4,
            "b":base64.b64encode(block).decode()}), [0,1.25,2.5,0,0])

    def test_flow_bins_and_orientation(self):
        matrix = np.array([[1.25, 2, 3], [4, 5, 6]])
        h = histogram_payload(matrix, "test", (10,16), (-5,5))
        flow = np.pad(matrix, 1, constant_values=999)
        h["fArray"] = flow.ravel().tolist()
        reader = ROOTHTTPReader("http://localhost/test/root.json", h)
        np.testing.assert_array_equal(reader.to_numpy(), matrix)
        np.testing.assert_array_equal(reader.get_projection(0), [5.25,7,9])
        self.assertEqual(reader.cal, {0:[10,2,0], 1:[-5,5,0]})
        self.assertFalse(reader.to_numpy().flags.writeable)

    def test_invalid_lengths_and_blocks(self):
        for value in ([1,2], {"$arr":"Float32", "len":3, "p":2, "v":1, "n":5}):
            with self.assertRaises(ValueError):
                decode_array(value, 3)

    def test_zero_large_rectangular_histogram(self):
        h = histogram_payload(np.zeros((2000,1000)), "lisa", (0,1000), (0,2000))
        self.assertEqual(h["fNcells"], 2006004)
        reader = ROOTHTTPReader("http://localhost/lisa", h)
        self.assertEqual(reader.to_numpy().shape, (2000,1000))
        self.assertEqual(reader.to_numpy().sum(), 0)

    def test_reject_nonuniform_bins(self):
        h = histogram_payload(np.ones(3), "test")
        h["fXaxis"]["fXbins"] = [0,1,3,6]
        with self.assertRaises(ValueError):
            ROOTHTTPReader("http://localhost/test", h)

    def test_url_normalization(self):
        self.assertEqual(histogram_url("http://localhost:1111/Histograms/Fast Vs. Slow/test/root.json.gz?compact=23"),
                         "http://localhost:1111/Histograms/Fast%20Vs.%20Slow/test/root.json?compact=23")

    def test_server_url_inference(self):
        self.assertEqual(infer_server_url("http://localhost:1111/Histograms/Demo/h1/root.json"), "http://localhost:1111")
        self.assertEqual(infer_server_url("https://host/root.app/Objects/Histograms/h1/root.json.gz"), "https://host/root.app")


class FixtureHandler(DemoHandler):
    fail = False
    lazy = False

    def do_GET(self):
        if self.fail:
            self.send_error(503, "Test source disconnected")
            return
        if self.lazy and self.path.startswith("/h.json"):
            body = json.dumps({"_name":"ROOT", "_childs":[{"_name":"Histograms", "_more":True}]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
            return
        if self.lazy and self.path.startswith("/Histograms/h.json"):
            body = json.dumps({"_name":"Histograms", "_childs":[{"_name":"Demo", "_childs":[
                {"_name":"h1_energy", "_kind":"ROOT.TH1F"}]}]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FixtureHandler.state = DemoState()
        cls.source = ThreadingHTTPServer(("127.0.0.1",0), FixtureHandler)
        cls.viewer = HTTPServer(("127.0.0.1",0), CMATWebHandler)
        cls.base = "http://127.0.0.1:" + str(cls.source.server_port)
        cls.app = "http://127.0.0.1:" + str(cls.viewer.server_port)
        for server in (cls.source, cls.viewer):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for server in (cls.viewer, cls.source):
            server.shutdown()
            server.server_close()

    def setUp(self):
        FixtureHandler.fail = FixtureHandler.lazy = False
        FixtureHandler.state = DemoState()
        CMATWebHandler.session = CMATSession()
        CMATWebHandler.config = DEFAULT_CONFIG
        CMATWebHandler.reader = CMATWebHandler.matrix = None
        CMATWebHandler.sync_class_attrs()

    def post(self, endpoint, data=None):
        req = Request(self.app + endpoint, data=json.dumps(data or {}).encode(),
                      headers={"Content-Type":"application/json"})
        with urlopen(req) as response:
            return json.load(response)

    def connect(self, name="h2_coincidences"):
        return self.post("/api/live_connect", {"url":self.base + "/Histograms/Demo/" + name + "/root.json", "interval":1})

    def test_browse_full_and_lazy_hierarchies(self):
        items = list_http_histograms(self.base)
        self.assertEqual(len(items), 2)
        FixtureHandler.lazy = True
        items = list_http_histograms(self.base)
        self.assertEqual(items[0]["name"], "Histograms/Demo/h1_energy")

    def test_browser_address_survives_selection_and_failed_browse(self):
        with urlopen(self.app + "/api/live_histograms?" + urlencode({"url":self.base})) as response:
            listing = json.load(response)
        self.assertEqual(len(listing["details"]), 2)
        self.assertEqual(listing["server_url"], self.base)
        result = self.connect("h1_energy")
        self.assertEqual(result["metadata"]["live_browser_url"], self.base)
        result = self.connect("h2_coincidences")
        self.assertEqual(result["metadata"]["live_browser_url"], self.base)
        self.assertEqual(len(result["metadata"]["matrices"]), 2)
        FixtureHandler.fail = True
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError):
            urlopen(self.app + "/api/live_histograms?" + urlencode({"url":self.base}))
        with urlopen(self.app + "/api/metadata") as response:
            self.assertEqual(json.load(response)["live_browser_url"], self.base)

    def test_gzip_transport(self):
        payload = read_json(self.base + "/Histograms/Demo/h1_energy/root.json.gz?compact=23")
        self.assertEqual(payload["_typename"], "TH1F")

    def test_refresh_pause_disconnect_reconnect(self):
        self.connect()
        old = CMATWebHandler.matrix.copy()
        FixtureHandler.state.fill()
        result = self.post("/api/live_refresh")
        self.assertTrue(result["changed"])
        self.assertGreater(result["metadata"]["total_counts"], old.sum())
        self.post("/api/live_control", {"paused":True})
        FixtureHandler.state.fill()
        self.assertFalse(self.post("/api/live_refresh")["changed"])
        self.assertTrue(self.post("/api/live_refresh", {"force":True})["changed"])
        self.post("/api/live_control", {"paused":False})
        good = CMATWebHandler.matrix.copy()
        FixtureHandler.fail = True
        result = self.post("/api/live_refresh")
        self.assertFalse(result["metadata"]["live"]["connected"])
        np.testing.assert_array_equal(CMATWebHandler.matrix, good)
        FixtureHandler.fail = False
        FixtureHandler.state.fill()
        result = self.post("/api/live_refresh")
        self.assertTrue(result["metadata"]["live"]["connected"])
        self.assertTrue(result["changed"])

    def test_changed_axes_keep_old_snapshot_until_reconnect(self):
        self.connect()
        old = CMATWebHandler.matrix
        FixtureHandler.state.matrix = np.zeros((12,24))
        result = self.post("/api/live_refresh")
        self.assertIn("axes changed", result["metadata"]["live"]["error"])
        self.assertIs(CMATWebHandler.matrix, old)
        result = self.connect()
        self.assertEqual(result["metadata"]["shape"], [24,12])

    def test_tile_preserves_fractional_counts(self):
        FixtureHandler.state.matrix[10,20] = 1.25
        self.connect()
        with urlopen(self.app + "/api/tile?x0=20&x1=21&y0=10&y1=11") as response:
            self.assertEqual(response.headers["X-Data-Type"], "float64")
            self.assertEqual(response.headers["X-Data-Revision"], "1")
            self.assertEqual(np.frombuffer(response.read(), dtype="<f8")[0], 1.25)

    def test_gate_and_fit_update_after_refresh(self):
        self.connect()
        gate_url = self.app + "/api/gate_1d?" + urlencode({"axis":0, "w_gates":"[[75,85]]", "b_gates":"[[55,65]]"})
        with urlopen(gate_url) as response:
            first = json.load(response)
        FixtureHandler.state.fill()
        self.post("/api/live_refresh")
        with urlopen(gate_url) as response:
            second = json.load(response)
        self.assertGreater(second["net_counts"], first["net_counts"])
        # Reuse the existing fitting endpoint on the live gated projection.
        fit_url = self.app + "/api/fit_peak?" + urlencode({"axis":1, "channel":100,
                     "w_gates":"[[75,85]]", "b_gates":"[[55,65]]"})
        with urlopen(fit_url) as response:
            fit = json.load(response)
        self.assertTrue(fit.get("success"), fit)

    def test_live_1d_physical_axis_and_projection(self):
        result = self.connect("h1_energy")
        self.assertTrue(result["metadata"]["is_1d"])
        self.assertEqual(result["metadata"]["cal_0"], [0,4,0])
        np.testing.assert_array_equal(CMATWebHandler.session.get_spectrum(0), FixtureHandler.state.spectrum)

    def test_histogram_reset_is_a_new_snapshot(self):
        self.connect()
        FixtureHandler.state.matrix[:] = 0
        result = self.post("/api/live_refresh")
        self.assertTrue(result["changed"])
        self.assertEqual(result["metadata"]["total_counts"], 0)
        self.assertTrue(result["metadata"]["live"]["connected"])


if __name__ == "__main__":
    unittest.main()
