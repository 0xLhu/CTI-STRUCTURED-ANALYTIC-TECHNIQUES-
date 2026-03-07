# Roadmap

This roadmap is derived from a real investigation conducted during the UNC3886 exercise (March 2026) using free tools only — Shodan, Censys, VirusTotal. Every item listed here addresses a concrete friction point encountered during that exercise, not a hypothetical feature request.

---

## Current State

`CSAT.py` implements four structured analytic techniques as an interactive CLI:

- ACH — Analysis of Competing Hypotheses
- KAC — Key Assumptions Check
- I&W — Indicators and Warnings
- DA — Devil's Advocacy

Sessions persist as YAML files. Output is a structured Markdown Flash Report.

---

## What Was Missing During the Exercise

During the UNC3886 investigation, several friction points slowed the analytical workflow:

- Evidence items (headers, certificates, firmware versions) had to be typed manually into the ACH matrix, even though they already existed as Shodan/Censys/VT output
- Findings produced in CSAT had to be imported manually into MISP with no link between the YAML session and the MISP event
- I&W confirm indicators were defined but not translated into executable hunting queries
- No link between sessions — starting a new investigation on the same actor six months later requires rebuilding context from scratch
- The Flash Report is Markdown only, with no structured export format for sharing or ticketing systems

---

## Planned Improvements

Items are ordered by analytical value, not implementation effort.

---

### Priority 1 — Reduce Input Friction

#### Evidence import from CSV / JSON

Allow loading evidence items from a structured file instead of manual entry. Analysts prepare their data outside CSAT (Shodan export, VT results, IOC list) and import it at the start of an ACH session.

```
evidence.csv
  description, reliability, source
  "Header Server: xxxxxxxx-xxxxx masked", A, Shodan
  "Cert CA=support SHA1/RSA1024 2014", A, Censys
  "Firmware Last-Modified 2018 EOL", A, Shodan
```

```bash
python CSAT.py --method ach --evidence evidence.csv
```

---

#### Session index and search

Maintain a local index file (`~/.csat/index.yaml`) referencing all past sessions with their key metadata: case ID, IOC, actor hypotheses, conclusion, confidence level, date.

```bash
python CSAT.py --search UNC3886
# cti-unc3386-2026.yaml  2026-03-07  IOC: 103.254.253.210  MEDIUM
# cti-unc3886-2025.yaml  2025-11-14  IOC: 45.77.23.11       LOW

python CSAT.py --search 103.254.253.210
```

Gives the tool cumulative memory without requiring an external backend.

---

### Priority 2 — MISP Integration

#### Export session as MISP event

At the end of a completed session, generate a MISP-compatible JSON file importable via the API or web interface.

The file would contain:
- The primary IOC as an attribute with type and TLP
- Pivot IOCs as related attributes
- ACH conclusion as an analytical note
- I&W confirm indicators as monitoring attributes
- Critical KAC assumptions as tags or comments

```bash
python CSAT.py --export-misp session.yaml > misp_event.json
```

---

#### MISP lookup before starting a session

Before opening a new session, query the local MISP instance to check whether the IOC is already known, in which event, and at what confidence level. Enforces the "MISP first" methodology at the tooling level rather than relying on procedural discipline.

```bash
python CSAT.py --misp-check 103.254.253.210
```

Requires a MISP API key configured in a local config file.

---

### Priority 3 — Generate Hunting Queries from I&W

#### Export pivot queries from I&W indicators

I&W confirm indicators are technical observables mapped to MITRE ATT&CK techniques. They can be automatically translated into Shodan, Censys, and VirusTotal queries using a technique-to-query mapping.

Base mapping:

| MITRE Technique | Query Target |
|---|---|
| T1600 Weaken Encryption | Shodan: ssl.cert + port |
| T1553.004 Code Signing | Censys: cert.issuer.common_name |
| T1190 Exploit Public App | Shodan: product + version |
| T1071.004 DNS C2 | VirusTotal: passive DNS |
| T1496 Resource Hijacking | VirusTotal: hash + tag:miner |

Output: `hunting_queries_<case_id>.txt` with all queries ready to copy, annotated by scenario and priority.

```bash
python CSAT.py --export-queries session.yaml
```

---

### Priority 4 — Session Memory and Continuity

#### Link between sessions

When opening a new session, allow referencing an existing session as context. Hypotheses and assumptions from the previous session are pre-loaded as a starting point.

Useful for: resuming an investigation months later, investigating a new IOC from the same cluster, onboarding an analyst on an active case.

```bash
python CSAT.py --context previous_session.yaml
```

---

### Priority 5 — Separate Tools

These items belong in standalone scripts rather than as CSAT extensions.

---

#### `fetch.py` — IOC Context Fetcher

A standalone script that queries Shodan, Censys, and VirusTotal for a given IOC and produces a structured JSON file usable as CSAT input.

```bash
python fetch.py 103.254.253.210 --out evidence.json
```

Output fields:
- Shodan: banner, HTTP headers, open ports, certificate, firmware version
- Censys: certificate details, services, ASN
- VirusTotal: detections, passive DNS, community score, related samples

Reduces the collection phase of an investigation from hours to minutes. The analytical phase (CSAT) remains fully manual.

---

#### `diff.py` — Session Diff

Compare two sessions on the same actor or IOC. Identify what changed: new hypotheses added, evidence updated, confidence revised, assumptions invalidated.

Useful for periodic re-assessments and for documenting how a case evolved over time.

```bash
python diff.py session_2025.yaml session_2026.yaml
```

---

#### TLP-aware Report Renderer

Take a completed session and produce filtered report versions by TLP level:
- TLP:RED — full report for internal team
- TLP:AMBER — without sensitive source references, for partners
- TLP:GREEN — without specific IOCs, for broad dissemination

```bash
python CSAT.py --report session.yaml --tlp AMBER
```

---

## Suggested Work Order

```
Sprint 1  (1-2 days)
  [ ] Evidence import from CSV/JSON
  [ ] Session index and search

Sprint 2  (2-3 days)
  [ ] MISP event export
  [ ] MISP lookup before session

Sprint 3  (3-5 days)
  [ ] fetch.py — IOC Context Fetcher
  [ ] Hunting query export from I&W indicators

Sprint 4  (1-2 days)
  [ ] Session diff
  [ ] TLP-aware report renderer
  [ ] Session context linking
```

---

## Out of Scope

**Graphical interface** — the value of CSAT is in the rigour of the process, not the ergonomics. A GUI risks creating the impression that filling in fields is sufficient. The CLI enforces intentional input.

**AI-assisted hypothesis generation** — the analytical value comes from the analyst formulating hypotheses and scoring evidence themselves. Delegating this step removes the primary benefit of the method.

**Direct SIEM/EDR integration** — out of scope for a free OSINT tool. The SIGMA hints produced by CSAT are the intended interface with detection infrastructure.

---

## Contributing

If you work in CTI and have encountered friction points not listed here, open an issue describing the specific investigation step that was slowed down and what data was available at that point. Feature requests framed around concrete analytical problems are prioritised over general improvements.

---

*Roadmap derived from investigation CTI-UNC3386-2026 — TLP:WHITE*
