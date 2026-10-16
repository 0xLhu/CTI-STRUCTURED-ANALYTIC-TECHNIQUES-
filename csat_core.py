"""
csat_core.py: Session model, scoring and report generation for CSAT.

Pure logic, no terminal / network I/O. Shared by the GUI (csat_gui.py)
and the interactive CLI (csat_cli.py).
"""

import datetime
import html
import re
from copy import deepcopy

import yaml


# ── CONSTANTS ──────────────────────────────────────────────────────────────

CONSISTENCY = {
    "CC": {"label": "Very consistent",     "value": 2},
    "C":  {"label": "Consistent",          "value": 1},
    "N":  {"label": "Neutral / N/A",       "value": 0},
    "I":  {"label": "Inconsistent",        "value": -1},
    "II": {"label": "Very inconsistent",   "value": -2},
}

# Source reliability weights (Admiralty-style A-D). Heuer: weight evidence by
# credibility so a single shaky report cannot eliminate a hypothesis on its own.
RELIABILITY = {
    "A": {"label": "Confirmed",       "weight": 1.0},
    "B": {"label": "Probably true",   "weight": 0.8},
    "C": {"label": "Possibly true",   "weight": 0.6},
    "D": {"label": "Unconfirmed",     "weight": 0.4},
}

CONFIDENCE_LEVELS = [
    (75, 100, "HIGH",    "Strong evidence base. Attribution supportable with documented caveats."),
    (50,  74, "MEDIUM",  "Reasonable basis. Additional collection required before dissemination."),
    (25,  49, "LOW",     "Working hypothesis. Not suitable for dissemination."),
    (0,   24, "MINIMAL", "Insufficient evidence. Analytical speculation only."),
]

TLP_LEVELS = ["CLEAR", "GREEN", "AMBER", "AMBER+STRICT", "RED"]
TLP_ALIASES = {"WHITE": "CLEAR"}  # TLP 1.0 → 2.0

IW_TYPES = ["CONFIRM", "REFUTE", "MONITOR"]
IW_OBSERVED = ["YES", "NO", "UNKNOWN"]

DA_AREAS = [
    ("False Flag",        "Could another actor be mimicking the TTPs of your leading hypothesis?"),
    ("Shared Tooling",    "Are the tools publicly available? Could any actor have used them?"),
    ("Coincidence",       "Could the signals be explained by non-malicious activity?"),
    ("Misidentification", "Could the infrastructure belong to another actor or be compromised by a third party?"),
    ("Confirmation Bias", "What evidence did you find FIRST that anchored your conclusion?"),
    ("Missing Evidence",  "What would you expect to see IF your hypothesis were true, but have NOT found?"),
]


def confidence_label(pct):
    try:
        pct = int(pct)
    except (TypeError, ValueError):
        return "UNKNOWN", ""
    pct = max(0, min(100, pct))
    for lo, hi, label, desc in CONFIDENCE_LEVELS:
        if lo <= pct <= hi:
            return label, desc
    return "UNKNOWN", ""


def risk_of(certainty, impact):
    """KAC risk: low certainty × high impact. Returns (value, label)."""
    value = (6 - int(certainty)) * int(impact)
    if value >= 16:
        label = "CRITICAL"
    elif value >= 10:
        label = "HIGH"
    elif value >= 5:
        label = "MEDIUM"
    else:
        label = "LOW"
    return value, label


# ── SESSION ────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def new_session():
    return normalize({
        "meta": {
            "created": now_iso(),
            "updated": now_iso(),
            "case_id": "CTI-{}".format(datetime.date.today().strftime("%Y%m%d")),
        }
    })


def _as_int(v, default, lo=None, hi=None):
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _s(v):
    """Coerce to a clean string (YAML may give None / numbers)."""
    return "" if v is None else str(v).strip()


def _str_list(v):
    if not v:
        return []
    if isinstance(v, str):
        return [v]
    return [_s(x) for x in v if _s(x)]


def normalize(session):
    """
    Bring any session dict (old CLI format, hand-edited YAML, GUI payload)
    to the canonical shape. Never raises on missing / malformed fields.
    """
    s = deepcopy(session) if isinstance(session, dict) else {}

    meta = s.get("meta") if isinstance(s.get("meta"), dict) else {}
    tlp = _s(meta.get("tlp")).upper() or "CLEAR"
    tlp = TLP_ALIASES.get(tlp, tlp)
    if tlp not in TLP_LEVELS:
        tlp = "CLEAR"
    s["meta"] = {
        "created": _s(meta.get("created")) or now_iso(),
        "updated": _s(meta.get("updated")) or now_iso(),
        "analyst": _s(meta.get("analyst")),
        "case_id": _s(meta.get("case_id")),
        "ioc": _s(meta.get("ioc")),
        "tlp": tlp,
        "geopolitical_context": _s(meta.get("geopolitical_context") or meta.get("context")),
    }

    # ACH
    ach = s.get("ach") if isinstance(s.get("ach"), dict) else {}
    hyps = [
        {"label": _s(h.get("label")), "description": _s(h.get("description"))}
        for h in (ach.get("hypotheses") or []) if isinstance(h, dict)
    ]
    evid = []
    for e in (ach.get("evidence") or []):
        if not isinstance(e, dict):
            continue
        rel = _s(e.get("reliability")).upper()[:1] or "B"
        evid.append({
            "description": _s(e.get("description")),
            "reliability": rel if rel in RELIABILITY else "B",
            "source": _s(e.get("source")),
        })
    matrix = {}
    raw_m = ach.get("matrix") or {}
    for ei in range(len(evid)):
        for hi in range(len(hyps)):
            v = _s(raw_m.get(f"{ei}_{hi}")).upper()
            matrix[f"{ei}_{hi}"] = v if v in CONSISTENCY else "N"
    concl = ach.get("conclusion") if isinstance(ach.get("conclusion"), dict) else {}
    lead = concl.get("leading_hypothesis")
    if isinstance(lead, str):  # "H2" (1-based label) or "1" (0-based index)
        m = re.match(r"\s*(H?)(\d+)\s*$", lead, re.I)
        lead = (int(m.group(2)) - (1 if m.group(1) else 0)) if m else None
    if not isinstance(lead, int) or not (0 <= lead < len(hyps)):
        lead = None
    pct = concl.get("confidence_pct")
    pct = None if pct is None or pct == "" else _as_int(pct, 50, 0, 100)
    s["ach"] = {
        "hypotheses": hyps,
        "evidence": evid,
        "matrix": matrix,
        "conclusion": {
            "leading_hypothesis": lead,
            "confidence_pct": pct,
            "confidence_label": confidence_label(pct)[0] if pct is not None else "",
            "rationale": _s(concl.get("rationale")),
            "caveats": _s(concl.get("caveats")),
            "confirm_indicators": _str_list(concl.get("confirm_indicators")),
            "refute_indicators": _str_list(concl.get("refute_indicators")),
        },
    }

    # KAC
    kac = s.get("kac") if isinstance(s.get("kac"), dict) else {}
    s["kac"] = {"assumptions": [
        {
            "text": _s(a.get("text")),
            "certainty": _as_int(a.get("certainty"), 3, 1, 5),
            "impact": _as_int(a.get("impact"), 3, 1, 5),
            "challenge": _s(a.get("challenge")),
        }
        for a in (kac.get("assumptions") or []) if isinstance(a, dict)
    ]}

    # I&W
    iw = s.get("iw") if isinstance(s.get("iw"), dict) else {}
    scenarios = []
    for sc in (iw.get("scenarios") or []):
        if not isinstance(sc, dict):
            continue
        inds = []
        for ind in (sc.get("indicators") or []):
            if not isinstance(ind, dict):
                continue
            t = _s(ind.get("type")).upper()
            obs = _s(ind.get("observed")).upper()
            obs = {"Y": "YES", "TRUE": "YES", "N": "NO", "FALSE": "NO"}.get(obs, obs)
            inds.append({
                "text": _s(ind.get("text")),
                "type": t if t in IW_TYPES else "MONITOR",
                "mitre": _s(ind.get("mitre")).upper(),
                "source": _s(ind.get("source")),
                "observed": obs if obs in IW_OBSERVED else "UNKNOWN",
                "observation_note": _s(ind.get("observation_note") or ind.get("note")),
            })
        scenarios.append({"label": _s(sc.get("label")), "indicators": inds})
    # Legacy flat structure (s1_label, s1_status, ...) → scenarios
    if not scenarios:
        nums = sorted({int(m.group(1)) for k in iw for m in [re.match(r"s(\d+)_", str(k))] if m})
        for n in nums:
            scenarios.append({"label": _s(iw.get(f"s{n}_label")) or f"Scenario {n}", "indicators": []})
    s["iw"] = {"scenarios": scenarios}

    # DA
    da = s.get("da") if isinstance(s.get("da"), dict) else {}
    by_area = {_s(ch.get("area")): ch for ch in (da.get("challenges") or []) if isinstance(ch, dict)}
    challenges = []
    for area, hint in DA_AREAS:
        ch = by_area.pop(area, {})
        challenges.append({
            "area": area, "hint": hint,
            "argument": _s(ch.get("argument")).lstrip("→ ").strip(),
            "strength": _as_int(ch.get("strength"), 1, 1, 5),
        })
    for area, ch in by_area.items():  # custom areas kept
        challenges.append({
            "area": area, "hint": _s(ch.get("hint")),
            "argument": _s(ch.get("argument")).lstrip("→ ").strip(),
            "strength": _as_int(ch.get("strength"), 1, 1, 5),
        })
    nc = da.get("new_confidence")
    s["da"] = {
        "leading_hypothesis": _s(da.get("leading_hypothesis")),
        "alternative_hypothesis": _s(da.get("alternative_hypothesis")).lstrip("→ ").strip(),
        "challenges": challenges,
        "revised": bool(da.get("revised")),
        "new_conclusion": _s(da.get("new_conclusion")),
        "new_confidence": None if nc in (None, "") else _as_int(nc, 50, 0, 100),
        "final_note": _s(da.get("final_note")),
    }

    # Extra free-form sections supported by the report (hand-edited YAML)
    src = session if isinstance(session, dict) else {}
    for key in ("iocs", "next_pivot", "gaps"):
        if src.get(key):
            s[key] = src[key]
    return s


def load_session(path):
    with open(path, encoding="utf-8") as f:
        return normalize(yaml.safe_load(f) or {})


def load_session_text(text):
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("Not a CSAT session (expected a YAML mapping)")
    return normalize(data)


def dump_session(session):
    s = normalize(session)
    s["meta"]["updated"] = now_iso()
    out = deepcopy(s)
    # Persist computed ACH scores so the YAML stays self-describing
    a = analyze(s)["ach"]
    if a["ready"]:
        out["ach"]["scores"] = {
            r["index"]: {"total": r["total"], "inconsistencies": r["inconsistency"],
                         "confidence_pct": r["support_pct"]}
            for r in a["hypotheses"]
        }
    return yaml.dump(out, allow_unicode=True, sort_keys=False, width=100)


def save_session(session, path):
    text = dump_session(session)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# ── ANALYSIS ───────────────────────────────────────────────────────────────

def _ach_scores(n_h, evidence, cell):
    """
    cell(ei, hi) -> code. Returns per-hypothesis dict.

    Heuer: the most likely hypothesis is the one with the LEAST evidence
    against it. Inconsistency = Σ |negative value| × reliability weight.
    Ties broken by weighted net consistency.
    """
    res = []
    for hi in range(n_h):
        inc = 0.0
        total = 0
        net = 0.0
        scored = 0
        for ei, e in enumerate(evidence):
            v = CONSISTENCY[cell(ei, hi)]["value"]
            scored += v != 0
            w = RELIABILITY.get(e["reliability"], RELIABILITY["B"])["weight"]
            total += v
            net += v * w
            if v < 0:
                inc += -v * w
        max_net = sum(2 * RELIABILITY.get(e["reliability"], RELIABILITY["B"])["weight"] for e in evidence)
        support = int(round((net + max_net) / (2 * max_net) * 100)) if max_net else 0
        res.append({"index": hi, "total": total, "net": round(net, 2),
                    "inconsistency": round(inc, 2), "support_pct": support,
                    "unscored": scored == 0})
    return res


def _rank(scores):
    # A hypothesis with only neutral cells has nothing against it simply
    # because it was never tested: it must not win by default.
    return sorted(range(len(scores)),
                  key=lambda i: (scores[i]["unscored"], scores[i]["inconsistency"], -scores[i]["net"], i))


def analyze_ach(ach):
    hyps, evid, matrix = ach["hypotheses"], ach["evidence"], ach["matrix"]
    out = {"ready": len(hyps) >= 2 and len(evid) >= 1, "hypotheses": [], "evidence": [],
           "ranking": [], "leader": None, "fragile": [], "robust": None, "tie": False,
           "unscored": []}
    if not out["ready"]:
        return out

    def cell(ei, hi):
        return matrix.get(f"{ei}_{hi}", "N")

    scores = _ach_scores(len(hyps), evid, cell)
    ranking = _rank(scores)
    leader = ranking[0]
    out["tie"] = (len(ranking) > 1
                  and scores[ranking[0]]["inconsistency"] == scores[ranking[1]]["inconsistency"]
                  and scores[ranking[0]]["net"] == scores[ranking[1]]["net"])

    # Sensitivity: drop each evidence item, re-score with correct re-indexing
    for drop in range(len(evid)):
        keep = [ei for ei in range(len(evid)) if ei != drop]
        if not keep:
            continue
        sub = _ach_scores(len(hyps), [evid[ei] for ei in keep], lambda j, hi: cell(keep[j], hi))
        if _rank(sub)[0] != leader:
            out["fragile"].append(drop)
    out["robust"] = not out["fragile"]
    out["unscored"] = [i for i, sc in enumerate(scores) if sc["unscored"]]

    # Diagnosticity: how much an item discriminates between hypotheses
    for ei, e in enumerate(evid):
        vals = [CONSISTENCY[cell(ei, hi)]["value"] for hi in range(len(hyps))]
        spread = max(vals) - min(vals)
        if all(v == 0 for v in vals):
            kind = "none"
        elif spread == 0:
            kind = "weak"  # same score everywhere: no discriminating power
        elif spread >= 2:
            kind = "high"
        else:
            kind = "medium"
        out["evidence"].append({"index": ei, "diagnosticity": kind, "spread": spread,
                                "fragile": ei in out["fragile"]})

    for rank, hi in enumerate(ranking):
        sc = dict(scores[hi])
        sc["rank"] = rank + 1
        sc["label"] = hyps[hi]["label"]
        out["hypotheses"].append(sc)
    out["hypotheses"].sort(key=lambda r: r["index"])
    out["ranking"] = ranking
    out["leader"] = leader
    return out


def analyze_kac(kac):
    rows = []
    for i, a in enumerate(kac["assumptions"]):
        v, lbl = risk_of(a["certainty"], a["impact"])
        rows.append({"index": i, "risk": v, "risk_label": lbl,
                     "critical": a["certainty"] <= 2 and a["impact"] >= 4})
    return {"assumptions": rows, "critical": [r["index"] for r in rows if r["critical"]]}


def analyze_iw(iw):
    out = []
    for sc in iw["scenarios"]:
        inds = sc["indicators"]
        confirm = [i for i in inds if i["type"] == "CONFIRM"]
        c_yes = [i for i in confirm if i["observed"] == "YES"]
        c_no = [i for i in confirm if i["observed"] == "NO"]
        r_yes = [i for i in inds if i["type"] == "REFUTE" and i["observed"] == "YES"]
        m_yes = [i for i in inds if i["type"] == "MONITOR" and i["observed"] == "YES"]
        pct = int(round(len(c_yes) / len(confirm) * 100)) if confirm else 0
        # Observed refuting indicators cap the assessment: absence of
        # expected indicators is evidence too.
        if r_yes:
            pct = min(pct, 24)
        label, _ = confidence_label(pct)
        if r_yes:
            status = "REFUTED"
        elif pct >= 75:
            status = "ACTIVE"
        elif pct >= 50:
            status = "LIKELY"
        elif c_yes or m_yes:
            status = "WATCH"
        else:
            status = "NOT OBSERVED"
        out.append({
            "confirm_total": len(confirm), "confirm_observed": len(c_yes),
            "confirm_missing": len(c_no), "refute_observed": len(r_yes),
            "monitor_observed": len(m_yes), "pct": pct, "label": label, "status": status,
        })
    return {"scenarios": out}


def analyze_da(da):
    strong = [i for i, ch in enumerate(da["challenges"]) if ch["argument"] and ch["strength"] >= 4]
    filled = [ch for ch in da["challenges"] if ch["argument"]]
    avg = round(sum(ch["strength"] for ch in filled) / len(filled), 1) if filled else 0
    if not filled:
        verdict = "NOT RUN"
    elif len(strong) >= 3 or (avg >= 4 and len(filled) >= 3):
        verdict = "CONCLUSION DOES NOT HOLD"
    elif strong:
        verdict = "UNRESOLVED CHALLENGES"
    else:
        verdict = "CONCLUSION SURVIVES"
    return {"strong": strong, "average": avg, "filled": len(filled), "verdict": verdict}


def completion(s):
    ach = s["ach"]
    return {
        "meta": bool(s["meta"]["case_id"] and s["meta"]["ioc"]),
        "ach": ach["conclusion"]["leading_hypothesis"] is not None
               and ach["conclusion"]["confidence_pct"] is not None,
        "kac": bool(s["kac"]["assumptions"]),
        "iw": any(sc["indicators"] for sc in s["iw"]["scenarios"]),
        "da": any(ch["argument"] for ch in s["da"]["challenges"]),
    }


def analyze(session):
    s = normalize(session)
    return {
        "ach": analyze_ach(s["ach"]),
        "kac": analyze_kac(s["kac"]),
        "iw": analyze_iw(s["iw"]),
        "da": analyze_da(s["da"]),
        "completion": completion(s),
    }


def final_assessment(s, a=None):
    """Bottom line: leading hypothesis + confidence, after DA if revised."""
    a = a or analyze(s)
    ach = s["ach"]
    concl = ach["conclusion"]
    lead = concl["leading_hypothesis"]
    if lead is None and a["ach"]["ready"]:
        lead = a["ach"]["leader"]
    if lead is None:
        return None
    h = ach["hypotheses"][lead]
    pct = concl["confidence_pct"]
    if pct is None:
        pct = next(r["support_pct"] for r in a["ach"]["hypotheses"] if r["index"] == lead)
    text = "H{} {}".format(lead + 1, h["label"]) + (": " + h["description"] if h["description"] else "")
    revised = False
    if s["da"]["revised"] and (s["da"]["new_conclusion"] or s["da"]["new_confidence"] is not None):
        revised = True
        if s["da"]["new_conclusion"]:
            text = s["da"]["new_conclusion"]
        if s["da"]["new_confidence"] is not None:
            pct = s["da"]["new_confidence"]
    label, desc = confidence_label(pct)
    return {"index": lead, "text": text, "pct": pct, "label": label, "desc": desc,
            "revised": revised, "matches_matrix": lead == a["ach"]["leader"]}


# ── REPORT ─────────────────────────────────────────────────────────────────

def _md_escape(v):
    return _s(v).replace("|", "\\|").replace("\n", " ")


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_md_escape(x) for x in r) + " |")
    return out


def generate_report(session):
    """Return the Flash Report as Markdown text."""
    s = normalize(session)
    a = analyze(s)
    meta = s["meta"]
    L = []
    L.append("# CTI Structured Analytic Report: {}".format(meta["case_id"] or "N/A"))
    L.append("")
    L.append("**TLP:{}** · **Date:** {} · **Analyst:** {}".format(
        meta["tlp"], datetime.date.today().isoformat(), meta["analyst"] or "N/A"))
    L.append("")
    L.append("**IOC:** `{}`  ".format(meta["ioc"] or "N/A"))
    L.append("**Context:** {}".format(meta["geopolitical_context"] or "N/A"))
    L.append("")

    # Bottom line
    fa = final_assessment(s, a)
    L.append("## Bottom Line")
    L.append("")
    if fa:
        L.append("**Assessment:** {}".format(fa["text"]))
        L.append("")
        L.append("**Confidence:** {} ({}%). {}".format(fa["label"], fa["pct"], fa["desc"]))
        if fa["revised"]:
            L.append("")
            L.append("> Conclusion revised after Devil's Advocacy.")
        if not fa["matches_matrix"] and not fa["revised"]:
            L.append("")
            L.append("> ⚠ The analyst's leading hypothesis differs from the ACH matrix leader "
                     "(H{}). Justification required.".format(a["ach"]["leader"] + 1))
        if a["ach"]["ready"] and a["ach"]["fragile"]:
            L.append("")
            L.append("> ⚠ Fragile conclusion, it depends on {}.".format(
                ", ".join("E{}".format(i + 1) for i in a["ach"]["fragile"])))
        if a["ach"]["ready"] and a["ach"]["unscored"]:
            L.append("")
            L.append("> ⚠ Never tested against evidence (all neutral): {}.".format(
                ", ".join("H{}".format(i + 1) for i in a["ach"]["unscored"])))
        if a["kac"]["critical"]:
            L.append("")
            L.append("> ⚠ {} critical assumption(s), see KAC.".format(len(a["kac"]["critical"])))
        if a["da"]["strong"]:
            L.append("")
            L.append("> ⚠ {} strong counter-argument(s) unresolved, see DA.".format(len(a["da"]["strong"])))
    else:
        L.append("_No conclusion yet. Complete the ACH first._")
    L.append("")

    # ACH
    ach, aa = s["ach"], a["ach"]
    if aa["ready"]:
        concl = ach["conclusion"]
        L += ["---", "", "## ACH: Analysis of Competing Hypotheses", ""]
        if concl["rationale"]:
            L.append("**Rationale:** {}".format(concl["rationale"]))
            L.append("")
        if concl["caveats"]:
            L.append("**Caveats:** {}".format(concl["caveats"]))
            L.append("")
        L.append("### Hypotheses")
        L.append("")
        rows = []
        for r in sorted(aa["hypotheses"], key=lambda r: r["rank"]):
            h = ach["hypotheses"][r["index"]]
            rows.append(["#{}".format(r["rank"]), "H{} {}".format(r["index"] + 1, h["label"]),
                         h["description"], r["inconsistency"], "{:+d}".format(r["total"]),
                         "{}%".format(r["support_pct"])])
        L += _md_table(["Rank", "Hypothesis", "Description", "Weighted inconsistency ↓",
                        "Net score", "Support"], rows)
        L.append("")
        L.append("### Evidence matrix")
        L.append("")
        heads = ["#", "Evidence", "Rel.", "Source"] + ["H{}".format(i + 1) for i in range(len(ach["hypotheses"]))] + ["Diagnostic"]
        rows = []
        for ei, e in enumerate(ach["evidence"]):
            d = aa["evidence"][ei]
            flag = d["diagnosticity"] + (" · FRAGILE" if d["fragile"] else "")
            rows.append(["E{}".format(ei + 1), e["description"], e["reliability"], e["source"]]
                        + [ach["matrix"].get(f"{ei}_{hi}", "N") for hi in range(len(ach["hypotheses"]))]
                        + [flag])
        L += _md_table(heads, rows)
        L.append("")
        L.append("Sensitivity: " + ("**robust**: no single evidence item changes the leader."
                                    if aa["robust"] else "**fragile**: removing {} changes the leader.".format(
                                        ", ".join("E{}".format(i + 1) for i in aa["fragile"]))))
        L.append("")
        if concl["confirm_indicators"] or concl["refute_indicators"]:
            L.append("### Indicators to monitor")
            L.append("")
            for x in concl["confirm_indicators"]:
                L.append("- **CONFIRM:** {}".format(x))
            for x in concl["refute_indicators"]:
                L.append("- **REFUTE:** {}".format(x))
            L.append("")

    # KAC
    if s["kac"]["assumptions"]:
        L += ["---", "", "## KAC: Key Assumptions Check", ""]
        rows = []
        for i, x in enumerate(s["kac"]["assumptions"]):
            r = a["kac"]["assumptions"][i]
            rows.append(["A{}".format(i + 1), x["text"], "{}/5".format(x["certainty"]),
                         "{}/5".format(x["impact"]), r["risk_label"], x["challenge"]])
        L += _md_table(["#", "Assumption", "Certainty", "Impact", "Risk", "What would prove it wrong"], rows)
        L.append("")
        if a["kac"]["critical"]:
            L.append("**Critical assumptions (low certainty, high impact), to collect on first:**")
            L.append("")
            for i in a["kac"]["critical"]:
                x = s["kac"]["assumptions"][i]
                L.append("- **A{}** {}. _Challenge:_ {}".format(i + 1, x["text"], x["challenge"] or "N/A"))
            L.append("")

    # I&W
    if any(sc["indicators"] or sc["label"] for sc in s["iw"]["scenarios"]):
        L += ["---", "", "## I&W: Indicators & Warnings", ""]
        for si, sc in enumerate(s["iw"]["scenarios"]):
            r = a["iw"]["scenarios"][si]
            L.append("### S{}: {}".format(si + 1, sc["label"] or "Unnamed scenario"))
            L.append("")
            L.append("**Status: {}**, {} ({}%) · confirm indicators observed {}/{} · "
                     "refuting observed {} · expected but absent {}".format(
                         r["status"], r["label"], r["pct"], r["confirm_observed"], r["confirm_total"],
                         r["refute_observed"], r["confirm_missing"]))
            L.append("")
            if sc["indicators"]:
                L += _md_table(["Type", "Indicator", "ATT&CK", "Source", "Observed", "Note"],
                               [[i["type"], i["text"], i["mitre"], i["source"], i["observed"],
                                 i["observation_note"]] for i in sc["indicators"]])
                L.append("")

    # DA
    da, ad = s["da"], a["da"]
    if ad["filled"]:
        L += ["---", "", "## DA: Devil's Advocacy", ""]
        L.append("**Hypothesis challenged:** {}".format(da["leading_hypothesis"] or (fa["text"] if fa else "N/A")))
        L.append("")
        if da["alternative_hypothesis"]:
            L.append("**Alternative:** {}".format(da["alternative_hypothesis"]))
            L.append("")
        L.append("**Verdict:** {} (average strength {}/5)".format(ad["verdict"], ad["average"]))
        L.append("")
        L += _md_table(["Area", "Strength", "Counter-argument"],
                       [[ch["area"], "{}/5".format(ch["strength"]), ch["argument"] or "-"]
                        for ch in da["challenges"]])
        L.append("")
        if da["revised"]:
            L.append("**Revised conclusion:** {} ({}%)".format(
                da["new_conclusion"] or "N/A",
                da["new_confidence"] if da["new_confidence"] is not None else "N/A"))
            L.append("")
        if da["final_note"]:
            L.append("**Final note:** {}".format(da["final_note"]))
            L.append("")

    # Optional hand-edited sections
    iocs = s.get("iocs")
    if isinstance(iocs, dict):
        rows = []
        for key, label in [("block", "BLOCK"), ("watch", "WATCH"), ("monitor", "MONITOR"), ("tls", "PIVOT")]:
            for entry in iocs.get(key) or []:
                if isinstance(entry, dict):
                    rows.append([label, entry.get("thumbprint", entry.get("value", "")), entry.get("note", "")])
                else:
                    rows.append([label, entry, ""])
        if rows:
            L += ["---", "", "## IOC Summary", ""] + _md_table(["Status", "IOC", "Note"], rows) + [""]
    gaps = s.get("next_pivot") or s.get("gaps")
    if gaps:
        L += ["---", "", "## Gaps: Next Actions", ""]
        if isinstance(gaps, dict):
            L += _md_table(["Priority", "Action"], [[k, v] for k, v in sorted(gaps.items())])
        else:
            L += ["- {}".format(g) for g in (gaps if isinstance(gaps, list) else [gaps])]
        L.append("")

    L += ["---", "", "_Generated by CSAT (CTI Structured Analytic Techniques) · TLP:{}_".format(meta["tlp"])]
    return "\n".join(L) + "\n"


def report_filename(session):
    cid = re.sub(r"[^\w.-]+", "_", normalize(session)["meta"]["case_id"] or "cti")
    return "flash_report_{}_{}.md".format(cid, datetime.date.today().isoformat())


# ── Minimal Markdown → HTML (only the subset generate_report emits) ───────

def _inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", t)
    return t


def markdown_to_html(md):
    out, i, lines = [], 0, md.splitlines()
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[-| ]+\|$", lines[i + 1]):
            def cells(row):
                parts = re.split(r"(?<!\\)\|", row.strip()[1:-1])
                return [p.strip().replace("\\|", "|") for p in parts]
            out.append("<table><thead><tr>" + "".join("<th>{}</th>".format(_inline(x)) for x in cells(ln)) + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                out.append("<tr>" + "".join("<td>{}</td>".format(_inline(x)) for x in cells(lines[i])) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue
        m = re.match(r"^(#{1,6}) (.*)", ln)
        if m:
            n = len(m.group(1))
            out.append("<h{0}>{1}</h{0}>".format(n, _inline(m.group(2))))
        elif ln.strip() == "---":
            out.append("<hr>")
        elif ln.startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].startswith("- "):
                out.append("<li>{}</li>".format(_inline(lines[i][2:])))
                i += 1
            out.append("</ul>")
            continue
        elif ln.startswith("> "):
            out.append("<blockquote>{}</blockquote>".format(_inline(ln[2:])))
        elif ln.strip():
            out.append("<p>{}</p>".format(_inline(ln.rstrip())))
        i += 1
    return "\n".join(out)


REPORT_CSS = """
body{font:15px/1.55 -apple-system,Segoe UI,Inter,Roboto,sans-serif;color:#1d1f23;max-width:960px;margin:40px auto;padding:0 24px}
h1{font-size:26px;margin-bottom:4px}h2{font-size:19px;margin-top:28px;border-bottom:2px solid #c9a227;padding-bottom:4px}
h3{font-size:16px;margin-top:20px}table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px}
th,td{border:1px solid #d6d8dc;padding:6px 8px;text-align:left;vertical-align:top}th{background:#f3f4f6}
code{background:#f3f4f6;padding:1px 5px;border-radius:4px}blockquote{margin:8px 0;padding:8px 12px;border-left:4px solid #d97706;background:#fff7ed}
hr{border:0;border-top:1px solid #e5e7eb;margin:24px 0}@media print{body{margin:0}h2{break-after:avoid}table{break-inside:auto}}
"""


def report_html(session):
    md = generate_report(session)
    meta = normalize(session)["meta"]
    return ("<!doctype html><html><head><meta charset='utf-8'><title>Flash Report: {}</title>"
            "<style>{}</style></head><body>{}</body></html>").format(
        html.escape(meta["case_id"]), REPORT_CSS, markdown_to_html(md))
