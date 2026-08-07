import logging
import os
import time
from collections import defaultdict, deque

import json
import urllib.error
import urllib.request

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("spark")

app = Flask(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Cheapest first; the loop falls back if a name is rejected.
MODELS = [
    os.getenv("SPARK_MODEL", "claude-haiku-4-5"),
    "claude-sonnet-4-5",
]


def call_claude(model: str, system: str, messages: list) -> str:
    payload = json.dumps({
        "model": model,
        "max_tokens": 1500,
        "system": system,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "content-type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    parts = data.get("content") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()

BASE_SYSTEM = (
    "You are Spark, an elite executive AI consultant.\n"
    "Operating principles:\n"
    "1. Be professional, precise and direct. No filler, no flattery.\n"
    "2. Structure answers with Markdown - short headers, bold key points, tables "
    "for comparisons. Lead with the answer, then the reasoning.\n"
    "3. If a request is ambiguous or missing key facts (budget, market, timeframe, "
    "goal), ask at most TWO sharp clarifying questions BEFORE giving a full answer.\n"
    "4. Quantify whenever possible; state assumptions explicitly.\n"
    "5. You advise - you do not have access to live data, the internet, or the "
    "user's files, and you say so when it matters. Never invent statistics.\n"
    "6. For legal, tax or regulated-industry questions, give the general picture "
    "and recommend a qualified professional for the final call."
)

MAX_MESSAGE_CHARS = 4000
MAX_HISTORY_MESSAGES = 20  # most recent turns sent back to the model

# --- Simple per-IP rate limit: 20 requests per minute (in-memory) ---
_hits: dict = defaultdict(deque)
RATE_LIMIT = 20
RATE_WINDOW = 60.0


def rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


@app.route("/")
def index():
    return HTML


@app.route("/health")
def health():
    return jsonify({"status": "ok", "key_configured": bool(ANTHROPIC_API_KEY)})


@app.route("/chat", methods=["POST"])
def chat():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    if rate_limited(ip):
        return jsonify({"error": "Rate limit reached - wait a minute and try again."}), 429

    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"error": "Empty message."}), 400
    if len(msg) > MAX_MESSAGE_CHARS:
        return jsonify({"error": f"Message too long (max {MAX_MESSAGE_CHARS} characters)."}), 400

    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Server is missing ANTHROPIC_API_KEY - set it in Render > Environment."}), 500

    # ---- Conversation memory ----
    # The browser sends prior turns as [{role: "user"|"model", text: "..."}].
    # We rebuild them into the format Claude expects, capped to the recent past.
    messages = []
    history = data.get("history") or []
    if isinstance(history, list):
        for turn in history[-MAX_HISTORY_MESSAGES:]:
            role = turn.get("role")
            text = (turn.get("text") or "").strip()
            if role in ("user", "model") and text:
                messages.append({
                    "role": "user" if role == "user" else "assistant",
                    "content": text[:MAX_MESSAGE_CHARS],
                })
    messages.append({"role": "user", "content": msg})

    last_error = None
    for name in MODELS:
        try:
            reply = call_claude(name, BASE_SYSTEM, messages)
            if not reply:
                raise ValueError("empty response")
            log.info("chat ok model=%s ip=%s turns=%d", name, ip, len(messages))
            return jsonify({"reply": reply, "model": name})
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            last_error = f"{e.code} {body}"
            log.warning("model %s failed: %s", name, last_error)
            continue
        except Exception as e:  # noqa: BLE001 - we log and fall through to the next model
            last_error = e
            log.warning("model %s failed: %s", name, e)
            continue

    log.error("all models failed for ip=%s: %s", ip, last_error)
    return jsonify({"error": "Spark is temporarily unavailable. Please retry shortly."}), 502


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Spark AI - Executive Consulting</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
    <style>
        :root {
            --bg: #0f172a; --sidebar: #1e293b; --brand: #38bdf8;
            --text: #f1f5f9; --muted: #94a3b8; --border: #334155;
            --user-bubble: #1d2b45;
        }
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; display: flex; height: 100dvh; background: var(--bg); color: var(--text); }
        aside { width: 260px; background: var(--sidebar); border-right: 1px solid var(--border); padding: 25px 20px; display: flex; flex-direction: column; gap: 14px; }
        .logo { font-size: 20px; font-weight: 800; color: var(--brand); letter-spacing: .04em; }
        .tagline { font-size: 12px; color: var(--muted); margin-top: -8px; line-height: 1.5; }
        .side-btn { background: var(--brand); color: #0f172a; border: none; padding: 12px; border-radius: 8px; cursor: pointer; font-weight: 700; font-size: 14px; }
        .side-btn.ghost { background: transparent; border: 1px solid var(--border); color: var(--muted); }
        .status { margin-top: auto; font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 7px; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: #34d399; }
        .disclaimer { font-size: 11px; color: #64748b; line-height: 1.5; }
        main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
        #chat { flex: 1; overflow-y: auto; padding: 36px 20px 10px; }
        .msg-wrap { max-width: 800px; margin: 0 auto 26px; display: flex; gap: 14px; }
        .icon { width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-weight: 800; background: var(--brand); color: #0f172a; font-size: 14px; }
        .user-icon { background: #64748b; color: #f1f5f9; }
        .content { font-size: 15.5px; line-height: 1.65; flex: 1; min-width: 0; overflow-wrap: break-word; }
        .user .content { background: var(--user-bubble); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px; white-space: pre-wrap; }
        .content table { border-collapse: collapse; margin: 10px 0; width: 100%; font-size: 14px; }
        .content th, .content td { border: 1px solid var(--border); padding: 7px 10px; text-align: left; }
        .content th { background: var(--sidebar); }
        .content pre { background: #0b1120; border: 1px solid var(--border); border-radius: 8px; padding: 12px; overflow-x: auto; font-size: 13.5px; }
        .content code { background: #0b1120; border-radius: 4px; padding: 1px 5px; font-size: 13.5px; }
        .content h1, .content h2, .content h3 { margin: 14px 0 6px; line-height: 1.3; }
        .thinking { color: var(--muted); font-style: italic; font-size: 14px; }
        .error-msg { color: #f87171; }
        .input-box { padding: 18px 20px 22px; border-top: 1px solid var(--border); }
        .input-inner { max-width: 800px; margin: 0 auto; display: flex; gap: 10px; align-items: flex-end; }
        textarea { flex: 1; border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; background: var(--sidebar); color: var(--text); resize: none; outline: none; font-size: 15.5px; font-family: inherit; max-height: 200px; }
        textarea:focus { border-color: var(--brand); }
        .send-btn { background: var(--brand); color: #0f172a; border: none; border-radius: 10px; padding: 12px 18px; font-weight: 800; cursor: pointer; font-size: 14px; }
        .send-btn:disabled { opacity: .5; cursor: default; }
        @media (max-width: 700px) { aside { display: none; } }
    </style>
</head>
<body>
    <aside>
        <div class="logo">SPARK AI</div>
        <div class="tagline">Executive consulting intelligence. Structured answers, sharp questions.</div>
        <button class="side-btn" onclick="newSession()">New Session</button>
        <button class="side-btn ghost" onclick="newSession()">Clear Screen</button>
        <div class="status"><span class="dot"></span>Systems online</div>
        <div class="disclaimer">Spark provides general guidance, not professional legal, tax or financial advice. Verify important decisions with a qualified adviser.</div>
    </aside>
    <main>
        <div id="chat"></div>
        <div class="input-box">
            <div class="input-inner">
                <textarea id="p" rows="1" placeholder="Describe your business question…" oninput="autoGrow(this)"></textarea>
                <button class="send-btn" id="sendBtn" onclick="send()">Send</button>
            </div>
        </div>
    </main>
<script>
    // Conversation memory lives here and is sent with every request,
    // so Spark remembers the whole session's context.
    let history = [];
    let busy = false;

    const WELCOME = "Spark online. Tell me about your business challenge - the more specific, the sharper the advice.";

    function autoGrow(el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }

    function newSession() {
        history = [];
        document.getElementById('chat').innerHTML = '';
        add('model', WELCOME, {remember: false});
    }

    function add(role, text, opts = {}) {
        const c = document.getElementById('chat');
        const w = document.createElement('div');
        w.className = 'msg-wrap' + (role === 'user' ? ' user' : '');
        const icon = document.createElement('div');
        icon.className = 'icon' + (role === 'user' ? ' user-icon' : '');
        icon.textContent = role === 'user' ? 'U' : 'S';
        const content = document.createElement('div');
        content.className = 'content' + (opts.thinking ? ' thinking' : '') + (opts.error ? ' error-msg' : '');
        if (role === 'user' || opts.thinking || opts.error) {
            content.textContent = text;              // plain text: no HTML injection possible
        } else {
            content.innerHTML = DOMPurify.sanitize(marked.parse(text));  // AI markdown, sanitised
        }
        w.appendChild(icon); w.appendChild(content);
        c.appendChild(w);
        c.scrollTop = c.scrollHeight;
        if (opts.remember !== false && !opts.thinking && !opts.error) {
            history.push({role: role, text: text});
        }
        return w;
    }

    async function send() {
        if (busy) return;
        const i = document.getElementById('p');
        const m = i.value.trim();
        if (!m) return;
        busy = true;
        document.getElementById('sendBtn').disabled = true;
        add('user', m);
        i.value = ''; i.style.height = 'auto';
        const t = add('model', 'Spark is thinking…', {thinking: true, remember: false});
        try {
            const r = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                // send everything BEFORE this turn, plus the new message
                body: JSON.stringify({message: m, history: history.slice(0, -1)})
            });
            const d = await r.json();
            t.remove();
            if (d.reply) add('model', d.reply);
            else add('model', d.error || 'Something went wrong.', {error: true, remember: false});
        } catch (err) {
            t.remove();
            add('model', 'Connection error - check your internet and retry.', {error: true, remember: false});
        } finally {
            busy = false;
            document.getElementById('sendBtn').disabled = false;
            i.focus();
        }
    }

    document.getElementById('p').addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    newSession();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
