import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import csat_core as core  # noqa: E402

SAMPLE = os.path.join(ROOT, "cti-unc3386-2026.yaml")


def ach(hyps, evid, matrix, rel=None):
    return core.normalize({"ach": {
        "hypotheses": [{"label": h} for h in hyps],
        "evidence": [{"description": e, "reliability": (rel or {}).get(i, "A")} for i, e in enumerate(evid)],
        "matrix": matrix,
    }})["ach"]


class TestACH(unittest.TestCase):
    def test_least_inconsistent_wins_not_most_confirming(self):
        # H1 has more support but one strong inconsistency; H2 has none.
        a = core.analyze_ach(ach(["H1", "H2"], ["e1", "e2", "e3"],
                                 {"0_0": "CC", "0_1": "C", "1_0": "CC", "1_1": "C", "2_0": "II", "2_1": "N"}))
        self.assertEqual(a["leader"], 1)

    def test_unscored_hypothesis_cannot_win(self):
        a = core.analyze_ach(ach(["H1", "H2"], ["e1"], {"0_0": "I", "0_1": "N"}))
        self.assertEqual(a["unscored"], [1])
        self.assertEqual(a["leader"], 0)

    def test_reliability_weighting(self):
        # Same inconsistency, but from an unconfirmed (D) source vs confirmed (A)
        m = {"0_0": "I", "0_1": "N", "1_0": "N", "1_1": "I"}
        a = core.analyze_ach(ach(["H1", "H2"], ["e1", "e2"], m, rel={0: "D", 1: "A"}))
        self.assertEqual(a["leader"], 0)

    def test_sensitivity_reindexes_evidence(self):
        # Removing e0 must re-index e1/e2 correctly (old code read the wrong cells).
        m = {"0_0": "II", "0_1": "N", "1_0": "C", "1_1": "I", "2_0": "C", "2_1": "C"}
        a = core.analyze_ach(ach(["H1", "H2"], ["e0", "e1", "e2"], m))
        self.assertEqual(a["leader"], 1)
        self.assertEqual(a["fragile"], [0])

    def test_diagnosticity(self):
        m = {"0_0": "C", "0_1": "C", "1_0": "N", "1_1": "N", "2_0": "CC", "2_1": "II"}
        a = core.analyze_ach(ach(["H1", "H2"], ["same", "none", "diag"], m))
        self.assertEqual([e["diagnosticity"] for e in a["evidence"]], ["weak", "none", "high"])

    def test_not_ready(self):
        self.assertFalse(core.analyze_ach(ach(["H1"], ["e"], {}))["ready"])


class TestOthers(unittest.TestCase):
    def test_kac_critical(self):
        s = core.normalize({"kac": {"assumptions": [{"text": "a", "certainty": 2, "impact": 4},
                                                    {"text": "b", "certainty": 3, "impact": 5}]}})
        self.assertEqual(core.analyze_kac(s["kac"])["critical"], [0])

    def test_iw_refute_caps(self):
        s = core.normalize({"iw": {"scenarios": [{"label": "x", "indicators": [
            {"text": "c", "type": "CONFIRM", "observed": "YES"},
            {"text": "r", "type": "REFUTE", "observed": "YES"}]}]}})
        r = core.analyze_iw(s["iw"])["scenarios"][0]
        self.assertEqual(r["status"], "REFUTED")
        self.assertLessEqual(r["pct"], 24)

    def test_iw_without_observed_key(self):
        s = core.normalize({"iw": {"scenarios": [{"label": "x", "indicators": [{"text": "c", "type": "CONFIRM"}]}]}})
        self.assertEqual(s["iw"]["scenarios"][0]["indicators"][0]["observed"], "UNKNOWN")

    def test_da_single_strong_argument_is_unresolved_not_fatal(self):
        s = core.normalize({"da": {"challenges": [{"area": "False Flag", "argument": "x", "strength": 5}]}})
        self.assertEqual(core.analyze_da(s["da"])["verdict"], "UNRESOLVED CHALLENGES")


class TestSession(unittest.TestCase):
    def test_normalize_garbage(self):
        s = core.normalize({"meta": None, "ach": "x", "iw": {"s1_label": "legacy"}})
        self.assertEqual(s["meta"]["tlp"], "CLEAR")
        self.assertEqual(s["iw"]["scenarios"][0]["label"], "legacy")
        self.assertEqual(len(s["da"]["challenges"]), 6)

    def test_leading_hypothesis_strings(self):
        mk = lambda v: core.normalize({"ach": {"hypotheses": [{}, {}],
                                               "conclusion": {"leading_hypothesis": v}}})["ach"]["conclusion"]["leading_hypothesis"]
        self.assertEqual(mk("H2"), 1)
        self.assertEqual(mk("1"), 1)
        self.assertIsNone(mk("H9"))

    def test_sample_roundtrip_and_report(self):
        s = core.load_session(SAMPLE)
        again = core.load_session_text(core.dump_session(s))
        self.assertEqual(again["ach"]["matrix"], s["ach"]["matrix"])
        md = core.generate_report(s)
        for part in ("Bottom Line", "ACH", "KAC", "I&W", "Devil's Advocacy", "fragile"):
            self.assertIn(part, md)
        self.assertIn("<table>", core.report_html(s))

    def test_md_table_escapes_pipes(self):
        s = core.normalize({"kac": {"assumptions": [{"text": "a | b"}]}})
        self.assertIn("a \\| b", core.generate_report(s))


if __name__ == "__main__":
    unittest.main()
