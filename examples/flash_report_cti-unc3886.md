# CTI Structured Analytic Report: cti-unc3886

**TLP:CLEAR** · **Date:** 2026-10-16 · **Analyst:** nba

**IOC:** `103.254.253.210`  
**Context:** UNC3886 suspected campaign singapore telecom feb 2026

## Bottom Line

**Assessment:** H1 UNC3886: CHine APT targeting network edge devices telecom sector apac

**Confidence:** MEDIUM (71%). Reasonable basis. Additional collection required before dissemination.

> ⚠ The analyst's leading hypothesis differs from the ACH matrix leader (H3). Justification required.

> ⚠ Fragile conclusion, it depends on E7.

> ⚠ Never tested against evidence (all neutral): H4.

> ⚠ 3 critical assumption(s), see KAC.

> ⚠ 3 strong counter-argument(s) unresolved, see DA.

---

## ACH: Analysis of Competing Hypotheses

**Rationale:** FortiGate EOL cluster with masked headers, non-official certificates and ORB MAC

**Caveats:** pattern is consistent with UNC3886 documented TTPs. E7 cryptominer is assessed

### Hypotheses

| Rank | Hypothesis | Description | Weighted inconsistency ↓ | Net score | Support |
|---|---|---|---|---|---|
| #1 | H3 Criminal | Opportunistic actor cyptominer or botnet | 0.8 | +3 | 60% |
| #2 | H1 UNC3886 | CHine APT targeting network edge devices telecom sector apac | 2.0 | +10 | 81% |
| #3 | H2 APT40 | CHinese apt alternative similar infra profile | 2.0 | +5 | 65% |
| #4 | H4 Uknown | Unattributed insufficiant evidence | 0.0 | +0 | 50% |

### Evidence matrix

| # | Evidence | Rel. | Source | H1 | H2 | H3 | H4 | Diagnostic |
|---|---|---|---|---|---|---|---|---|
| E1 | header server xxxxxx-xxxxxx non-standard fortigate | A | shodan | CC | C | N | N | high |
| E2 | certificat ca support sha1 RSA1024 emis 2014 | A | censys | CC | C | N | N | high |
| E3 | firmware last-modified 2018 EOL | A | Shodan | CC | CC | C | N | high |
| E4 | discordance ASN Zonetel vs starhub | B | VT | C | C | N | N | medium |
| E5 | mac address spoofé sur vps multicanaux signature orb | B | shodan | CC | C | I | N | high |
| E6 | passive dns remotewd.com anomalie comportementale | B | ct | C | N | C | N | medium |
| E7 | Cryptominer minergate confirmer sur domaine associe | A | VT | II | II | CC | N | high · FRAGILE |
| E8 | Custer 3 ip zonetel meme patterns header et cert | B | shodan | CC | C | N | N | high |

Sensitivity: **fragile**: removing E7 changes the leader.

### Indicators to monitor

- **CONFIRM:** as a distinct opportunistic actor on same infrastructure.TINYSHELL process or binary inddentified on fortigate firmware
- **CONFIRM:** addtional fortigate eol with same masked header pattern in APAC
- **CONFIRM:** CVE-2025-21590 exploit attempt on zonetel networ range
- **CONFIRM:** C2 callback to known UNC3386 infrastructure
- **REFUTE:** malware on infrastructure identifed as on chinese apt tooling
- **REFUTE:** zonetel confirms legitimate ownership of anomalous devices
- **REFUTE:** no eol devices found on targeted operator networks

---

## KAC: Key Assumptions Check

| # | Assumption | Certainty | Impact | Risk | What would prove it wrong |
|---|---|---|---|---|---|
| A1 | Zonetel infrastructure is compromised not legitimate | 2/5 | 5/5 | CRITICAL | Zonetel confirms devices are legitimate research nodes |
| A2 | Masked HTTP header is post-compromise not misconfiguration | 3/5 | 4/5 | HIGH | Vendor confirms header valid in some FortiOS versions |
| A3 | UNC3886 campaign still active in 2026 not historical | 2/5 | 5/5 | CRITICAL | No new C2 activity observed after December 2025 |
| A4 | ORB MAC pattern is deliberate evasion not coincidence | 3/5 | 3/5 | MEDIUM | MAC range assigned to legitimate hardware vendor |
| A5 | FortiGate EOL devices under adversary control | 2/5 | 5/5 | CRITICAL | Firmware analysis shows no backdoor only unpatched CVEs |
| A6 | remotewd.com DNS link connects to same campaign | 1/5 | 3/5 | HIGH | NAS device auto-registration explains DNS resolution |

**Critical assumptions (low certainty, high impact), to collect on first:**

- **A1** Zonetel infrastructure is compromised not legitimate. _Challenge:_ Zonetel confirms devices are legitimate research nodes
- **A3** UNC3886 campaign still active in 2026 not historical. _Challenge:_ No new C2 activity observed after December 2025
- **A5** FortiGate EOL devices under adversary control. _Challenge:_ Firmware analysis shows no backdoor only unpatched CVEs

---

## I&W: Indicators & Warnings

### S1: UNC3886 active FortiGate compromise Singapore telecoms

**Status: ACTIVE**, HIGH (100%) · confirm indicators observed 1/1 · refuting observed 0 · expected but absent 0

| Type | Indicator | ATT&CK | Source | Observed | Note |
|---|---|---|---|---|---|
| CONFIRM | FortiGate header Server xxxxxxxx-xxxxx observed on new IPs | T1600 | Shodan | YES | Observed on 103.254.253.210 and 103.254.253.78 via Shodan |
| REFUTE | Firmware updated to supported version on all Zonetel devices |  | Shodan | NO |  |
| MONITOR | Anomalous TACACS+ traffic on telecom management network | T1556 | SIEM | UNKNOWN |  |

### S2: Opportunistic cryptominer on exposed NAS Asia telecoms

**Status: ACTIVE**, HIGH (100%) · confirm indicators observed 1/1 · refuting observed 0 · expected but absent 0

| Type | Indicator | ATT&CK | Source | Observed | Note |
|---|---|---|---|---|---|
| CONFIRM | Non-official TLS certificate CA support on port 8443 | T1553.004 | Censys | YES | SHA1/RSA1024 cert 2014 found via Censys on 103.254.253.210 |
| REFUTE | Zonetel confirms legitimate ownership and no compromise |  | OSINT | NO |  |
| MONITOR | New ASN discordance on Singapore IP ranges | T1583.003 | VirusTotal | YES | Zonetel AS132526 vs StarHub AS4657 confirmed via VirusTotal |

---

## DA: Devil's Advocacy

**Hypothesis challenged:** H1 UNC3886: CHine APT targeting network edge devices telecom sector apac

**Alternative:** False flag or misattribution Chinese criminal actor mimicking APT TTPs

**Verdict:** CONCLUSION DOES NOT HOLD (average strength 3.5/5)

| Area | Strength | Counter-argument |
|---|---|---|
| False Flag | 3/5 | UNC3886 TTPs are publicly documented any actor could replicate them |
| Shared Tooling | 3/5 | FortiGate EOL targeting is common across multiple Chinese actors and criminals |
| Coincidence | 2/5 | Zonetel may operate legitimate EOL devices with non-standard configs |
| Misidentification | 4/5 | Infrastructure could belong to a third party compromised by different actor |
| Confirmation Bias | 4/5 | Mandiant UNC3886 report anchored attribution before investigation started |
| Missing Evidence | 5/5 | No TINYSHELL binary found no direct link to known UNC3886 malware family |

**Final note:** Attribution remains MEDIUM confidence pending malware confirmation no TINYSHELL identified

---

_Generated by CSAT (CTI Structured Analytic Techniques) · TLP:CLEAR_
