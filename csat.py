#!/usr/bin/env python3
"""
CSAT.py — Structured Analytic Techniques for CTI

FIXES v1.1 (minimal patch on original):
  BUG #1 — I&W checkmark never shown in main menu
             label.split("—")[0].strip().lower() gives "i&w" ≠ "iw"
             FIX: explicit dict mapping menu key → session key
  BUG #2 — Accents stripped / color function c() shadowed
             In _identify_diagnostic_evidence, md_table, method_da :
             list/set comprehensions used 'c' as loop var, silently
             overwriting the global color helper c().
             FIX: renamed loop vars to 'cell' / 'ch'
  BUG #3 — YAML load: iw section not detected when loaded from flat YAML
             (s1_status / s1_confirmed keys instead of 'scenarios' list)
             FIX: _iw_has_data() helper checks both structures
  FIX  #4 — UTF-8 forced at startup to avoid accent loss on Windows/some Linux
"""

import os
import sys
import json
import yaml
import datetime
import argparse
import unicodedata
from textwrap import wrap, fill
from copy import deepcopy


# ── FIX #4 : Force UTF-8 output at startup ────────────────────────────────
def _force_utf8():
    for name in ("stdout", "stderr"):
        s = getattr(sys, name, None)
        if s is None:
            continue
        enc = getattr(s, "encoding", "") or ""
        if enc.lower().replace("-", "") not in ("utf8", "utf16", "utf32"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError):
                pass

_force_utf8()


# ── TERMINAL HELPERS ───────────────────────────────────────────────────────

WIDTH = 90

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

BLACK  = "\033[30m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
CYAN   = "\033[36m"
WHITE  = "\033[97m"
GRAY   = "\033[90m"

BG_RED    = "\033[41m"
BG_YELLOW = "\033[43m"
BG_GREEN  = "\033[42m"
BG_BLUE   = "\033[44m"
BG_CYAN   = "\033[46m"

def c(text, *codes):
    return "".join(codes) + str(text) + RESET

def hr(char="─", color=GRAY):
    print(c(char * WIDTH, color))

def hr_title(title, char="─", color=CYAN):
    pad = (WIDTH - len(title) - 2) // 2
    line = char * pad + f" {title} " + char * (WIDTH - pad - len(title) - 2)
    print(c(line[:WIDTH], color, BOLD))

def banner():
    os.system("clear" if os.name == "posix" else "cls")
    print()
    print(c("  ╔══════════════════════════════════════════════════════════════════════════════════════╗", CYAN))
    print(c("  ║", CYAN) + c("  CTI STRUCTURED ANALYTIC TECHNIQUES", WHITE, BOLD) + c("                                                 ║", CYAN))
    print(c("  ║", CYAN) + c("  ACH · Key Assumptions Check · Indicators & Warnings · Devil's Advocacy            ", GRAY) + c("  ║", CYAN))
    print(c("  ╚══════════════════════════════════════════════════════════════════════════════════════╝", CYAN))
    print()

def prompt(msg, default=None, color=YELLOW):
    suffix = f" [{default}]" if default else ""
    try:
        val = input(c(f"  ▶ {msg}{suffix}: ", color)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val if val else (default or "")

def prompt_int(msg, min_val=1, max_val=99, default=None):
    while True:
        raw = prompt(msg, str(default) if default else None)
        try:
            v = int(raw)
            if min_val <= v <= max_val:
                return v
        except ValueError:
            pass
        print(c(f"  Please enter a number between {min_val} and {max_val}.", RED))

def prompt_choice(msg, choices):
    """choices: list of (key, label)"""
    print()
    for key, label in choices:
        print(c(f"  [{key}]", CYAN, BOLD) + f"  {label}")
    print()
    valid = [str(k) for k, _ in choices]
    while True:
        val = prompt(msg).strip()
        val_low = val.lower()
        match = next((v for v in valid if v.lower() == val_low), None)
        if match:
            return match
        print(c(f"  Invalid choice. Options: {', '.join(valid)}", RED))

def prompt_list(msg, hint="(empty line to finish)"):
    """Collect multiple strings until empty input."""
    print(c(f"  {msg} {hint}", GRAY))
    items = []
    i = 1
    while True:
        val = prompt(f"  {i}", color=WHITE)
        if not val:
            break
        items.append(val)
        i += 1
    return items

def confirm(msg):
    val = prompt(f"{msg} [y/n]", "n").lower()
    return val in ("y", "yes")

def info(msg):
    print(c(f"  i  {msg}", BLUE))

def warn(msg):
    print(c(f"  !  {msg}", YELLOW))

def success(msg):
    print(c(f"  v  {msg}", GREEN))

def error_msg(msg):
    print(c(f"  x  {msg}", RED))

def box(title, content_lines, color=CYAN, width=WIDTH-4):
    print(c(f"  ┌─ {title} " + "─" * (width - len(title) - 4) + "┐", color))
    for line in content_lines:
        wrapped = wrap(line, width - 4) or [""]
        for wl in wrapped:
            pad = width - len(wl) - 2
            print(c("  │ ", color) + wl + " " * pad + c("│", color))
    print(c("  └" + "─" * width + "┘", color))
    print()


# ── CONFIDENCE & SCORING ───────────────────────────────────────────────────

CONSISTENCY_SCORES = {
    "CC": ("Consistent Confirming",  "+2", GREEN),
    "C":  ("Consistent",             "+1", GREEN),
    "N":  ("Neutral / N/A",          " 0", GRAY),
    "I":  ("Inconsistent",           "-1", YELLOW),
    "II": ("Highly Inconsistent",    "-2", RED),
}

CONFIDENCE_LEVELS = {
    (75, 100): ("HIGH",   RED,    "Strong evidence base. Attribution supportable."),
    (50,  74): ("MEDIUM", YELLOW, "Reasonable basis. Additional evidence needed."),
    (25,  49): ("LOW",    GRAY,   "Weak basis. Working hypothesis only."),
    (0,   24): ("MINIMAL",GRAY,   "Insufficient evidence. Treat as speculation."),
}

TLP_LEVELS = ["WHITE", "GREEN", "AMBER", "RED"]

def confidence_label(score_pct):
    for (lo, hi), (label, col, desc) in CONFIDENCE_LEVELS.items():
        if lo <= score_pct <= hi:
            return label, col, desc
    return "UNKNOWN", GRAY, ""


# ── SESSION OBJECT ─────────────────────────────────────────────────────────

def new_session():
    return {
        "meta": {
            "created": datetime.datetime.now().isoformat(),
            "updated": datetime.datetime.now().isoformat(),
            "analyst": "",
            "case_id": "",
            "ioc": "",
            "tlp": "WHITE",
            "geopolitical_context": "",
        },
        "ach": None,
        "kac": None,
        "iw": None,
        "da": None,
    }

def save_session(session, path):
    session["meta"]["updated"] = datetime.datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(session, f, allow_unicode=True, sort_keys=False)
    success(f"Session saved → {path}")

def load_session(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── FIX #3 : I&W data detection — handles both YAML structures ────────────
def _iw_has_data(iw_val):
    """
    Return True if the iw section contains usable data.
    Accepts:
      Structure A (interactive): iw.scenarios is a non-empty list
      Structure B (flat YAML):   keys like s1_status, s1_confirmed, etc.
    """
    if not iw_val or not isinstance(iw_val, dict):
        return False
    # Structure A
    if iw_val.get("scenarios"):
        return True
    # Structure B: at least one key matching s<N>_ pattern
    import re
    return any(re.match(r"s\d+_", k) for k in iw_val.keys())


# ── SESSION INIT ───────────────────────────────────────────────────────────

def init_session(session):
    banner()
    hr_title("SESSION INITIALISATION", color=CYAN)
    print()
    meta = session["meta"]
    meta["case_id"]   = prompt("Case ID / reference", meta.get("case_id") or f"CTI-{datetime.date.today().strftime('%Y%m%d')}")
    meta["analyst"]   = prompt("Analyst initials", meta.get("analyst") or "")
    meta["ioc"]       = prompt("IOC under analysis (IP / domain / hash / URL)", meta.get("ioc") or "")
    meta["tlp"]       = prompt_choice("TLP classification", [(t, t) for t in TLP_LEVELS])
    meta["geopolitical_context"] = prompt("Geopolitical / operational context (1 line)", meta.get("geopolitical_context") or "")
    print()
    success("Session initialised.")
    return session


# ═══════════════════════════════════════════════════════════════════════════
# METHOD 1 — ACH (Analysis of Competing Hypotheses)
# ═══════════════════════════════════════════════════════════════════════════

def method_ach(session):
    banner()
    hr_title("ACH — ANALYSIS OF COMPETING HYPOTHESES", color=CYAN)
    print()
    box("ACH Principle", [
        "The goal is NOT to find the hypothesis with the most supporting evidence.",
        "It is to find the hypothesis that can be REFUTED the least.",
        "A good analyst eliminates hypotheses; the last standing is the answer.",
        "Evidence that is consistent with ALL hypotheses has no diagnostic value.",
    ], color=BLUE)

    ach = session.get("ach") or {}

    hr_title("STEP 1 / 8 — Define Hypotheses", char="·", color=YELLOW)
    info("List all PLAUSIBLE hypotheses. Include unlikely ones to avoid tunnel vision.")
    info("Example: H1=APT33, H2=APT34, H3=cybercriminal, H4=insider, H5=unknown actor")
    print()

    existing_h = ach.get("hypotheses", [])
    if existing_h:
        print(c("  Existing hypotheses:", GRAY))
        for i, h in enumerate(existing_h):
            print(f"  H{i+1}: {h['label']} — {h['description']}")
        print()
        if not confirm("Edit hypotheses?"):
            hypotheses = existing_h
        else:
            hypotheses = _collect_hypotheses()
    else:
        hypotheses = _collect_hypotheses()

    if len(hypotheses) < 2:
        warn("ACH requires at least 2 hypotheses. Add more.")
        return session

    hr_title("STEP 2 / 8 — List Evidence & Diagnostics", char="·", color=YELLOW)
    info("List ALL evidence — not just what confirms a hypothesis.")
    info("Include absence of evidence. Include negative indicators.")
    info("Mark source reliability (A=confirmed, B=probably true, C=possibly true, D=unconfirmed)")
    print()

    existing_e = ach.get("evidence", [])
    if existing_e:
        print(c("  Existing evidence:", GRAY))
        for i, e in enumerate(existing_e):
            print(f"  E{i+1} [{e.get('reliability','?')}]: {e['description']}")
        print()
        if not confirm("Edit evidence?"):
            evidence = existing_e
        else:
            evidence = _collect_evidence()
    else:
        evidence = _collect_evidence()

    if not evidence:
        warn("No evidence collected. ACH requires at least 1 evidence item.")
        return session

    hr_title("STEP 3 / 8 — Consistency Matrix", char="·", color=YELLOW)
    info("For each Evidence x Hypothesis cell, score consistency:")
    for code, (label, score, col) in CONSISTENCY_SCORES.items():
        print(c(f"  {code:4s}", col, BOLD) + f" {score}  {label}")
    print()

    matrix = ach.get("matrix", {})
    matrix = _fill_matrix(hypotheses, evidence, matrix)

    scores = _calculate_ach_scores(hypotheses, evidence, matrix)

    hr_title("STEP 4 / 8 — Matrix Results", char="·", color=YELLOW)
    _print_ach_matrix(hypotheses, evidence, matrix, scores)

    hr_title("STEP 5 / 8 — Sensitivity Analysis", char="·", color=YELLOW)
    info("Identify which evidence items are MOST DIAGNOSTIC.")
    info("If your conclusion changes when you remove one piece of evidence — it's fragile.")
    _sensitivity_analysis(hypotheses, evidence, matrix, scores)

    hr_title("STEP 6 / 8 — Diagnostic Evidence", char="·", color=YELLOW)
    _identify_diagnostic_evidence(hypotheses, evidence, matrix)

    hr_title("STEP 7 / 8 — Analytical Conclusion", char="·", color=YELLOW)
    ranked = sorted(scores.items(), key=lambda x: x[1]["total"], reverse=True)
    winner_idx = ranked[0][0]
    winner = hypotheses[winner_idx]

    print(c(f"\n  LEADING HYPOTHESIS: H{winner_idx+1} — {winner['label']}", GREEN, BOLD))
    print(c(f"  {winner['description']}", WHITE))
    print()

    conf_input = prompt_int("Analyst confidence % (0-100)", 0, 100, default=scores[winner_idx]["confidence_pct"])
    conf_lbl, conf_col, conf_desc = confidence_label(conf_input)
    print(c(f"\n  Confidence: {conf_lbl} ({conf_input}%)", conf_col, BOLD))
    print(c(f"  {conf_desc}", conf_col))
    print()

    analyst_rationale = prompt("Analytical rationale (1-2 sentences)")
    caveats = prompt("Key caveats / what would change this conclusion")

    hr_title("STEP 8 / 8 — Indicators to Monitor", char="·", color=YELLOW)
    info("What new evidence would CONFIRM or REFUTE the leading hypothesis?")
    confirm_indicators = prompt_list("Evidence that would CONFIRM H" + str(winner_idx+1))
    refute_indicators  = prompt_list("Evidence that would REFUTE H"  + str(winner_idx+1))

    session["ach"] = {
        "hypotheses": hypotheses,
        "evidence": evidence,
        "matrix": matrix,
        "scores": scores,
        "conclusion": {
            "leading_hypothesis": winner_idx,
            "confidence_pct": conf_input,
            "confidence_label": conf_lbl,
            "rationale": analyst_rationale,
            "caveats": caveats,
            "confirm_indicators": confirm_indicators,
            "refute_indicators": refute_indicators,
        }
    }

    print()
    success("ACH analysis saved to session.")
    input(c("\n  Press Enter to return to menu...", GRAY))
    return session


def _collect_hypotheses():
    hypotheses = []
    print(c("  Enter hypotheses (empty label to finish):", GRAY))
    i = 1
    while True:
        label = prompt(f"  H{i} label (e.g. 'APT33')")
        if not label:
            break
        desc  = prompt(f"  H{i} description")
        hypotheses.append({"label": label, "description": desc})
        i += 1
    return hypotheses


def _collect_evidence():
    evidence = []
    print(c("  Enter evidence items (empty to finish):", GRAY))
    i = 1
    while True:
        desc = prompt(f"  E{i} description")
        if not desc:
            break
        rel  = prompt(f"  E{i} reliability [A/B/C/D]", "B").upper()
        source = prompt(f"  E{i} source (Shodan / VT / OSINT / HUMINT / etc.)")
        evidence.append({"description": desc, "reliability": rel, "source": source})
        i += 1
    return evidence


def _fill_matrix(hypotheses, evidence, existing_matrix):
    matrix = deepcopy(existing_matrix)
    valid_scores = list(CONSISTENCY_SCORES.keys())
    print(c(f"  Score each Evidence x Hypothesis cell.", GRAY))
    print(c(f"  Valid scores: {' / '.join(valid_scores)}", GRAY))
    print()
    for ei, e in enumerate(evidence):
        print(c(f"\n  E{ei+1}: {e['description']}", WHITE, BOLD))
        for hi, h in enumerate(hypotheses):
            cell_key = f"{ei}_{hi}"
            existing = matrix.get(cell_key, "N")
            score = prompt(f"    H{hi+1} [{h['label']}]", existing).upper()
            if score not in valid_scores:
                score = "N"
            matrix[cell_key] = score
    return matrix


def _calculate_ach_scores(hypotheses, evidence, matrix):
    scores = {}
    for hi in range(len(hypotheses)):
        total = 0
        inconsistencies = 0
        for ei in range(len(evidence)):
            cell = matrix.get(f"{ei}_{hi}", "N")
            score_map = {"CC": 2, "C": 1, "N": 0, "I": -1, "II": -2}
            val = score_map.get(cell, 0)
            total += val
            if val < 0:
                inconsistencies += abs(val)

        max_possible = len(evidence) * 2
        if max_possible > 0:
            conf_pct = max(0, min(100, int(((total + max_possible) / (2 * max_possible)) * 100)))
        else:
            conf_pct = 0

        scores[hi] = {
            "total": total,
            "inconsistencies": inconsistencies,
            "confidence_pct": conf_pct,
        }
    return scores


def _print_ach_matrix(hypotheses, evidence, matrix, scores):
    h_labels = [f"H{i+1}:{h['label'][:8]}" for i, h in enumerate(hypotheses)]
    col_w = max(10, max(len(l) for l in h_labels) + 2)
    e_col_w = 42

    header = c(f"  {'Evidence':<{e_col_w}}", GRAY)
    for hl in h_labels:
        header += c(f" {hl:^{col_w}}", CYAN)
    print(header)
    hr("─", GRAY)

    for ei, e in enumerate(evidence):
        desc = e['description'][:e_col_w-2]
        rel  = e.get('reliability', '?')
        row = f"  {c(f'E{ei+1}', YELLOW)}[{c(rel, CYAN)}] {desc:<{e_col_w-6}}"
        for hi in range(len(hypotheses)):
            cell = matrix.get(f"{ei}_{hi}", "N")
            _, score_str, col = CONSISTENCY_SCORES.get(cell, ("?", "?", GRAY))
            row += f" {c(f'{cell:^{col_w}}', col)}"
        print(row)

    hr("─", GRAY)
    score_row = c(f"  {'SCORE ( up = fewer inconsistencies)':<{e_col_w}}", BOLD)
    for hi, s in scores.items():
        val = s["total"]
        col = GREEN if val > 0 else RED if val < 0 else GRAY
        score_row += c(f" {val:^{col_w}}", col, BOLD)
    print(score_row)

    inconsistency_row = c(f"  {'INCONSISTENCIES ( down = stronger H)':<{e_col_w}}", BOLD)
    for hi, s in scores.items():
        inc = s["inconsistencies"]
        col = GREEN if inc == 0 else YELLOW if inc <= 2 else RED
        inconsistency_row += c(f" {inc:^{col_w}}", col, BOLD)
    print(inconsistency_row)

    conf_row = c(f"  {'CONFIDENCE %':<{e_col_w}}", BOLD)
    for hi, s in scores.items():
        pct = s["confidence_pct"]
        lbl, col, _ = confidence_label(pct)
        conf_row += c(f" {pct:^{col_w}}", col, BOLD)
    print(conf_row)
    print()


def _sensitivity_analysis(hypotheses, evidence, matrix, scores):
    original_ranking = sorted(scores.keys(), key=lambda x: scores[x]["total"], reverse=True)
    original_winner = original_ranking[0]
    fragile_evidence = []

    for ei in range(len(evidence)):
        reduced_matrix = {k: v for k, v in matrix.items() if not k.startswith(f"{ei}_")}
        reduced_evidence = [e for j, e in enumerate(evidence) if j != ei]
        reduced_scores = _calculate_ach_scores(hypotheses, reduced_evidence, reduced_matrix)
        new_ranking = sorted(reduced_scores.keys(), key=lambda x: reduced_scores[x]["total"], reverse=True)
        if new_ranking[0] != original_winner:
            fragile_evidence.append(ei)

    if fragile_evidence:
        warn("FRAGILE CONCLUSION — removing these evidence items changes the winner:")
        for ei in fragile_evidence:
            print(c(f"  !  E{ei+1}: {evidence[ei]['description']}", YELLOW))
        print()
        warn("Validate these evidence items carefully before finalising.")
    else:
        success("ROBUST CONCLUSION — ranking is stable across sensitivity checks.")
    print()


# ── FIX #2a : renamed loop var 'c' → 'cell' to avoid shadowing c() ────────
def _identify_diagnostic_evidence(hypotheses, evidence, matrix):
    info("Diagnostic evidence = items that DIFFERENTIATE hypotheses (not neutral for all).")
    print()
    for ei, e in enumerate(evidence):
        # FIX: was `set(c for c in cells ...)` and `all(c == ...)` — 'c' shadowed color helper
        cells = [matrix.get(f"{ei}_{hi}", "N") for hi in range(len(hypotheses))]
        unique_non_neutral = set(cell for cell in cells if cell != "N")
        if len(unique_non_neutral) > 0 and not all(cell == cells[0] for cell in cells):
            print(c(f"  * DIAGNOSTIC  E{ei+1}: {e['description']}", GREEN))
        elif all(cell == "N" for cell in cells):
            print(c(f"  o NO VALUE    E{ei+1}: {e['description']}", GRAY))
        else:
            print(c(f"  . WEAK        E{ei+1}: {e['description']}", YELLOW))
    print()


# ═══════════════════════════════════════════════════════════════════════════
# METHOD 2 — KEY ASSUMPTIONS CHECK (KAC)
# ═══════════════════════════════════════════════════════════════════════════

def method_kac(session):
    banner()
    hr_title("KAC — KEY ASSUMPTIONS CHECK", color=CYAN)
    print()
    box("KAC Principle", [
        "Analysts make assumptions when evidence is incomplete — which is always.",
        "Hidden assumptions drive conclusions more than evidence does.",
        "The KAC forces you to surface, challenge, and rate each assumption.",
        "Ask: 'What would have to be true for my analysis to be wrong?'",
    ], color=BLUE)

    kac = session.get("kac") or {}

    hr_title("STEP 1 — Identify Assumptions", char="·", color=YELLOW)
    info("List all assumptions behind your current analysis.")
    info("Include assumptions about: actor capability, geopolitical context, IOC attribution,")
    info("infrastructure ownership, intent, and what evidence is NOT present.")
    print()

    existing_assumptions = kac.get("assumptions", [])
    if existing_assumptions:
        print(c("  Existing assumptions:", GRAY))
        for i, a in enumerate(existing_assumptions):
            print(f"  A{i+1}: {a['text']}")
        print()
        if confirm("Edit assumptions?"):
            assumptions = _collect_assumptions()
        else:
            assumptions = existing_assumptions
    else:
        assumptions = _collect_assumptions()

    if not assumptions:
        warn("No assumptions collected.")
        return session

    hr_title("STEP 2 — Rate Each Assumption", char="·", color=YELLOW)
    info("For each assumption, rate:")
    print(c("  CERTAINTY:", CYAN)  + "  How certain are you this is true? (1=uncertain -> 5=certain)")
    print(c("  IMPACT:", CYAN)     + "     If wrong, how much does it change your conclusion? (1=minor -> 5=major)")
    print()

    rated = []
    for i, a in enumerate(assumptions):
        print(c(f"\n  A{i+1}: {a['text']}", WHITE, BOLD))
        existing_certainty = a.get("certainty", 3)
        existing_impact    = a.get("impact", 3)
        certainty = prompt_int("    Certainty  (1-5)", 1, 5, default=existing_certainty)
        impact    = prompt_int("    Impact     (1-5)", 1, 5, default=existing_impact)
        challenge = prompt("    Challenge: what would prove this assumption wrong?")
        rated.append({
            "text": a["text"],
            "certainty": certainty,
            "impact": impact,
            "challenge": challenge,
        })

    hr_title("STEP 3 — Assumption Criticality Matrix", char="·", color=YELLOW)
    _print_kac_matrix(rated)

    critical = [a for a in rated if a["certainty"] <= 2 and a["impact"] >= 4]
    if critical:
        print()
        warn("CRITICAL ASSUMPTIONS (low certainty + high impact):")
        for a in critical:
            print(c(f"  !  {a['text']}", YELLOW))
            print(c(f"     Challenge: {a['challenge']}", GRAY))
    else:
        success("No critical assumption vulnerabilities identified.")

    session["kac"] = {"assumptions": rated}
    print()
    success("KAC analysis saved to session.")
    input(c("\n  Press Enter to return to menu...", GRAY))
    return session


def _collect_assumptions():
    assumptions = []
    print(c("  Enter assumptions (empty to finish):", GRAY))
    i = 1
    while True:
        text = prompt(f"  A{i}")
        if not text:
            break
        assumptions.append({"text": text})
        i += 1
    return assumptions


def _print_kac_matrix(rated):
    print(c(f"  {'#':<4} {'CERTAINTY':<12} {'IMPACT':<10} {'RISK':<10} {'ASSUMPTION'}", GRAY))
    hr("─", GRAY)
    for i, a in enumerate(rated):
        cert = a["certainty"]
        imp  = a["impact"]
        risk = (6 - cert) * imp
        risk_label = "CRITICAL" if risk >= 16 else "HIGH" if risk >= 10 else "MEDIUM" if risk >= 5 else "LOW"
        risk_col   = RED if risk >= 16 else YELLOW if risk >= 10 else CYAN if risk >= 5 else GREEN
        cert_bar   = c("X" * cert + "." * (5-cert), GREEN if cert >= 4 else YELLOW if cert >= 2 else RED)
        imp_bar    = c("X" * imp  + "." * (5-imp),  RED if imp >= 4 else YELLOW if imp >= 2 else GREEN)
        text_short = a["text"][:45]
        print(f"  A{i+1:<3} {cert_bar}  {imp_bar}  {c(f'{risk_label:<10}', risk_col)} {text_short}")
    print()


# ═══════════════════════════════════════════════════════════════════════════
# METHOD 3 — INDICATORS & WARNINGS (I&W)
# ═══════════════════════════════════════════════════════════════════════════

def method_iw(session):
    banner()
    hr_title("I&W — INDICATORS & WARNINGS", color=CYAN)
    print()
    box("I&W Principle", [
        "Define BEFORE the event what you expect to observe IF a hypothesis is true.",
        "Indicators are observable facts; warnings are analytical conclusions.",
        "The absence of expected indicators is itself evidence.",
        "In CTI: map each TTP to a detectable observable in your telemetry.",
    ], color=BLUE)

    iw = session.get("iw") or {}

    hr_title("STEP 1 — Define Scenarios", char="·", color=YELLOW)
    info("Each scenario = a specific threat hypothesis to monitor.")
    info("Example: 'APT34 targeting energy sector', 'DPRK crypto theft via LinkedIn'")
    print()

    existing_scenarios = iw.get("scenarios", [])
    if existing_scenarios and not confirm("Redefine scenarios?"):
        scenarios = existing_scenarios
    else:
        scenarios = []
        raw = prompt_list("Scenario labels")
        for s in raw:
            scenarios.append({"label": s, "indicators": []})

    if not scenarios:
        warn("No scenarios defined.")
        return session

    hr_title("STEP 2 — Define Indicators per Scenario", char="·", color=YELLOW)
    info("For each scenario, define observable indicators split into:")
    print(c("  CONFIRM", GREEN) + " — would confirm the scenario is active")
    print(c("  REFUTE ", RED)   + " — would refute the scenario")
    print(c("  MONITOR", CYAN)  + " — ambiguous, needs further analysis")
    print()

    for si, scenario in enumerate(scenarios):
        print(c(f"\n  Scenario S{si+1}: {scenario['label']}", WHITE, BOLD))
        existing_ind = scenario.get("indicators", [])
        if existing_ind and not confirm(f"  Edit indicators for S{si+1}?"):
            continue

        indicators = []
        for itype, icolor, hint in [
            ("CONFIRM", GREEN, "e.g. FortiGate masked header, TINYSHELL process, TACACS+ binary replaced"),
            ("REFUTE",  RED,   "e.g. firmware updated, no EOL devices, no matching TTPs"),
            ("MONITOR", CYAN,  "e.g. unusual DNS queries, anomalous login times"),
        ]:
            print(c(f"\n    {itype} indicators:", icolor))
            print(c(f"    Hint: {hint}", GRAY))
            items = prompt_list(f"    {itype}")
            for item in items:
                indicators.append({
                    "text": item,
                    "type": itype,
                    "mitre": prompt(f"      MITRE ATT&CK technique (e.g. T1014) for: '{item[:40]}'", ""),
                    "source": prompt(f"      Data source (Shodan/VT/SIEM/EDR/etc.)", ""),
                    "observed": None,
                })
        scenarios[si]["indicators"] = indicators

    hr_title("STEP 3 — Mark Observed Indicators", char="·", color=YELLOW)
    info("For each indicator, mark if it has been observed in your investigation.")
    print()

    for si, scenario in enumerate(scenarios):
        print(c(f"\n  S{si+1}: {scenario['label']}", WHITE, BOLD))
        for ii, ind in enumerate(scenario.get("indicators", [])):
            itype = ind["type"]
            col   = GREEN if itype == "CONFIRM" else RED if itype == "REFUTE" else CYAN
            print(c(f"  [{itype}]", col) + f" {ind['text'][:60]}")
            obs = prompt("    Observed? [y/n/unknown]", ind.get("observed") or "unknown").lower()
            if obs in ("y", "yes"):
                obs = "YES"
            elif obs in ("n", "no"):
                obs = "NO"
            else:
                obs = "UNKNOWN"
            ind["observed"] = obs
            if obs == "YES":
                note = prompt("    Observation note / evidence ref")
                ind["observation_note"] = note

    hr_title("STEP 4 — I&W Assessment", char="·", color=YELLOW)
    _print_iw_results(scenarios)

    session["iw"] = {"scenarios": scenarios}
    print()
    success("I&W analysis saved to session.")
    input(c("\n  Press Enter to return to menu...", GRAY))
    return session


def _print_iw_results(scenarios):
    for si, scenario in enumerate(scenarios):
        inds = scenario.get("indicators", [])
        confirmed = [i for i in inds if i["observed"] == "YES" and i["type"] == "CONFIRM"]
        refuted   = [i for i in inds if i["observed"] == "YES" and i["type"] == "REFUTE"]
        missing   = [i for i in inds if i["observed"] == "NO"  and i["type"] == "CONFIRM"]

        total_confirm = len([i for i in inds if i["type"] == "CONFIRM"])
        score_pct = int((len(confirmed) / total_confirm * 100)) if total_confirm else 0
        lbl, col, _ = confidence_label(score_pct)

        print()
        hr_title(f"S{si+1}: {scenario['label']}", char="·", color=CYAN)
        print(c(f"  Confirmed indicators : ", GREEN) + c(f"{len(confirmed)}/{total_confirm}", GREEN, BOLD))
        print(c(f"  Refuting indicators  : ", RED)   + c(str(len(refuted)), RED, BOLD))
        print(c(f"  Missing expected     : ", YELLOW) + c(str(len(missing)), YELLOW, BOLD))
        print(c(f"  Assessment           : {lbl} ({score_pct}%)", col, BOLD))
        print()

        if refuted:
            warn("Refuting evidence observed:")
            for r in refuted:
                print(c(f"  x {r['text']}", RED))
        if missing:
            print(c("  Expected but NOT observed (weakens hypothesis):", GRAY))
            for m in missing:
                print(c(f"  ? {m['text']}", YELLOW))


# ═══════════════════════════════════════════════════════════════════════════
# METHOD 4 — DEVIL'S ADVOCACY (DA)
# ═══════════════════════════════════════════════════════════════════════════

def method_da(session):
    banner()
    hr_title("DA — DEVIL'S ADVOCACY", color=CYAN)
    print()
    box("Devil's Advocacy Principle", [
        "Assign a role to argue as forcefully as possible AGAINST the leading conclusion.",
        "In CTI context: assume your leading hypothesis is WRONG. Build the counter-case.",
        "Especially critical for APT attribution: state actors deliberately mimic others.",
        "Ask: could this be a false flag? Could another actor fit the evidence equally well?",
        "Force yourself to identify evidence you may have ignored or underweighted.",
    ], color=BLUE)

    da = session.get("da") or {}

    leading = ""
    if session.get("ach") and session["ach"].get("conclusion"):
        ach = session["ach"]
        hi  = ach["conclusion"]["leading_hypothesis"]
        h   = ach["hypotheses"][hi]
        leading = f"H{hi+1}: {h['label']} — {h['description']}"
        print(c(f"  Leading hypothesis from ACH: {leading}", WHITE, BOLD))
    else:
        leading = prompt("  What is the leading hypothesis to challenge?")
    print()

    hr_title("STEP 1 — Steel-Man the Alternative", char="·", color=YELLOW)
    info("Build the strongest possible case AGAINST your leading hypothesis.")
    info("In CTI: consider false flag, misattribution, shared tooling, coincidence.")
    print()

    alternative = prompt("  Alternative hypothesis (the counter-argument)")
    print()

    challenges = []
    challenge_areas = [
        ("False Flag",        "Could another actor be mimicking the TTPs of your leading hypothesis?"),
        ("Shared Tooling",    "Are the tools used publicly available? Could any actor have used them?"),
        ("Coincidence",       "Could the behavioral signals be explained by non-malicious activity?"),
        ("Misidentification", "Could the infrastructure belong to a different actor or be compromised?"),
        ("Confirmation Bias", "What evidence did you find FIRST that anchored your conclusion?"),
        ("Missing Evidence",  "What evidence would you expect IF true, but you have NOT found?"),
    ]

    print(c("  Challenge each area — provide your best counter-argument:", GRAY))
    for area, hint in challenge_areas:
        print(c(f"\n  [{area}]", CYAN, BOLD))
        print(c(f"  Hint: {hint}", GRAY))
        arg = prompt(f"  Your counter-argument")
        strength = prompt_int(f"  Strength of this counter-argument (1=weak -> 5=strong)", 1, 5, default=2)
        challenges.append({"area": area, "hint": hint, "argument": arg, "strength": strength})

    hr_title("STEP 2 — Devil's Advocacy Results", char="·", color=YELLOW)
    _print_da_results(leading, alternative, challenges)

    hr_title("STEP 3 — Post-DA Conclusion", char="·", color=YELLOW)
    # FIX #2b: was [c for c in challenges ...] — 'c' shadowed color helper
    strong_challenges = [ch for ch in challenges if ch["strength"] >= 4]
    if strong_challenges:
        warn(f"{len(strong_challenges)} strong challenge(s) identified — review your hypothesis.")
        for sc in strong_challenges:
            print(c(f"  !  [{sc['area']}] {sc['argument']}", YELLOW))
        print()

    revised = prompt("  Does DA change your conclusion? [y/n]", "n").lower() in ("y", "yes")
    if revised:
        new_conclusion = prompt("  Revised conclusion after DA")
        new_confidence = prompt_int("  New confidence % (0-100)", 0, 100)
    else:
        new_conclusion = ""
        new_confidence = None

    final_note = prompt("  Final note for the record")

    session["da"] = {
        "leading_hypothesis": leading,
        "alternative_hypothesis": alternative,
        "challenges": challenges,
        "revised": revised,
        "new_conclusion": new_conclusion,
        "new_confidence": new_confidence,
        "final_note": final_note,
    }

    print()
    success("Devil's Advocacy analysis saved to session.")
    input(c("\n  Press Enter to return to menu...", GRAY))
    return session


def _print_da_results(leading, alternative, challenges):
    print(c(f"  Hypothesis challenged : {leading}", WHITE))
    print(c(f"  Alternative           : {alternative}", YELLOW))
    print()
    print(c(f"  {'AREA':<22} {'STRENGTH':<12} {'ARGUMENT'}", GRAY))
    hr("─", GRAY)
    for ch in challenges:
        strength = ch["strength"]
        col = RED if strength >= 4 else YELLOW if strength >= 3 else GREEN
        bar = "X" * strength + "." * (5 - strength)
        arg_short = ch["argument"][:50] if ch["argument"] else c("[no argument]", GRAY)
        print(f"  {ch['area']:<22} {c(bar, col)}  {arg_short}")
    print()


# ── REPORT GENERATOR ───────────────────────────────────────────────────────

def generate_report(session):
    """Generate a rich structured Flash Report from all completed analyses."""

    def safe(text):
        """Return text as-is if terminal handles it; strip accents as last resort."""
        s = str(text)
        try:
            s.encode(sys.stdout.encoding or "utf-8")
            return s
        except (UnicodeEncodeError, LookupError):
            return "".join(
                ch for ch in unicodedata.normalize("NFD", s)
                if unicodedata.category(ch) != "Mn"
            )

    # FIX #2c: renamed loop var 'c' → 'cell' in md_table inner join
    def md_table(headers, rows):
        lines = []
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
        return lines

    banner()
    hr_title("FLASH REPORT GENERATION", color=CYAN)

    meta = session.get("meta", {})
    lines = []

    # ── HEADER ─────────────────────────────────────────────────────────────
    lines.append("# CTI STRUCTURED ANALYTICAL REPORT")
    lines.append("## Case: {}".format(meta.get("case_id", "N/A")))
    lines.append("**Date:** {}".format(datetime.date.today().isoformat()))
    lines.append("**Analyst:** {}".format(meta.get("analyst", "N/A")))
    lines.append("**TLP:** {}".format(meta.get("tlp", "WHITE")))
    lines.append("**IOC:** `{}`".format(meta.get("ioc", "N/A")))
    lines.append("**Context:** {}".format(
        meta.get("geopolitical_context", meta.get("context", "N/A"))
    ))
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── ACH ────────────────────────────────────────────────────────────────
    ach = session.get("ach")
    if ach and ach.get("conclusion"):
        c_data = ach["conclusion"]

        hi = c_data.get("leading_hypothesis", 0)
        if isinstance(hi, str):
            raw = hi.strip()
            if raw.upper().startswith("H"):
                try:
                    hi = int(raw[1:]) - 1
                except ValueError:
                    hi = 0
            else:
                try:
                    hi = int(raw)
                except ValueError:
                    hi = 0
        hi = max(0, min(int(hi), len(ach.get("hypotheses", [{}])) - 1))

        h = ach.get("hypotheses", [{}])[hi]
        lines.append("## ACH -- Analysis of Competing Hypotheses")
        lines.append("")
        lines.append("**Leading Hypothesis:** H{} -- {}: {}".format(
            hi + 1, h.get("label", "N/A"), h.get("description", "N/A")
        ))
        lines.append("**Confidence:** {} ({}%)".format(
            c_data.get("confidence_label", "N/A"),
            c_data.get("confidence_pct", "N/A"),
        ))
        lines.append("**Rationale:** {}".format(c_data.get("rationale", "N/A")))
        lines.append("**Caveats:** {}".format(c_data.get("caveats", "N/A")))
        lines.append("")

        lines.append("### Hypotheses Scored")
        lines.append("")
        hyp_rows = []
        eliminated = []
        for i, hx in enumerate(ach.get("hypotheses", [])):
            s = (ach.get("scores", {}).get(i)
                 or ach.get("scores", {}).get(str(i))
                 or {})
            total = s.get("total", 0)
            inc   = s.get("inconsistencies", 0)
            conf  = s.get("confidence_pct", 0)
            marker = "LEADING" if i == hi else ""
            hyp_rows.append([
                "H{} -- {}".format(i + 1, hx.get("label", "?")),
                "{:+d}".format(total) if isinstance(total, int) else total,
                inc,
                "{}%".format(conf),
                marker,
            ])
            if inc > 0 or (isinstance(total, int) and total < 0):
                eliminated.append("H{} -- {} ({} inconsistencies)".format(
                    i + 1, hx.get("label", "?"), inc
                ))
        lines += md_table(
            ["Hypothesis", "Score", "Inconsistencies", "Confidence", "Status"],
            hyp_rows
        )
        lines.append("")

        if eliminated:
            lines.append("**Hypotheses eliminated:** " + " | ".join(eliminated))
            lines.append("")

        confirm_inds = c_data.get("confirm_indicators", [])
        refute_inds  = c_data.get("refute_indicators", [])
        if confirm_inds or refute_inds:
            lines.append("### Indicators to Monitor")
            lines.append("")
            if confirm_inds:
                lines.append("**CONFIRM H{}:**".format(hi + 1))
                for ind in confirm_inds:
                    lines.append("- {}".format(ind))
            if refute_inds:
                lines.append("")
                lines.append("**REFUTE H{}:**".format(hi + 1))
                for ind in refute_inds:
                    lines.append("- {}".format(ind))
            lines.append("")

    # ── KAC ────────────────────────────────────────────────────────────────
    kac = session.get("kac")
    if kac and kac.get("assumptions"):
        lines.append("---")
        lines.append("")
        lines.append("## KAC -- Key Assumptions Check")
        lines.append("")

        kac_rows = []
        critical = []
        for i, a in enumerate(kac["assumptions"]):
            cert = a.get("certainty", "?")
            imp  = a.get("impact", "?")
            risk = a.get("risk", "N/A")
            if risk == "N/A" and isinstance(cert, int) and isinstance(imp, int):
                rv = (6 - cert) * imp
                risk = "CRITICAL" if rv >= 16 else "HIGH" if rv >= 10 else "MEDIUM" if rv >= 5 else "LOW"
            text = a.get("text", "N/A")
            chal = a.get("challenge", "N/A")
            kac_rows.append([
                "A{}".format(i + 1),
                text,
                "{}/5".format(cert),
                "{}/5".format(imp),
                risk,
                chal,
            ])
            if risk in ("CRITICAL",) or (
                isinstance(cert, int) and isinstance(imp, int)
                and cert <= 2 and imp >= 4
            ):
                critical.append((i + 1, text, chal))

        lines += md_table(
            ["#", "Assumption", "Certainty", "Impact", "Risk", "Challenge"],
            kac_rows
        )
        lines.append("")

        if critical:
            lines.append("**Critical assumptions flagged:**")
            for num, text, chal in critical:
                lines.append("- **A{}** -- {}: `{}`".format(num, text, chal))
            lines.append("")

    # ── I&W ────────────────────────────────────────────────────────────────
    # FIX #3: use _iw_has_data() — detects both interactive and flat YAML structures
    iw = session.get("iw")
    if _iw_has_data(iw):
        lines.append("---")
        lines.append("")
        lines.append("## I&W -- Indicators & Warnings")
        lines.append("")

        # Structure A: interactive — has 'scenarios' list
        if iw.get("scenarios"):
            for si, scenario in enumerate(iw["scenarios"]):
                label = scenario.get("label", "N/A")
                inds  = scenario.get("indicators", [])

                confirmed_list = [ind for ind in inds if ind.get("observed") == "YES" and ind.get("type") == "CONFIRM"]
                total_c        = len([ind for ind in inds if ind.get("type") == "CONFIRM"])
                score_pct      = int(len(confirmed_list) / total_c * 100) if total_c else 0
                lbl, _, _      = confidence_label(score_pct)

                lines.append("### S{}: {}".format(si + 1, label))
                lines.append("")
                lines.append("**Assessment: {}** -- Confirmed: {}/{} expected indicators".format(
                    lbl, len(confirmed_list), total_c
                ))
                lines.append("")

                if inds:
                    iw_rows = []
                    for ind in inds:
                        obs    = ind.get("observed", "UNKNOWN")
                        marker = "**YES**" if obs == "YES" else "NO" if obs == "NO" else "?"
                        note   = ind.get("observation_note", ind.get("note", ""))
                        iw_rows.append([
                            ind.get("type", "?"),
                            ind.get("text", "N/A"),
                            ind.get("mitre", ""),
                            marker,
                            note,
                        ])
                    lines += md_table(["Type", "Indicator", "MITRE", "Observed", "Note"], iw_rows)
                lines.append("")

        # Structure B: flat YAML (s1_status, s1_confirmed, etc.)
        else:
            import re
            scenario_nums = sorted(set(
                int(m.group(1))
                for k in iw.keys()
                for m in [re.match(r"s(\d+)_", k)]
                if m
            ))
            lines.append("*I&W loaded from YAML. Run method [3] to edit interactively.*")
            lines.append("")
            for sn in scenario_nums:
                prefix = f"s{sn}_"
                sk = {k[len(prefix):]: v for k, v in iw.items() if k.startswith(prefix)}
                lines.append("### S{}: {}".format(sn, sk.get("label", f"Scenario {sn}")))
                lines.append("")
                lines.append("**Status:** {}  |  **Confirmed:** {}/{}".format(
                    sk.get("status", "N/A"),
                    sk.get("confirmed", "?"),
                    sk.get("total", "?"),
                ))
                lines.append("")

        # Optional warning level block
        if iw.get("warning_level"):
            lines.append("### WARNING LEVEL {}".format(iw["warning_level"]))
            lines.append("")
            lines.append("**Trigger:** {}".format(iw.get("trigger", "N/A")))
            lines.append("**Escalation required:** {}".format(iw.get("escalation_required", False)))
            actions = iw.get("immediate_actions", [])
            if actions:
                lines.append("")
                lines.append("**Immediate Actions (priority order):**")
                for n, action in enumerate(actions, 1):
                    lines.append("{}. {}".format(n, action))
            lines.append("")

    # ── DA ─────────────────────────────────────────────────────────────────
    da = session.get("da")
    if da:
        lines.append("---")
        lines.append("")
        lines.append("## DA -- Devil's Advocacy")
        lines.append("")
        lines.append("**Leading hypothesis challenged:** {}".format(da.get("leading_hypothesis", "N/A")))
        lines.append("**Alternative:** {}".format(da.get("alternative_hypothesis", "N/A")))
        lines.append("")

        challenges = da.get("challenges", [])
        if challenges:
            lines.append("### Challenge Areas")
            lines.append("")
            da_rows = []
            strong  = []
            for i, ch in enumerate(challenges):
                strength = ch.get("strength", 0)
                arg      = ch.get("argument", "N/A")
                area     = ch.get("area", "?")
                da_rows.append([
                    "DA{}".format(i + 1),
                    area,
                    "{}/5".format(strength),
                    arg,
                ])
                if strength >= 4:
                    strong.append("DA{} -- {} ({}/5)".format(i + 1, area, strength))
            lines += md_table(["#", "Area", "Strength", "Argument"], da_rows)
            lines.append("")
            if strong:
                lines.append("**Strong challenges identified (strength >= 4/5):** {}".format(" | ".join(strong)))
                lines.append("")

        if da.get("revised"):
            lines.append("### Revised Conclusion")
            lines.append("")
            lines.append(da.get("new_conclusion", "N/A"))
            lines.append("")
            lines.append("**Post-DA confidence:** {}%".format(da.get("new_confidence", "N/A")))
            lines.append("")

        lines.append("**Final note:** {}".format(da.get("final_note", "N/A")))
        lines.append("")

    # ── IOC SUMMARY ────────────────────────────────────────────────────────
    iocs = session.get("iocs")
    if iocs:
        lines.append("---")
        lines.append("")
        lines.append("## IOC Summary")
        lines.append("")
        ioc_rows = []
        for key, label in [("block","**BLOCK**"), ("watch","**WATCH**"), ("monitor","MONITOR"), ("tls","PIVOT")]:
            for entry in iocs.get(key, []):
                if isinstance(entry, dict):
                    val  = entry.get("thumbprint", entry.get("value", str(entry)))
                    note = entry.get("note", "")
                    ioc_rows.append([label, val, note])
                else:
                    ioc_rows.append([label, str(entry), ""])
        if ioc_rows:
            lines += md_table(["Status", "IOC", "Note"], ioc_rows)
            lines.append("")

    # ── GAPS ───────────────────────────────────────────────────────────────
    gaps = session.get("next_pivot") or session.get("gaps")
    if gaps:
        lines.append("---")
        lines.append("")
        lines.append("## Gaps -- Next Actions")
        lines.append("")
        if isinstance(gaps, dict):
            pmap = {"priority_1":"P1","priority_2":"P2","priority_3":"P3","priority_4":"P4","priority_5":"P5"}
            lines += md_table(["Priority","Action"], [[pmap.get(k,k), str(v)] for k,v in sorted(gaps.items())])
        elif isinstance(gaps, list):
            for g in gaps:
                lines.append("- {}".format(g))
        lines.append("")

    # ── FOOTER ─────────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("*Generated by CSAT.py -- CTI Structured Analytic Techniques*")
    lines.append("*TLP: {}*".format(meta.get("tlp", "WHITE")))

    report_path = "flash_report_{}_{}.md".format(
        meta.get("case_id", "cti"),
        datetime.date.today().isoformat(),
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    success("Flash Report written -> {}".format(report_path))
    print()

    if confirm("Print report to terminal?"):
        print()
        for line in lines:
            try:
                print("  {}".format(line))
            except UnicodeEncodeError:
                print("  {}".format(safe(line)))

    return report_path


# ── MAIN MENU ──────────────────────────────────────────────────────────────

MENU_ITEMS = [
    ("0", "Initialise / edit session metadata"),
    ("1", "ACH    — Analysis of Competing Hypotheses"),
    ("2", "KAC    — Key Assumptions Check"),
    ("3", "I&W    — Indicators & Warnings"),
    ("4", "DA     — Devil's Advocacy"),
    ("5", "Report — Generate Flash Report"),
    ("6", "Save   — Save session to YAML"),
    ("q", "Quit"),
]

# ── FIX #1 : explicit menu key → session key mapping ──────────────────────
# Replaces the broken: label.split("—")[0].strip().lower()
# which gave "i&w" (never matching "iw" in completed set).
_MENU_KEY_TO_SESSION = {
    "1": "ach",
    "2": "kac",
    "3": "iw",
    "4": "da",
}

def main_menu(session, session_path):
    while True:
        banner()

        meta = session.get("meta", {})

        # FIX #3: use _iw_has_data() for iw completion check
        completed = set()
        for key in ("ach", "kac", "da"):
            if session.get(key):
                completed.add(key)
        if _iw_has_data(session.get("iw")):
            completed.add("iw")

        completed_display = [k.upper() for k in ("ach", "kac", "iw", "da") if k in completed]

        print(c(f"  Case: {meta.get('case_id','—')}  |  Analyst: {meta.get('analyst','—')}  |  IOC: {meta.get('ioc','—')}", WHITE, BOLD))
        print(c(f"  TLP: {meta.get('tlp','WHITE')}  |  Completed: {', '.join(completed_display) or 'none'}", GRAY))
        print()

        hr_title("MAIN MENU", color=YELLOW)
        print()
        for key, label in MENU_ITEMS:
            # FIX #1: explicit mapping — never mis-matches "i&w" vs "iw"
            section_key = _MENU_KEY_TO_SESSION.get(key, "")
            done_marker = c(" v", GREEN) if section_key in completed else ""
            print(c(f"  [{key}]", CYAN, BOLD) + f"  {label}{done_marker}")
        print()

        choice = prompt("Select", color=YELLOW)

        if choice == "0":
            session = init_session(session)
        elif choice == "1":
            session = method_ach(session)
        elif choice == "2":
            session = method_kac(session)
        elif choice == "3":
            session = method_iw(session)
        elif choice == "4":
            session = method_da(session)
        elif choice == "5":
            generate_report(session)
            input(c("\n  Press Enter to continue...", GRAY))
        elif choice == "6":
            path = prompt("Save path", session_path or f"session_{meta.get('case_id','cti')}.yaml")
            save_session(session, path)
            session_path = path
            input(c("\n  Press Enter to continue...", GRAY))
        elif choice in ("q", "quit", "exit"):
            if confirm("Save session before quitting?"):
                path = session_path or f"session_{meta.get('case_id','cti')}.yaml"
                save_session(session, path)
            print(c("\n  Goodbye.\n", CYAN))
            sys.exit(0)
        else:
            warn("Invalid choice.")


# ── ENTRY POINT ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CTI Structured Analytic Techniques")
    parser.add_argument("--load",   metavar="FILE",   help="Load existing session YAML")
    parser.add_argument("--method", metavar="METHOD", help="Jump to method: ach|kac|iw|da")
    parser.add_argument("--report", metavar="FILE",   help="Generate report from session file and exit")
    args = parser.parse_args()

    session_path = None

    if args.load:
        try:
            session = load_session(args.load)
            session_path = args.load
            success(f"Session loaded: {args.load}")
        except Exception as e:
            error_msg(f"Could not load session: {e}")
            sys.exit(1)
    else:
        session = new_session()

    if args.report:
        try:
            session = load_session(args.report)
            generate_report(session)
            sys.exit(0)
        except Exception as e:
            error_msg(f"Could not generate report: {e}")
            sys.exit(1)

    if args.method:
        m = args.method.lower()
        if m == "ach":
            session = method_ach(session)
        elif m == "kac":
            session = method_kac(session)
        elif m == "iw":
            session = method_iw(session)
        elif m == "da":
            session = method_da(session)
        else:
            error_msg(f"Unknown method: {m}. Use ach|kac|iw|da")
            sys.exit(1)

    main_menu(session, session_path)


if __name__ == "__main__":
    main()
