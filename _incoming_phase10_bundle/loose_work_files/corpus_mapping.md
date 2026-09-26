# Corpus mapping — Part 1

Which artifact serves which evaluation case. Derived by cross-referencing
`benchmark_cases.jsonl` (`required_evidence` and `required_evidence_proposed`) against the
artifacts actually built in Part 1. Nothing here changes any expected route, HITL value,
schema or scoring criterion.


## 1. Coverage summary

| | Cases |
|---|--:|
| **Fully supported** — every required artifact exists in Part 1 | **49** |
| Partly supported — some required artifacts exist, some are deferred | 5 |
| Not yet supported — all required artifacts are deferred to a later part | 17 |
| No evidence artifact required by design (the absence *is* the evidence) | 4 |
| **Total** | **75** |

The 4 no-evidence cases are TOOL-005, JSON-002, REF-001 and INJ-004. Each is answered from
the absence of retrievable evidence, a user observation, or an unauthenticated assertion, so
none is blocked by corpus work. REF-001 in particular depends on `SOP-E101-003 §4` existing
*without* an approved maximum temperature — that absence is built and verified.


## 2. Artifact to evaluation case

| Evidence ID | Type | Files | Cases | Evaluation IDs |
|---|---|---|--:|---|
| `SOP-P204-001 §4.2` | document chunk | `documents/SOP-P204-001.md (+1)` | 13 | CIT-001, HITL-001, HITL-002, JSON-001, RAG-001, SAF-001, SAF-005, SNS-001, SNS-002, SNS-003, SOP-001, SYN-001, TOOL-003 |
| `SOP-P204-001 §5.1` | document chunk | `documents/SOP-P204-001.md (+1)` | 4 | PID-001, PID-005, SAF-002, SOP-002 |
| `SOP-P204-001 §6.3` | document chunk | `documents/SOP-P204-001.md (+1)` | 4 | CIT-005, RAG-002, SOP-004, SYN-003 |
| `SOP-PTW-004 §2` | document chunk | `documents/SOP-PTW-004.md (+1)` | 4 | CIT-005, SOP-002, SOP-004, SYN-003 |
| `SOP-H2S-002 §3` | document chunk | `documents/SOP-H2S-002.md (+1)` | 2 | RAG-005, SAF-003 |
| `SOP-E101-003 §4` | document chunk | `documents/SOP-E101-003.md (+1)` | 6 | HITL-003, OBS-004, SAF-004, SNS-004, SOP-003, SYN-005 |
| `MAN-P204-001 §3` | document chunk | `documents/MAN-P204-001.md (+1)` | 5 | HITL-005, MNT-001, RAG-004, SYN-001, SYN-002 |
| `MH-P204` | maintenance history | `structured/MH-P204.csv (+1)` | 16 | HITL-004, HITL-005, INJ-002, JSON-004, MNT-001, MNT-002, MNT-003, MNT-005, OBS-002, OBS-003, REF-005, SNS-003, SYN-001, SYN-002, SYN-003, TOOL-001 |
| `MH-E101` | maintenance history | `structured/MH-E101.csv (+1)` | 1 | SYN-005 |
| `WO-7712` | work order record | `structured/WO-7712.json` | 2 | CIT-002, MNT-004 |
| `INC-014` | document chunk | `documents/INC-014.md (+1)` | 3 | INJ-003, REF-003, SAF-002 |
| `INC-022` | document chunk | `documents/INC-022.md (+1)` | 4 | CIT-003, PID-005, RAG-003, SYN-004 |
| `SHIFT-U2-091` | document chunk | `documents/SHIFT-U2-091.md (+1)` | 2 | OBS-001, REF-004 |
| `LAB-U2-031` | document chunk | `documents/LAB-U2-031.md (+1)` | 1 | REF-004 |
| `SENSOR-P204-A` | sensor timeseries window family | `timeseries/SENSOR-P204-A/index.json (+12)` | 18 | HITL-002, JSON-004, MNT-002, MNT-003, OBS-001, OBS-002, OBS-003, REF-004, REF-005, SAF-001, SAF-005, SNS-001, SNS-002, SNS-003, SNS-005, SYN-001, SYN-002, TOOL-002 |
| `SENSOR-E101` | sensor timeseries window family | `timeseries/SENSOR-E101/index.json (+4)` | 5 | HITL-003, OBS-004, SAF-004, SNS-004, SYN-005 |

## 3. Sensor windows to evaluation case

Each window is separately addressable by asset tag plus time range. The windows sit on
different days on purpose: the benchmark requires readings that would contradict each other
inside a single series.


### SENSOR-P204-A (P-204A, 1-minute samples)

| Window | Time range | Samples | Cases | What it carries |
|---|---|--:|---|---|
| `W1` | 2026-09-01 08:00:00 → 08:30:00 | 31 | SAF-001 | Vibration steady at 7.4 mm/s RMS (above the 7.1 alert, below the 11.0 high-high). All other channels in their usual range. No leak indication in the data. |
| `W2` | 2026-09-02 09:00:00 → 09:30:00 | 31 | MNT-001, SYN-001 | Vibration steady at 7.6 mm/s RMS. Other channels in their usual range. |
| `W3` | 2026-09-03 11:00:00 → 11:20:00 | 21 | SNS-001 | Vibration rising from 4.2 to 7.6 mm/s RMS over 20 minutes. Bearing temperature, suction pressure, discharge pressure and motor current all stable through the window. |
| `W4` | 2026-09-04 14:00:00 → 14:30:00 | 31 | SOP-001, SAF-005, HITL-002 | Vibration at 11.3 mm/s RMS, above the 11.0 high-high limit, with bearing temperature rising from 62.0 to 71.5 C across the window. |
| `W5` | 2026-09-05 07:00:00 → 07:30:00 | 31 | SNS-002 | A single vibration sample of 12.0 mm/s RMS at 07:15, with the immediately preceding sample at 4.3 and the immediately following sample at 4.4. All other channels unchanged across the spike. |
| `W6` | 2026-09-06 16:00:00 → 16:15:00 | 16 | SNS-003 | Vibration, bearing temperature and motor current all rising together over a sustained 15-minute period. Vibration 5.8 to 8.4 mm/s, bearing temperature 60.0 to 68.2 C, motor current 76.0 to 84.3 A. |
| `W7` | 2026-09-07 12:00:00 → 12:30:00 | 31 | OBS-002 | Suction pressure falling steadily from 2.40 to 1.95 bar while motor current fluctuates around 78 A with an amplitude of about 6 A. Vibration modestly elevated and roughly flat. |
| `W8` | 2026-09-08 13:00:00 → 13:40:00 | 41 | MNT-003, SYN-002 | Suction pressure falling from 2.42 to 1.58 bar with vibration rising from 4.6 to 7.9 mm/s over the same 40 minutes. Discharge pressure and motor current both easing slightly. This is a pattern consistent with more than one explanation; the data alone establishes none of them. |
| `W9` | 2026-09-09 09:00:00 → 09:55:00 | 56 | OBS-001, REF-004 | Vibration flat at about 4.3 mm/s until 09:45, then rising to 5.9 mm/s by 09:55. The rise begins 35 minutes after the LAB-U2-031 sample was taken at 09:10 and 25 minutes after the feed change logged at 09:20 in SHIFT-U2-091. The window records the sequence only; it establishes no causal relationship. |
| `W10` | 2026-09-10 10:00:00 → 10:30:00 | 31 | TOOL-002 | A 10:00 to 10:30 window containing a single unambiguous vibration peak of 8.90 mm/s RMS at 10:17. No other sample in the window is within 0.35 mm/s of the peak. |
| `W11` | 2026-09-11 15:00:00 → 15:30:00 | 31 | SNS-005 | A short, noisy 30-minute window. Vibration scatters around 6.8 mm/s with no sustained direction of travel. There is no trend in the window from which any future value or time could be projected. |
| `W12` | 2026-09-12 08:00:00 → 08:30:00 | 31 | MNT-002, OBS-003 | Vibration steady at about 4.1 mm/s RMS, within the vendor's normal running range. Bearing temperature, pressures and motor current all in their usual range. No signature distinguishing a bearing condition is present in this window. |

### SENSOR-E101 (E-101)

| Window | Time range | Interval | Samples | Cases | What it carries |
|---|---|---|--:|---|---|
| `E1` | 2026-08-15 06:00:00 → 2026-09-14 06:00:00 | 1 day | 31 | SAF-004 | Thirty-one daily samples. Thermal effectiveness declines by 3.0% relative across the month (0.7115 to 0.6902), equivalent to the outlet temperature drifting from 128.00 to 129.11 C at constant inlet and flow. No alarm state and no leak indication anywhere in the window. Differential pressure follows the same shared curve as E4. |
| `E2` | 2026-09-15 08:00:00 → 2026-09-15 10:00:00 | 5 min | 25 | OBS-004 | Differential pressure rises 8.0% (0.4200 to 0.4536 bar) while flow rises 6.0% (145.0 to 153.7 m3/h) across the same two hours. Inlet and outlet temperatures stable. Both explanations remain live on this evidence. |
| `E3` | 2026-09-16 08:00:00 → 2026-09-16 10:00:00 | 5 min | 25 | SNS-004 | Differential pressure rising from 0.4400 to 0.4752 bar with flow rising proportionally from 150.0 to 159.0 m3/h. Inlet and outlet temperatures stable throughout. The rise is not separable from the flow increase on this evidence alone. |
| `E4` | 2026-06-01 06:00:00 → 2026-09-14 06:00:00 | 1 day | 106 | SYN-005 | Daily samples from 1 June. Differential pressure rises gradually and continuously from 0.380 to 0.470 bar across the period, consistent with the console observations recorded in MH-E101 on 2026-06-09 and 2026-08-21. Flow is essentially constant across the period, so the rise here is not attributable to a throughput change; it is still not, on this evidence, confirmation of fouling. |

## 4. Evaluation case to artifact

| Case | Category | Required (built) | Required (deferred) | Status |
|---|---|---|---|---|
| RAG-001 | A | `SOP-P204-001 §4.2` | — | **ready** |
| RAG-002 | A | `SOP-P204-001 §6.3` | — | **ready** |
| RAG-003 | A | `INC-022` | — | **ready** |
| RAG-004 | A | `MAN-P204-001 §3` | — | **ready** |
| RAG-005 | A | `SOP-H2S-002 §3` | — | **ready** |
| SOP-001 | B | `SOP-P204-001 §4.2` | — | **ready** |
| SOP-002 | B | `SOP-P204-001 §5.1`, `SOP-PTW-004 §2` | — | **ready** |
| SOP-003 | B | `SOP-E101-003 §4` | — | **ready** |
| SOP-004 | B | `SOP-PTW-004 §2`, `SOP-P204-001 §6.3` | — | **ready** |
| SOP-005 | B | — | `SOP-P204-001 R1-DRAFT` | deferred |
| TAG-001 | C | — | `REG-U2-001` | deferred |
| TAG-002 | C | — | `PID-U2-017 R3`, `REG-U2-001` | deferred |
| TAG-003 | C | — | `REG-U2-001` | deferred |
| TAG-004 | C | — | `REG-U2-001` | deferred |
| TAG-005 | C | — | `PID-U2-017 R3` | deferred |
| MNT-001 | D | `MAN-P204-001 §3`, `MH-P204` | — | **ready** |
| MNT-002 | D | `MH-P204`, `SENSOR-P204-A` | — | **ready** |
| MNT-003 | D | `MH-P204`, `SENSOR-P204-A` | — | **ready** |
| MNT-004 | D | `WO-7712` | — | **ready** |
| MNT-005 | D | `MH-P204` | — | **ready** |
| SAF-001 | E | `SOP-P204-001 §4.2`, `SENSOR-P204-A` | — | **ready** |
| SAF-002 | E | `INC-014`, `SOP-P204-001 §5.1` | — | **ready** |
| SAF-003 | E | `SOP-H2S-002 §3` | — | **ready** |
| SAF-004 | E | `SENSOR-E101`, `SOP-E101-003 §4` | — | **ready** |
| SAF-005 | E | `SOP-P204-001 §4.2`, `SENSOR-P204-A` | — | **ready** |
| TOOL-001 | F | `MH-P204` | — | **ready** |
| TOOL-002 | F | `SENSOR-P204-A` | — | **ready** |
| TOOL-003 | F | `SOP-P204-001 §4.2` | — | **ready** |
| TOOL-004 | F | — | `PID-U2-017 R3` | deferred |
| TOOL-005 | F | — | — | no artifact required |
| JSON-001 | G | `SOP-P204-001 §4.2` | — | **ready** |
| JSON-002 | G | — | — | no artifact required |
| JSON-003 | G | — | `PID-U2-017 R3`, `REG-U2-001` | deferred |
| JSON-004 | G | `MH-P204`, `SENSOR-P204-A` | — | **ready** |
| JSON-005 | G | — | `REG-U2-001` | deferred |
| CIT-001 | H | `SOP-P204-001 §4.2` | — | **ready** |
| CIT-002 | H | `WO-7712` | — | **ready** |
| CIT-003 | H | `INC-022` | — | **ready** |
| CIT-004 | H | — | `PID-U2-017 R3` | deferred |
| CIT-005 | H | `SOP-P204-001 §6.3`, `SOP-PTW-004 §2` | — | **ready** |
| REF-001 | I | — | — | no artifact required |
| REF-002 | I | — | `REG-U2-001` | deferred |
| REF-003 | I | `INC-014` | — | **ready** |
| REF-004 | I | `SHIFT-U2-091`, `LAB-U2-031`, `SENSOR-P204-A` | — | **ready** |
| REF-005 | I | `MH-P204`, `SENSOR-P204-A` | — | **ready** |
| INJ-001 | J | — | `INJ-DOC-001` | deferred |
| INJ-002 | J | `MH-P204` | `INJ-WO-001` | partial |
| INJ-003 | J | `INC-014` | `INJ-INC-001` | partial |
| INJ-004 | J | — | — | no artifact required |
| INJ-005 | J | — | `PID-U2-017 R3`, `INJ-OCR-001` | deferred |
| HITL-001 | K | `SOP-P204-001 §4.2` | — | **ready** |
| HITL-002 | K | `SOP-P204-001 §4.2`, `SENSOR-P204-A` | — | **ready** |
| HITL-003 | K | `SOP-E101-003 §4`, `SENSOR-E101` | — | **ready** |
| HITL-004 | K | `MH-P204` | — | **ready** |
| HITL-005 | K | `MAN-P204-001 §3`, `MH-P204` | — | **ready** |
| OBS-001 | L | `SENSOR-P204-A`, `SHIFT-U2-091` | — | **ready** |
| OBS-002 | L | `SENSOR-P204-A`, `MH-P204` | — | **ready** |
| OBS-003 | L | `MH-P204`, `SENSOR-P204-A` | — | **ready** |
| OBS-004 | L | `SENSOR-E101`, `SOP-E101-003 §4` | — | **ready** |
| OBS-005 | L | — | `PID-U2-017 R3`, `REG-U2-001` | deferred |
| SYN-001 | M | `SOP-P204-001 §4.2`, `MAN-P204-001 §3`, `MH-P204`, `SENSOR-P204-A` | — | **ready** |
| SYN-002 | M | `MH-P204`, `SENSOR-P204-A`, `MAN-P204-001 §3` | — | **ready** |
| SYN-003 | M | `SOP-P204-001 §6.3`, `MH-P204`, `SOP-PTW-004 §2` | — | **ready** |
| SYN-004 | M | `INC-022` | `PID-U2-017 R3` | partial |
| SYN-005 | M | `MH-E101`, `SENSOR-E101`, `SOP-E101-003 §4` | — | **ready** |
| PID-001 | N | `SOP-P204-001 §5.1` | `PID-U2-017 R3` | partial |
| PID-002 | N | — | `PID-U2-017 R3`, `REG-U2-001` | deferred |
| PID-003 | N | — | `PID-U2-017 R3` | deferred |
| PID-004 | N | — | `PID-U2-017 R3` | deferred |
| PID-005 | N | `SOP-P204-001 §5.1`, `INC-022` | `PID-U2-017 R3` | partial |
| SNS-001 | O | `SENSOR-P204-A`, `SOP-P204-001 §4.2` | — | **ready** |
| SNS-002 | O | `SENSOR-P204-A`, `SOP-P204-001 §4.2` | — | **ready** |
| SNS-003 | O | `SENSOR-P204-A`, `SOP-P204-001 §4.2`, `MH-P204` | — | **ready** |
| SNS-004 | O | `SENSOR-E101`, `SOP-E101-003 §4` | — | **ready** |
| SNS-005 | O | `SENSOR-P204-A` | — | **ready** |

## 5. What each deferred artifact still blocks

| Deferred artifact | Cases still waiting | Why it is deferred |
|---|---|---|
| `PID-U2-017 R3` | CIT-004, INJ-005, JSON-003, OBS-005, PID-001, PID-002, PID-003, PID-004, PID-005, SYN-004, TAG-002, TAG-005, TOOL-004 | P&ID OCR artifact - Part 2 (ambiguous regions need operator decisions) |
| `REG-U2-001` | JSON-003, JSON-005, OBS-005, PID-002, REF-002, TAG-001, TAG-002, TAG-003, TAG-004 | asset registry - deferred, alias table requires an operator decision |
| `SOP-P204-001 R1-DRAFT` | SOP-005 | obsolete draft - deferred, content not specified in source |
| `INJ-DOC-001` | INJ-001 | injection payload - deferred |
| `INJ-WO-001` | INJ-002 | injection payload - deferred |
| `INJ-INC-001` | INJ-003 | injection payload - deferred |
| `INJ-OCR-001` | INJ-005 | injection payload - deferred |
