# TactOS — Technical Report
**Africa Deep Tech Challenge 2026 | Domain: Corporate / Enterprise**

---

## 1. Problem

Small and medium enterprises (SMEs) across Nigeria and broader sub-Saharan Africa face a growing volume of cybersecurity threats — phishing, brute-force attacks, port scanning, and unauthorized access attempts — with little to no dedicated security operations capacity. Enterprise-grade SOC tools (Splunk, CrowdStrike, SentinelOne) are cloud-dependent, expensive, and assume stable internet connectivity that most African SMEs cannot guarantee.

The result is alert fatigue: security events pile up in IDS/SIEM logs, analysts lack the capacity to triage them rapidly, and critical incidents go unactioned. Load-shedding, intermittent connectivity, and limited IT budgets compound the problem.

**TactOS** is an offline, on-device cybersecurity triage assistant designed specifically for this context. It runs entirely on a standard budget laptop with no cloud dependency, no subscription fee, and no internet requirement during operation. A security analyst pastes an IDS alert or incident description and receives an immediate structured triage brief, recommended actions, and an incident response memo — all generated locally in seconds.

**Target users:** IT officers, security analysts, and system administrators at African SMEs, fintechs, NGOs, and public sector organisations operating under constrained infrastructure conditions.

---

## 2. Design Decisions

### Model Selection: Qwen2.5-1.5B-Instruct
Qwen2.5-1.5B-Instruct was selected after evaluating three candidates:

| Model | Params | Est. RAM | Instruction Quality | Decision |
|---|---|---|---|---|
| TinyLlama-1.1B-Chat | 1.1B | ~1.0 GB | Poor — inconsistent structure | Rejected |
| Qwen2.5-1.5B-Instruct | 1.5B | ~1.8 GB | Strong — follows structured prompts reliably | **Selected** |
| Phi-3-mini-4k-instruct | 3.8B | ~2.5 GB | Excellent — but slower on CPU | Deferred |

Qwen2.5-1.5B offers the best accuracy-to-throughput ratio for CPU-only inference on the standard 8 GB laptop profile. Its instruction-tuning makes it reliable at producing structured triage outputs without fine-tuning.

### Quantization: GGUF Q4_K_M
Q4_K_M was chosen over Q5_K_M and Q8_0 for the following reasons:
- Peak RAM of **1,820 MB** — well within the 8 GB constraint, leaving headroom for the OS and application layer
- Minimal quality degradation vs Q5_K_M for structured text generation tasks
- Faster token generation on CPU due to reduced memory bandwidth pressure

### Runtime: llama.cpp (llama-server mode)
TactOS uses `llama-server` rather than `llama-cli` to avoid interactive mode conflicts and enable clean subprocess communication via HTTP on localhost. This approach is 100% offline — the server binds only to `127.0.0.1` and makes zero external network calls.

### RAG: TF-IDF (Zero Dependencies)
A lightweight TF-IDF retrieval engine was implemented in pure Python (standard library only) to avoid dependency installation failures under constrained network conditions — a real constraint in the Nigerian deployment context. The knowledge base currently includes:

- `mitre_initial_access.txt` — MITRE ATT&CK TA0001 techniques and mitigations
- `incident_response_playbook.txt` — SME-tailored IR playbook with Nigerian regulatory context (ngCERT, NDPC)

Relevant snippets are injected into the prompt context at inference time, grounding responses in domain knowledge beyond the model's training data.

---

## 3. Constraints

### Hardware
- **CPU:** Intel Core i5-10210U (4 cores, 1.6 GHz base)
- **RAM:** 16 GB physical; profiler reports 7.7 GB available (WSL2 environment)
- **GPU:** Intel UHD 620 (integrated) — no CUDA, no Metal, CPU-only inference
- **Storage:** NVMe SSD — fast model load times

### Connectivity
Development was conducted under intermittent WiFi conditions typical of Nigerian urban environments. The zero-dependency RAG design and offline-first architecture were direct responses to this constraint — not academic choices.

### Data Privacy
On-device inference means no analyst query, alert content, or incident data ever leaves the machine. For African fintechs and organisations subject to NDPC data protection requirements, this is a meaningful compliance advantage over cloud-based AI tools.

---

## 4. Benchmarks

All benchmarks measured on participant laptop (Intel i5-10210U, 7.7 GB RAM available, Ubuntu 24.04 via WSL2):

| Metric | Value |
|---|---|
| Prompt processing speed | 31.4 tokens/sec |
| Generation speed | 26.1 tokens/sec |
| Peak RSS memory | 1,820 MB |
| Steady-state RSS | 1,739 MB |
| Peak VMS | 2,294 MB |
| Thermal throttling | None |
| Context length | 2,048 tokens |
| Quantization | GGUF Q4_K_M |

**Projected scores against reference hardware (TPS_REFERENCE = 15.0):**
- Sperf: 100 × (26.1 ÷ 15.0) ≈ **100 (capped)**
- Seff: 100 × ((7.0 − 1.82) ÷ 7.0) ≈ **74.0**
- Pthermal: **0** (no throttling observed)

---

## 5. African Use Case Justification

TactOS directly addresses the cybersecurity capacity gap facing African SMEs:

- **No cloud dependency** — operates during load-shedding and internet outages
- **No subscription cost** — runs on hardware organisations already own
- **Nigerian regulatory awareness** — IR playbook references ngCERT reporting obligations and NDPC data breach notification requirements
- **Language:** English with domain-specific cybersecurity vocabulary appropriate for Nigerian IT professionals

The problem TactOS solves — alert fatigue under resource constraints — is documented in the submitter's undergraduate thesis: *"A Hybrid Intelligence Framework for Reducing Alert Fatigue Using Cross-Domain Intrusion and Malware Detection"* (AFIT, 2026), providing direct academic grounding for the design approach.
