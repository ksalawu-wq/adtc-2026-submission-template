#!/usr/bin/env python3
"""
TactOS — Offline Cybersecurity Triage Assistant for African SMEs
Zero external dependencies. Runs entirely on-device via llama.cpp server.
"""

import math
import json
import subprocess
import re
import time
import urllib.request
from pathlib import Path

BASE_DIR      = Path(__file__).parent
MODEL_PATH    = BASE_DIR / "model" / "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
LLAMA_SERVER  = Path.home() / "llama.cpp" / "build" / "bin" / "llama-server"
MAX_TOKENS    = 800
CONTEXT_LEN   = 2048
TOP_K_DOCS    = 2
SERVER_PORT   = 8765
SERVER_URL    = f"http://127.0.0.1:{SERVER_PORT}/completion"

_server_proc = None

def start_server():
    global _server_proc
    if _server_proc and _server_proc.poll() is None:
        return
    print("[+] Starting inference server...")
    cmd = [
        str(LLAMA_SERVER), "-m", str(MODEL_PATH),
        "-c", str(CONTEXT_LEN), "--port", str(SERVER_PORT),
        "--log-disable", "-np", "1", "--no-webui", "-t", "4"
    ]
    _server_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Wait for server to be ready
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=1)
            print("[+] Server ready.")
            return
        except:
            time.sleep(1)
    print("[!] Server took longer than expected — continuing anyway.")

def stop_server():
    global _server_proc
    if _server_proc:
        _server_proc.terminate()

def run_llm(prompt: str) -> str:
    payload = json.dumps({
        "prompt": prompt,
        "n_predict": MAX_TOKENS,
        "temperature": 0.7,
        "stop": ["[ANALYST INPUT]", "tactos>", "\n\n\n"]
    }).encode()
    req = urllib.request.Request(
        SERVER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data.get("content", "").strip()
    except Exception as e:
        return f"ERROR: {e}"

# ── TF-IDF RAG ────────────────────────────────────────────────────────────────

def load_knowledge():
    docs = []
    if not KNOWLEDGE_DIR.exists():
        return docs
    for f in sorted(KNOWLEDGE_DIR.glob("*.txt")):
        docs.append((f.name, f.read_text(encoding="utf-8")))
    return docs

def tokenize(text):
    return re.findall(r'[a-z0-9]+', text.lower())

def build_tfidf(docs):
    corpus = [tokenize(text) for _, text in docs]
    N = len(corpus)
    df = {}
    for tokens in corpus:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log((N + 1) / (v + 1)) for t, v in df.items()}
    vecs = []
    for tokens in corpus:
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = len(tokens) or 1
        vec = {t: (c / total) * idf.get(t, 0) for t, c in tf.items()}
        vecs.append(vec)
    return vecs, idf

def cosine(a, b):
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    na  = math.sqrt(sum(v*v for v in a.values()))
    nb  = math.sqrt(sum(v*v for v in b.values()))
    return dot / (na * nb + 1e-9)

def retrieve(query, docs, vecs, idf):
    if not docs:
        return ""
    qtokens = tokenize(query)
    qtf = {}
    for t in qtokens:
        qtf[t] = qtf.get(t, 0) + 1
    total = len(qtokens) or 1
    qvec = {t: (c / total) * idf.get(t, 0) for t, c in qtf.items()}
    scored = [(cosine(qvec, v), docs[i][0], docs[i][1]) for i, v in enumerate(vecs)]
    scored.sort(reverse=True)
    snippets = []
    for score, name, text in scored[:TOP_K_DOCS]:
        if score > 0.01:
            snippet = text[:300].replace('\n', ' ').strip()
            snippets.append(f"[{name}]: {snippet}")
    return "\n".join(snippets)

# ── Prompt ────────────────────────────────────────────────────────────────────

def build_prompt(user_input, context):
    ctx_block = f"\n\nRELEVANT KNOWLEDGE:\n{context}" if context.strip() else ""
    is_memo = user_input.lower().startswith("memo")
    if is_memo:
        template = """You are a cybersecurity analyst at an African SME. Write a short incident response memo for the following incident. Be direct and specific. Use this exact format:

INCIDENT RESPONSE MEMO
Severity: High
Summary: Write one sentence here.
Affected Systems: List them here.
Immediate Actions:
1. First action.
2. Second action.
3. Third action.
Short-term Actions:
1. First action.
2. Second action.
Regulatory Note: Report to ngCERT at cert@certncc.gov.ng if data was compromised.
"""
    else:
        template = """You are a cybersecurity analyst triaging a security alert for an African SME.
Analyse the alert and respond using ONLY this structure — no extra commentary:

TRIAGE REPORT
Severity:
Threat Type:
MITRE Technique:

Summary:
[Two sentences describing what happened and why it matters]

Immediate Actions:
1. [Action]
2. [Action]
3. [Action]

Risk if Unaddressed:
[One sentence on the consequence of ignoring this alert]
"""
    return f"{template}\n\nALERT/INCIDENT:\n{user_input}{ctx_block}\n\nRESPONSE:\n"

# ── CLI ───────────────────────────────────────────────────────────────────────

BANNER = """
╔════════════════════════════════════════════╗
║  TactOS — Offline Cybersecurity Assistant  ║
║  Powered by Qwen2.5-1.5B · llama.cpp      ║
║  Type 'exit' to quit · 'help' for commands ║
╚════════════════════════════════════════════╝
"""

def main():
    print(BANNER, flush=True)
    docs = load_knowledge()
    if docs:
        vecs, idf = build_tfidf(docs)
        print(f"[+] Knowledge base loaded: {len(docs)} document(s)")
    else:
        vecs, idf = [], {}
        print("[!] No knowledge documents found — running without RAG")

    start_server()

    while True:
        try:
            user_input = input("\ntactos> ").strip()
        except (EOFError, KeyboardInterrupt):
            stop_server()
            print("\n[+] Exiting TactOS.")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            stop_server()
            print("[+] Exiting TactOS.")
            break
        if user_input.lower() == "help":
            print("\nCommands: triage <alert> | memo <incident> | advise <question> | clear | exit\n")
            continue
        if user_input.lower() == "clear":
            print("\033[2J\033[H", end="")
            continue

        query = user_input
        for prefix in ("triage ", "memo ", "advise "):
            if user_input.lower().startswith(prefix):
                query = user_input[len(prefix):]
                break

        context = retrieve(query, docs, vecs, idf) if docs else ""
        prompt = build_prompt(user_input, context)
        print("\n[~] Analysing...\n")
        raw = run_llm(prompt)
        # Extract clean memo/report block if present
        for marker in ["INCIDENT RESPONSE MEMO", "TRIAGE REPORT"]:
            if marker in raw:
                raw = raw[raw.index(marker):]
                break
        # Cut off at trailing noise
        for cutoff in ["ACTION:", "Response:", "[Attach", "John Doe", "[Add your",
                       "ALERT/INCIDENT:", "RELEVANT KNOWLEDGE:", "**Note:",
                       "We are working", "The company has taken",
                       "[incident_response", "[mitre_initial",
                       "Incident response memo", "**Incident Response Memo",
                       "The unauthorized login", "The incident involves",
                       "The incident is classified", "The incident is considered",
                       "Based on the above", "[mitre_initial",
                       "**The alert", "**The incident"]:
            if cutoff in raw:
                raw = raw[:raw.index(cutoff)].strip()
                break
        # Cut triage repeats
        if raw.count("Immediate Actions") > 1:
            idx = raw.index("Immediate Actions")
            idx2 = raw.index("Immediate Actions", idx + 1)
            raw = raw[:idx2].strip()
        # Cut triage repeats — find second occurrence of "Immediate Actions"
        if "TRIAGE" not in raw and raw.count("Immediate Actions") > 1:
            idx = raw.index("Immediate Actions")
            idx2 = raw.index("Immediate Actions", idx + 1)
            raw = raw[:idx2].strip()
        print(raw)

if __name__ == "__main__":
    main()
