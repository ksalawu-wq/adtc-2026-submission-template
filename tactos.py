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
MAX_TOKENS    = 300
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
        "--log-disable", "-np", "1", "--no-webui"
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
        "temperature": 0.3,
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

SYSTEM_PROMPT = """You are TactOS, an offline cybersecurity triage assistant for African SMEs.
You help analysts summarize alerts, draft incident reports, and recommend immediate actions.
Be concise and practical. Assume limited internet or cloud access."""

def build_prompt(user_input, context):
    ctx_block = f"\n\n[KNOWLEDGE CONTEXT]\n{context}" if context.strip() else ""
    return f"{SYSTEM_PROMPT}{ctx_block}\n\n[ANALYST INPUT]\n{user_input}\n\n[TACTOS RESPONSE]\n"

# ── CLI ───────────────────────────────────────────────────────────────────────

BANNER = """
╔════════════════════════════════════════════╗
║  TactOS — Offline Cybersecurity Assistant  ║
║  Powered by Qwen2.5-1.5B · llama.cpp      ║
║  Type 'exit' to quit · 'help' for commands ║
╚════════════════════════════════════════════╝
"""

def main():
    print(BANNER)
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
            print("\nCommands: triage <alert> | memo <incident> | advise <question> | exit\n")
            continue

        query = user_input
        for prefix in ("triage ", "memo ", "advise "):
            if user_input.lower().startswith(prefix):
                query = user_input[len(prefix):]
                break

        context = retrieve(query, docs, vecs, idf) if docs else ""
        prompt = build_prompt(user_input, context)
        print("\n[~] Analysing...\n")
        print(run_llm(prompt))

if __name__ == "__main__":
    main()
