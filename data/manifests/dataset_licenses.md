# Dataset licenses

No external datasets imported. Synthetic smoke-test documents are generated locally and marked synthetic. Record origin, license, permitted use, and checksum before importing any dataset.

## Phase 9 local demonstration

`backend/scripts/seed_phase9.py` materializes existing fictional corpus facts
(SOP-P204-001 and PID-U2-017 R3 source inventory) and the Phase 3C synthetic
maintenance/sensor records. P-204 family records are explicitly instantiated as
P-204A. No evaluation-case questions, expected answers, scoring notes, external
dataset, confidential MRPL data or actual engineering drawing is imported.

Permitted use: local software demonstration/testing only, never operational
guidance, model training or evidence of current plant state. The generated P&ID
is a clearly labelled synthetic label excerpt, processed with real local OCR;
it contains no asserted connectivity. No external dataset license is involved.

Current local source hashes (generated PDF bytes may differ on another machine;
the importer records that machine's actual immutable bytes):

| Source | SHA-256 |
| --- | --- |
| SOP-P204-001-demo-v1.pdf | 57bcc48d628000b6321b58d2ec0b20c42e78c3d1675529d97d6c98f0ed21a22c |
| MH-P204-demo-v1.csv | d47314dcc9b59b9e004c6b52e9fb7ee7912334525f081a3c00ee60162b089b8f |
| SENSOR-P204-A-demo-v1.csv | 78a0c950f4e3a5b3d04ee3a88867d41599946dd08c522c08c7c369d13953b66e |
| PID-U2-017-R3-demo-v1.png | 4aea75eaf9cbf8ced43251f4f1f49170e7fe5cc5d55a990c4d2e25b3d08eba3f |

`data/processed/phase9-seed.json` records ingestion IDs, counts, statuses and hashes.
