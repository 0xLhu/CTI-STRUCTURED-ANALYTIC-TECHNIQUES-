# CSAT — CTI-Structured Analytic Techniques for CTI

A command-line tool implementing structured analytic techniques for cyber threat intelligence analysis. Designed for analysts who need to document and challenge their reasoning on IOC investigations, attribution assessments, and campaign analysis.

---

## Rationale

CTI analysis fails in predictable ways: confirmation bias anchors conclusions to the first plausible hypothesis, high-confidence language obscures weak evidence chains, and attribution often rests on a single behavioral signal rather than converging independent indicators. These are not skill gaps — they are cognitive patterns that affect experienced analysts as much as junior ones.

Structured analytic techniques address this by forcing explicit separation between evidence collection, hypothesis generation, and scoring. The analyst documents assumptions, scores evidence against competing hypotheses, and builds a counter-case against their own conclusion before finalising. The output is an auditable reasoning chain, not just a verdict.

This tool implements four techniques as a guided CLI workflow. Sessions persist as YAML files and can be shared, version-controlled, or attached to MISP events as analytical notes.

---

## Methods

### ACH — Analysis of Competing Hypotheses

The analyst defines all plausible hypotheses before examining evidence. Each evidence item is scored against each hypothesis on a five-point consistency scale (CC / C / N / I / II). The leading hypothesis is the one with the fewest inconsistencies, not the most confirming evidence — a distinction that matters when evidence is ambiguous or potentially fabricated.

The tool runs a sensitivity analysis automatically: if removing a single evidence item changes the ranking, the conclusion is flagged as fragile. Diagnostic evidence (items that differentiate between hypotheses) is identified separately from evidence that is consistent with all hypotheses and therefore has no analytical value.

### KAC — Key Assumptions Check

Every CTI assessment rests on assumptions that are rarely made explicit: that an IP address is under adversary control rather than legitimately misconfigured, that a campaign observed in historical data is still active, that infrastructure ownership inferred from passive DNS is accurate. The KAC forces the analyst to list these assumptions and rate them on two axes — certainty and impact if wrong. Assumptions with low certainty and high impact are flagged as critical and become the primary targets for additional collection.

### I&W — Indicators and Warnings

For each threat scenario under consideration, the analyst defines observable indicators in advance: what would confirm the scenario is active, what would refute it, and what requires further analysis. Each indicator is mapped to a MITRE ATT&CK technique and a data source. The analyst then marks which indicators have been observed. The absence of expected indicators is treated as evidence, not as absence of evidence.

This technique is particularly useful for building persistent monitoring queries: the confirm indicators for a given actor translate directly into Shodan, Censys, and SIEM searches.

### DA — Devil's Advocacy

The analyst argues as forcefully as possible against their leading hypothesis. Six challenge areas are structured into the workflow: false flag, shared tooling, coincidence, misidentification, confirmation bias, and missing evidence. Each counter-argument is rated for strength. Counter-arguments rated 4/5 or higher are surfaced in the final report as unresolved challenges.

In APT attribution specifically, this technique surfaces the most common analytical error: treating TTP compatibility as attribution. State actors deliberately replicate the TTPs of other groups. A conclusion that does not survive a structured counter-case should not be disseminated.

---

## Usage

```bash
# Start a new session
python CSAT.py

# Resume an existing session
python CSAT.py --load session.yaml

# Jump directly to a method
python CSAT.py --method ach
python CSAT.py --method kac
python CSAT.py --method iw
python CSAT.py --method da

# Generate a Flash Report from a saved session without entering interactive mode
python CSAT.py --report session.yaml
```

Sessions are saved as YAML. The `--report` flag generates a structured Markdown report covering all completed analyses, suitable for attachment to MISP events or inclusion in a wider intelligence product.

---

## Requirements

```
Python 3.8+
pyyaml
```

On Arch Linux:
```bash
sudo pacman -S python-yaml
```

Or in a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
pip install pyyaml
```

---

## Output

Each session produces two files:

- `session_<case_id>.yaml` — full session state including all hypotheses, evidence, matrix scores, assumptions, indicators, and DA challenges. Can be reloaded and continued.
- `flash_report_<case_id>_<date>.md` — structured analytical report covering ACH conclusion with confidence level, critical assumptions from KAC, I&W scenario assessments, and DA counter-arguments. Formatted for TLP-tagged dissemination.

---

## Confidence Levels

| Label   | Range  | Interpretation |
|---------|--------|----------------|
| HIGH    | 75-100 | Strong evidence base. Attribution supportable with documented caveats. |
| MEDIUM  | 50-74  | Reasonable basis. Additional collection required before dissemination. |
| LOW     | 25-49  | Working hypothesis. Not suitable for dissemination. |
| MINIMAL | 0-24   | Insufficient evidence. Analytical speculation only. |

---

## Notes

The tool does not make analytical judgements. It structures the process and surfaces the weak points in an existing analysis. The quality of the output depends entirely on the quality of the evidence and hypotheses the analyst brings to it.

Sessions can be committed to version control alongside investigation notes, providing an auditable record of how a conclusion evolved over time and what evidence was available at each stage.

The YAML session format is intentionally simple and human-readable. Fields can be edited directly if the interactive workflow is not suitable for a given use case.

---

## References

Richards J. Heuer Jr., *Psychology of Intelligence Analysis*, Center for the Study of Intelligence, CIA, 1999. Available in the public domain.

Pherson, R.H. and Heuer, R.J., *Structured Analytic Techniques for Intelligence Analysis*, CQ Press, 2021.

MITRE ATT&CK Framework: https://attack.mitre.org
