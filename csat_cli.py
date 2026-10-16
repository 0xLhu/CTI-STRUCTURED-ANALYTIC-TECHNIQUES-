"""
csat_cli.py: Interactive terminal workflow for CSAT (same sessions as the GUI).
"""

import os
import sys
from textwrap import wrap

import csat_core as core


def _force_utf8():
    for name in ("stdout", "stderr"):
        s = getattr(sys, name, None)
        enc = (getattr(s, "encoding", "") or "").lower().replace("-", "")
        if s is not None and enc not in ("utf8", "utf16", "utf32"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError):
                pass


# ── TERMINAL HELPERS ───────────────────────────────────────────────────────

WIDTH = 90
COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

RESET, BOLD = "\033[0m", "\033[1m"
RED, GREEN, YELLOW, BLUE, CYAN, WHITE, GRAY = (
    "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[36m", "\033[97m", "\033[90m")
CONF_COLOR = {"HIGH": GREEN, "MEDIUM": YELLOW, "LOW": GRAY, "MINIMAL": GRAY}
CELL_COLOR = {"CC": GREEN, "C": GREEN, "N": GRAY, "I": YELLOW, "II": RED}


def c(text, *codes):
    return ("".join(codes) + str(text) + RESET) if COLOR else str(text)


def hr(char="─", color=GRAY):
    print(c(char * WIDTH, color))


def hr_title(title, char="─", color=CYAN):
    pad = max(0, (WIDTH - len(title) - 2) // 2)
    print(c((char * pad + f" {title} " + char * WIDTH)[:WIDTH], color, BOLD))


def banner():
    if sys.stdout.isatty():
        os.system("clear" if os.name == "posix" else "cls")
    print()
    print(c("  CTI STRUCTURED ANALYTIC TECHNIQUES", WHITE, BOLD))
    print(c("  ACH · Key Assumptions Check · Indicators & Warnings · Devil's Advocacy", GRAY))
    hr()
    print()


def prompt(msg, default=None, color=YELLOW):
    suffix = f" [{default}]" if default not in (None, "") else ""
    try:
        val = input(c(f"  ▶ {msg}{suffix}: ", color)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val if val else ("" if default is None else str(default))


def prompt_int(msg, lo, hi, default=None):
    while True:
        raw = prompt(msg, default)
        try:
            v = int(raw)
            if lo <= v <= hi:
                return v
        except ValueError:
            pass
        print(c(f"  Please enter a number between {lo} and {hi}.", RED))


def prompt_choice(msg, choices, default=None):
    print()
    for key, label in choices:
        print(c(f"  [{key}]", CYAN, BOLD) + f"  {label}")
    print()
    valid = {str(k).lower(): str(k) for k, _ in choices}
    while True:
        val = prompt(msg, default).lower()
        if val in valid:
            return valid[val]
        print(c(f"  Invalid choice. Options: {', '.join(valid.values())}", RED))


def prompt_list(msg, existing=None):
    existing = existing or []
    if existing:
        print(c(f"  Current: " + " | ".join(existing), GRAY))
        if not confirm("Replace this list?"):
            return existing
    print(c(f"  {msg} (empty line to finish)", GRAY))
    items = []
    while True:
        val = prompt(f"  {len(items) + 1}", color=WHITE)
        if not val:
            return items
        items.append(val)


def confirm(msg, default="n"):
    return prompt(f"{msg} [y/n]", default).lower() in ("y", "yes", "o", "oui")


def info(msg):
    print(c(f"  i  {msg}", BLUE))


def warn(msg):
    print(c(f"  !  {msg}", YELLOW))


def success(msg):
    print(c(f"  ✓  {msg}", GREEN))


def box(title, lines, color=BLUE):
    w = WIDTH - 4
    print(c(f"  ┌─ {title} " + "─" * (w - len(title) - 4) + "┐", color))
    for line in lines:
        for wl in wrap(line, w - 4) or [""]:
            print(c("  │ ", color) + wl + " " * (w - len(wl) - 2) + c("│", color))
    print(c("  └" + "─" * w + "┘", color))
    print()


def pause():
    input(c("\n  Press Enter to return to menu...", GRAY))


# ── SESSION INIT ───────────────────────────────────────────────────────────

def init_session(s):
    banner()
    hr_title("CASE")
    m = s["meta"]
    m["case_id"] = prompt("Case ID", m["case_id"])
    m["analyst"] = prompt("Analyst initials", m["analyst"])
    m["ioc"] = prompt("IOC under analysis (IP / domain / hash / URL)", m["ioc"])
    m["tlp"] = prompt_choice("TLP", [(t, t) for t in core.TLP_LEVELS], m["tlp"])
    m["geopolitical_context"] = prompt("Operational / geopolitical context", m["geopolitical_context"])
    success("Case details saved.")
    return s


# ── ACH ────────────────────────────────────────────────────────────────────

def _edit_rows(name, rows, fields):
    """Generic keep/edit/add loop. fields: list of (key, question, default)."""
    if rows:
        print(c(f"  Existing {name}:", GRAY))
        for i, r in enumerate(rows):
            print(f"  {name[0].upper()}{i + 1}: " + " · ".join(str(r[k]) for k, _, _ in fields if r.get(k)))
        if not confirm(f"Re-enter {name}?"):
            return rows
    out = []
    print(c(f"  Enter {name} (empty first field to finish):", GRAY))
    while True:
        tag = f"{name[0].upper()}{len(out) + 1}"
        row = {}
        for j, (k, q, d) in enumerate(fields):
            row[k] = prompt(f"  {tag} {q}", d)
            if j == 0 and not row[k]:
                return out
        out.append(row)


def print_ach_matrix(ach, a):
    hyps, evid = ach["hypotheses"], ach["evidence"]
    col_w, e_w = 11, 44
    head = c(f"  {'Evidence':<{e_w}}", GRAY)
    for i, h in enumerate(hyps):
        head += c(f"{('H%d:%s' % (i + 1, h['label']))[:col_w - 1]:^{col_w}}", GREEN if i == a["leader"] else CYAN)
    print(head)
    hr()
    for ei, e in enumerate(evid):
        d = a["evidence"][ei]
        flag = "!" if d["fragile"] else {"high": "*", "medium": "+", "weak": ".", "none": "o"}[d["diagnosticity"]]
        row = f"  {c(flag, YELLOW)} {c(f'E{ei + 1:<2}', YELLOW)}[{e['reliability']}] {e['description'][:e_w - 12]:<{e_w - 12}}"
        for hi in range(len(hyps)):
            v = ach["matrix"].get(f"{ei}_{hi}", "N")
            row += c(f"{v:^{col_w}}", CELL_COLOR[v])
        print(row)
    hr()
    for title, key in (("WEIGHTED INCONSISTENCY (lower = stronger)", "inconsistency"),
                       ("NET SCORE", "total"), ("RANK", "rank")):
        line = c(f"  {title:<{e_w}}", BOLD)
        for r in a["hypotheses"]:
            line += c(f"{str(r[key]) if not (r['unscored'] and key == 'rank') else 'untested':^{col_w}}",
                      GREEN if r["index"] == a["leader"] else GRAY, BOLD)
        print(line)
    print(c("  * diagnostic  + partly diagnostic  . same everywhere  o no value  ! fragile", GRAY))
    print()


def method_ach(s):
    banner()
    hr_title("ACH: ANALYSIS OF COMPETING HYPOTHESES")
    box("Principle", [
        "The goal is NOT to find the hypothesis with the most supporting evidence.",
        "It is to find the hypothesis with the LEAST evidence against it.",
        "Evidence consistent with ALL hypotheses has no diagnostic value.",
    ])
    ach = s["ach"]

    hr_title("1 / 5: Hypotheses", "·", YELLOW)
    info("Include unlikely ones (unknown actor, benign) to avoid tunnel vision.")
    hyps = _edit_rows("hypotheses", ach["hypotheses"],
                      [("label", "label (e.g. APT40)", None), ("description", "description", "")])
    if len(hyps) < 2:
        warn("ACH requires at least 2 hypotheses.")
        pause()
        return s

    hr_title("2 / 5: Evidence", "·", YELLOW)
    info("Reliability: A=confirmed  B=probably true  C=possibly true  D=unconfirmed")
    evid = _edit_rows("evidence", ach["evidence"],
                      [("description", "description", None), ("reliability", "reliability A/B/C/D", "B"),
                       ("source", "source (Shodan / VT / OSINT…)", "")])
    if not evid:
        warn("ACH requires at least 1 evidence item.")
        pause()
        return s

    # Re-entering rows invalidates old matrix indices
    matrix = ach["matrix"] if (hyps is ach["hypotheses"] and evid is ach["evidence"]) else {}
    s["ach"] = ach = core.normalize({"ach": {**ach, "hypotheses": hyps, "evidence": evid, "matrix": matrix}})["ach"]

    hr_title("3 / 5: Consistency matrix", "·", YELLOW)
    for code, d in core.CONSISTENCY.items():
        print(c(f"  {code:3s}", CELL_COLOR[code], BOLD) + f" {d['value']:+d}  {d['label']}")
    for ei, e in enumerate(ach["evidence"]):
        print(c(f"\n  E{ei + 1}: {e['description']}", WHITE, BOLD))
        for hi, h in enumerate(ach["hypotheses"]):
            k = f"{ei}_{hi}"
            v = prompt(f"    H{hi + 1} [{h['label']}]", ach["matrix"].get(k, "N")).upper()
            ach["matrix"][k] = v if v in core.CONSISTENCY else "N"

    a = core.analyze_ach(ach)
    hr_title("4 / 5: Results", "·", YELLOW)
    print_ach_matrix(ach, a)
    if a["unscored"]:
        warn("Untested (all neutral): " + ", ".join(f"H{i + 1}" for i in a["unscored"]))
    if a["fragile"]:
        warn("FRAGILE: removing these items changes the leader:")
        for ei in a["fragile"]:
            print(c(f"     E{ei + 1}: {ach['evidence'][ei]['description']}", YELLOW))
    else:
        success("ROBUST: no single evidence item changes the leader.")
    lead = a["leader"]
    print(c(f"\n  MATRIX LEADER: H{lead + 1} {ach['hypotheses'][lead]['label']}", GREEN, BOLD))

    hr_title("5 / 5: Conclusion", "·", YELLOW)
    concl = ach["conclusion"]
    cur = concl["leading_hypothesis"] if concl["leading_hypothesis"] is not None else lead
    chosen = prompt_int("Leading hypothesis number (H#)", 1, len(ach["hypotheses"]), cur + 1) - 1
    support = a["hypotheses"][chosen]["support_pct"]
    pct = prompt_int("Analyst confidence % (0-100)", 0, 100,
                     concl["confidence_pct"] if concl["confidence_pct"] is not None else support)
    lbl, desc = core.confidence_label(pct)
    print(c(f"  Confidence: {lbl} ({pct}%). {desc}", CONF_COLOR.get(lbl, GRAY), BOLD))
    if chosen != lead:
        warn("Your choice differs from the matrix leader. Justify it in the rationale.")
    concl.update({
        "leading_hypothesis": chosen, "confidence_pct": pct, "confidence_label": lbl,
        "rationale": prompt("Rationale", concl["rationale"]),
        "caveats": prompt("Caveats / what would change this", concl["caveats"]),
    })
    concl["confirm_indicators"] = prompt_list(f"Evidence that would CONFIRM H{chosen + 1}", concl["confirm_indicators"])
    concl["refute_indicators"] = prompt_list(f"Evidence that would REFUTE H{chosen + 1}", concl["refute_indicators"])
    success("ACH saved.")
    pause()
    return s


# ── KAC ────────────────────────────────────────────────────────────────────

def method_kac(s):
    banner()
    hr_title("KAC: KEY ASSUMPTIONS CHECK")
    box("Principle", [
        "Hidden assumptions drive conclusions more than evidence does.",
        "Ask: 'What would have to be true for my analysis to be wrong?'",
    ])
    existing = s["kac"]["assumptions"]
    rows = _edit_rows("assumptions", existing, [("text", "assumption", None)])
    by_text = {a["text"]: a for a in existing}
    info("Certainty 1=uncertain → 5=certain · Impact if wrong 1=minor → 5=major")
    rated = []
    for i, r in enumerate(rows):
        old = by_text.get(r["text"], {})
        print(c(f"\n  A{i + 1}: {r['text']}", WHITE, BOLD))
        rated.append({
            "text": r["text"],
            "certainty": prompt_int("    Certainty (1-5)", 1, 5, old.get("certainty", 3)),
            "impact": prompt_int("    Impact    (1-5)", 1, 5, old.get("impact", 3)),
            "challenge": prompt("    What would prove it wrong?", old.get("challenge", "")),
        })
    s["kac"]["assumptions"] = rated
    a = core.analyze_kac(s["kac"])
    print()
    print(c(f"  {'#':<4} {'CERT.':<8} {'IMPACT':<8} {'RISK':<10} ASSUMPTION", GRAY))
    hr()
    for i, x in enumerate(rated):
        r = a["assumptions"][i]
        col = {"CRITICAL": RED, "HIGH": YELLOW, "MEDIUM": CYAN}.get(r["risk_label"], GREEN)
        risk = c("{:<10}".format(r["risk_label"]), col)
        print("  A{:<3} {:<8} {:<8} {} {}".format(i + 1, "●" * x["certainty"], "●" * x["impact"], risk, x["text"][:50]))
    if a["critical"]:
        print()
        warn("CRITICAL (low certainty + high impact). Collect on these first:")
        for i in a["critical"]:
            print(c(f"     A{i + 1} {rated[i]['text']} → {rated[i]['challenge']}", YELLOW))
    success("KAC saved.")
    pause()
    return s


# ── I&W ────────────────────────────────────────────────────────────────────

def method_iw(s):
    banner()
    hr_title("I&W: INDICATORS & WARNINGS")
    box("Principle", [
        "Define BEFORE observing what you expect to see IF a scenario is true.",
        "The absence of expected indicators is itself evidence.",
    ])
    scenarios = s["iw"]["scenarios"]
    if not scenarios or confirm("Add scenarios?"):
        for label in prompt_list("New scenario labels"):
            scenarios.append({"label": label, "indicators": []})
    for si, sc in enumerate(scenarios):
        print(c(f"\n  S{si + 1}: {sc['label']}", WHITE, BOLD))
        if not sc["indicators"] or confirm("  Add indicators?"):
            for itype, col in (("CONFIRM", GREEN), ("REFUTE", RED), ("MONITOR", CYAN)):
                print(c(f"    {itype} indicators", col))
                for text in prompt_list(f"    {itype}"):
                    sc["indicators"].append({
                        "text": text, "type": itype,
                        "mitre": prompt("      ATT&CK technique (e.g. T1190)", "").upper(),
                        "source": prompt("      Data source", ""),
                        "observed": "UNKNOWN", "observation_note": "",
                    })
        for ind in sc["indicators"]:
            col = {"CONFIRM": GREEN, "REFUTE": RED}.get(ind["type"], CYAN)
            print(c(f"  [{ind['type']}]", col) + f" {ind['text'][:65]}")
            obs = prompt("    Observed? y / n / ?", {"YES": "y", "NO": "n"}.get(ind["observed"], "?")).lower()
            ind["observed"] = {"y": "YES", "yes": "YES", "n": "NO", "no": "NO"}.get(obs, "UNKNOWN")
            if ind["observed"] == "YES":
                ind["observation_note"] = prompt("    Observation note", ind["observation_note"])
    a = core.analyze_iw(s["iw"])
    for si, (sc, r) in enumerate(zip(scenarios, a["scenarios"])):
        print()
        hr_title(f"S{si + 1}: {sc['label']}", "·")
        print(f"  Status {c(r['status'], BOLD)}: {r['label']} ({r['pct']}%) · confirm {r['confirm_observed']}/"
              f"{r['confirm_total']} · refute observed {r['refute_observed']} · absent {r['confirm_missing']}")
    success("I&W saved.")
    pause()
    return s


# ── DA ─────────────────────────────────────────────────────────────────────

def method_da(s):
    banner()
    hr_title("DA: DEVIL'S ADVOCACY")
    box("Principle", [
        "Argue as forcefully as possible AGAINST the leading conclusion.",
        "State actors deliberately mimic others: TTP compatibility is not attribution.",
    ])
    da = s["da"]
    fa = core.final_assessment(s)
    da["leading_hypothesis"] = prompt("Hypothesis challenged", da["leading_hypothesis"] or (fa["text"] if fa else ""))
    da["alternative_hypothesis"] = prompt("Best alternative explanation", da["alternative_hypothesis"])
    for ch in da["challenges"]:
        print(c(f"\n  [{ch['area']}]", CYAN, BOLD))
        print(c(f"  {ch['hint']}", GRAY))
        ch["argument"] = prompt("  Counter-argument", ch["argument"])
        if ch["argument"]:
            ch["strength"] = prompt_int("  Strength (1 weak → 5 strong)", 1, 5, ch["strength"])
    a = core.analyze_da(da)
    print()
    print(c(f"  Verdict: {a['verdict']} (average {a['average']}/5, {len(a['strong'])} strong)", BOLD))
    da["revised"] = confirm("Does DA change your conclusion?", "y" if da["revised"] else "n")
    if da["revised"]:
        da["new_conclusion"] = prompt("Revised conclusion", da["new_conclusion"])
        da["new_confidence"] = prompt_int("New confidence %", 0, 100, da["new_confidence"] if da["new_confidence"] is not None else 50)
    da["final_note"] = prompt("Final note", da["final_note"])
    success("DA saved.")
    pause()
    return s


# ── REPORT / MENU ──────────────────────────────────────────────────────────

def write_report(s, show=None):
    path = core.report_filename(s)
    with open(path, "w", encoding="utf-8") as f:
        f.write(core.generate_report(s))
    success(f"Flash report written → {path}")
    if show is None:
        show = sys.stdin.isatty() and confirm("Print it here?")
    if show:
        print()
        print(core.generate_report(s))
    return path


def main_menu(s, path):
    methods = {"1": method_ach, "2": method_kac, "3": method_iw, "4": method_da}
    keys = {"1": "ach", "2": "kac", "3": "iw", "4": "da"}
    while True:
        banner()
        m = s["meta"]
        done = core.completion(s)
        print(c(f"  Case: {m['case_id'] or '-'}  |  Analyst: {m['analyst'] or '-'}  |  IOC: {m['ioc'] or '-'}  |  TLP:{m['tlp']}", WHITE, BOLD))
        print(c(f"  File: {path or 'not saved yet'}", GRAY))
        print()
        for k, label in (("0", "Case details"), ("1", "ACH     Analysis of Competing Hypotheses"),
                         ("2", "KAC     Key Assumptions Check"), ("3", "I&W     Indicators & Warnings"),
                         ("4", "DA      Devil's Advocacy"), ("5", "Report  Generate Flash Report"),
                         ("6", "Save"), ("q", "Quit")):
            mark = c(" ✓", GREEN) if done.get(keys.get(k, "meta" if k == "0" else "")) else ""
            print(c(f"  [{k}]", CYAN, BOLD) + f"  {label}{mark}")
        print()
        ch = prompt("Select").lower()
        if ch == "0":
            s = init_session(s)
        elif ch in methods:
            s = methods[ch](s)
        elif ch == "5":
            write_report(s)
            pause()
        elif ch == "6":
            path = prompt("Save as", path or f"session_{m['case_id'] or 'cti'}.yaml")
            core.save_session(s, path)
            success(f"Saved → {path}")
            pause()
            continue
        elif ch in ("q", "quit", "exit"):
            if confirm("Save before quitting?", "y"):
                path = path or f"session_{m['case_id'] or 'cti'}.yaml"
                core.save_session(s, path)
                success(f"Saved → {path}")
            print(c("\n  Goodbye.\n", CYAN))
            return
        else:
            warn("Invalid choice.")
            continue
        if path and (ch in methods or ch == "0"):
            core.save_session(s, path)  # autosave once a file exists


def run(load=None, method=None):
    _force_utf8()
    s = core.load_session(load) if load else core.new_session()
    if method:
        fn = {"ach": method_ach, "kac": method_kac, "iw": method_iw, "da": method_da}.get(method.lower())
        if not fn:
            raise SystemExit(f"Unknown method: {method}. Use ach|kac|iw|da")
        s = fn(s)
    main_menu(s, load)
