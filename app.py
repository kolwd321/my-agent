import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("spark")

app = Flask(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ACCESS_CODE = os.getenv("ACCESS_CODE", "")

# Cheapest first; the loop falls back if a name is rejected.
MODELS = [
    os.getenv("SPARK_MODEL", "claude-haiku-4-5"),
    "claude-sonnet-4-5",
]

# ============================================================
# THE SHARED ROOM
# One conversation, stored on the server, visible to everyone
# with the access code. Both founders (and Spark) share it.
# NOTE: it lives in memory - if Render restarts or the free
# instance spins down, the room resets. Fine for daily use;
# copy anything precious somewhere permanent.
# ============================================================
_room_lock = threading.Lock()
_room: list = []          # {id, role: "user"|"model", name, text, ts}
_next_id = 1
_busy_with: str = ""      # name of whoever Spark is currently answering


def room_add(role: str, name: str, text: str) -> dict:
    global _next_id
    with _room_lock:
        msg = {"id": _next_id, "role": role, "name": name, "text": text, "ts": time.time()}
        _room.append(msg)
        _next_id += 1
        # keep the room from growing forever
        if len(_room) > 500:
            del _room[: len(_room) - 500]
        return msg


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


# Facts about your business that Spark should always know.
# Edit this - or set the SPARK_CONTEXT env var on Render to override without code changes.
EMPLOYER_CONTEXT = os.getenv("SPARK_CONTEXT") or (
    "Your employers are two co-founders building Hauz (hauz.uk) - a mobile-first web app "
    "where verified UK university students host and discover house parties. Free RSVP only "
    "(no payments, UK Licensing Act caution), exact party addresses stay hidden until a host "
    "approves a guest, launch city Sheffield, launch window: freshers week in late September. "
    "Stack: Next.js + Supabase + Vercel, with in-app AI agents already live. "
    "They are also experimenting with side projects like this assistant."
)

BASE_SYSTEM = (
    "You are Spark, a private executive assistant employed by two co-founders, and you are all "
    "talking in ONE shared room - both founders see every message, including each other's.\n\n"
    "How you behave:\n"
    "1. Talk like a sharp, experienced colleague - natural first-person language, warm but "
    "efficient, contractions welcome, no corporate-brochure tone. Never open with 'As an AI'. "
    "(If someone sincerely asks whether you are human, be honest.)\n"
    "2. Each human message is prefixed with the speaker's name. Address people by name when it "
    "helps, notice when the founders disagree, and help them reach a decision together - "
    "summarise both views, then give YOUR recommendation.\n"
    "3. You know your employers' business inside out:\n" + EMPLOYER_CONTEXT + "\n"
    "4. Use that context proactively - connect advice to Hauz and their real situation instead "
    "of generic answers. Refer back to earlier decisions in the conversation like a colleague would.\n"
    "5. Be direct and have opinions. Recommend ONE course of action and say why, then note the "
    "main alternative.\n"
    "6. Structure longer answers with light Markdown. Keep quick questions quick.\n"
    "7. If a request is missing a key fact, ask at most TWO sharp questions first.\n"
    "8. Quantify when you can, state assumptions, never invent statistics - you have no live "
    "data or internet access, and you flag that when it matters.\n"
    "9. For legal, tax or regulated questions: practical picture first, then recommend a "
    "qualified professional for the final call."
)

MAX_MESSAGE_CHARS = 4000
MAX_HISTORY_MESSAGES = 30  # recent room messages sent to the model

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


def code_ok(data: dict) -> bool:
    return not ACCESS_CODE or (data or {}).get("code") == ACCESS_CODE


@app.route("/")
def index():
    return HTML


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "key_configured": bool(ANTHROPIC_API_KEY),
        "room_messages": len(_room),
    })


@app.route("/messages", methods=["POST"])
def messages():
    """Poll endpoint: returns room messages newer than 'since'."""
    data = request.get_json(silent=True) or {}
    if not code_ok(data):
        return jsonify({"error": "access code required", "need_code": True}), 401
    since = int(data.get("since") or 0)
    with _room_lock:
        new = [m for m in _room if m["id"] > since]
    return jsonify({"messages": new, "busy_with": _busy_with})


@app.route("/chat", methods=["POST"])
def chat():
    global _busy_with
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    if rate_limited(ip):
        return jsonify({"error": "Rate limit reached - wait a minute and try again."}), 429

    data = request.get_json(silent=True) or {}
    if not code_ok(data):
        return jsonify({"error": "access code required", "need_code": True}), 401

    name = (data.get("name") or "Founder").strip()[:30] or "Founder"
    msg = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"error": "Empty message."}), 400
    if len(msg) > MAX_MESSAGE_CHARS:
        return jsonify({"error": f"Message too long (max {MAX_MESSAGE_CHARS} characters)."}), 400
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Server is missing ANTHROPIC_API_KEY - set it in Render > Environment."}), 500

    # The human message goes into the shared room immediately,
    # so the other founder sees it even before Spark replies.
    room_add("user", name, msg)

    # Build Claude's view of the room: names embedded in the text.
    with _room_lock:
        recent = _room[-MAX_HISTORY_MESSAGES:]
    claude_messages = []
    for m in recent:
        if m["role"] == "user":
            claude_messages.append({"role": "user", "content": f'{m["name"]}: {m["text"]}'})
        else:
            claude_messages.append({"role": "assistant", "content": m["text"]})
    # Claude requires the conversation to start with a user turn.
    while claude_messages and claude_messages[0]["role"] != "user":
        claude_messages.pop(0)

    _busy_with = name
    try:
        last_error = None
        for model in MODELS:
            try:
                reply = call_claude(model, BASE_SYSTEM, claude_messages)
                if not reply:
                    raise ValueError("empty response")
                room_add("model", "Spark", reply)
                log.info("chat ok model=%s from=%s ip=%s", model, name, ip)
                return jsonify({"ok": True})
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:300]
                last_error = f"{e.code} {body}"
                log.warning("model %s failed: %s", model, last_error)
                continue
            except Exception as e:  # noqa: BLE001
                last_error = e
                log.warning("model %s failed: %s", model, e)
                continue
        log.error("all models failed for %s: %s", name, last_error)
        room_add("model", "Spark", "(I hit a technical problem answering that - check the Render logs, then ask me again.)")
        return jsonify({"ok": False}), 502
    finally:
        _busy_with = ""


@app.route("/clear", methods=["POST"])
def clear():
    data = request.get_json(silent=True) or {}
    if not code_ok(data):
        return jsonify({"error": "access code required", "need_code": True}), 401
    with _room_lock:
        _room.clear()
    room_add("model", "Spark", "Fresh start. What are we working on?")
    return jsonify({"ok": True})


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Spark AI - Founders' Room</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
    <style>
        :root {
            --bg: #0f172a; --sidebar: #1e293b; --brand: #38bdf8;
            --text: #f1f5f9; --muted: #94a3b8; --border: #334155;
            --user-bubble: #1d2b45; --partner-bubble: #16241c;
        }
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; display: flex; height: 100dvh; background: var(--bg); color: var(--text); }
        aside { width: 250px; background: var(--sidebar); border-right: 1px solid var(--border); padding: 25px 20px; display: flex; flex-direction: column; gap: 14px; }
        .logo { font-size: 20px; font-weight: 800; color: var(--brand); letter-spacing: .04em; }
        .tagline { font-size: 12px; color: var(--muted); margin-top: -8px; line-height: 1.5; }
        .side-btn { background: transparent; border: 1px solid var(--border); color: var(--muted); padding: 11px; border-radius: 8px; cursor: pointer; font-weight: 700; font-size: 13px; }
        .who { font-size: 13px; color: var(--muted); }
        .who b { color: var(--text); }
        .status { margin-top: auto; font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 7px; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: #34d399; }
        .disclaimer { font-size: 11px; color: #64748b; line-height: 1.5; }
        main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
        #chat { flex: 1; overflow-y: auto; padding: 30px 20px 10px; }
        .msg-wrap { max-width: 820px; margin: 0 auto 22px; display: flex; gap: 13px; }
        .icon { width: 34px; height: 34px; border-radius: 9px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-weight: 800; background: var(--brand); color: #0f172a; font-size: 14px; }
        .icon.me { background: #64748b; color: #f1f5f9; }
        .icon.partner { background: #34d399; color: #0f172a; }
        .stack { flex: 1; min-width: 0; }
        .author { font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 700; }
        .content { font-size: 15.5px; line-height: 1.6; overflow-wrap: break-word; }
        .bubble { border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px; white-space: pre-wrap; }
        .bubble.me { background: var(--user-bubble); }
        .bubble.partner { background: var(--partner-bubble); }
        .content table { border-collapse: collapse; margin: 10px 0; width: 100%; font-size: 14px; }
        .content th, .content td { border: 1px solid var(--border); padding: 7px 10px; text-align: left; }
        .content th { background: var(--sidebar); }
        .content pre { background: #0b1120; border: 1px solid var(--border); border-radius: 8px; padding: 12px; overflow-x: auto; font-size: 13.5px; }
        .content code { background: #0b1120; border-radius: 4px; padding: 1px 5px; font-size: 13.5px; }
        .thinking { color: var(--muted); font-style: italic; font-size: 13.5px; max-width: 820px; margin: 0 auto 16px; padding-left: 47px; }
        .input-box { padding: 16px 20px 20px; border-top: 1px solid var(--border); }
        .input-inner { max-width: 820px; margin: 0 auto; display: flex; gap: 10px; align-items: flex-end; }
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
        <div class="tagline">Founders' room - one shared conversation for both of you, plus Spark.</div>
        <div class="who">Signed in as <b id="whoami">…</b></div>
        <button class="side-btn" onclick="changeName()">Change my name</button>
        <button class="side-btn" onclick="clearRoom()">Clear room (for everyone)</button>
        <div class="status"><span class="dot"></span><span id="statusText">Live - updates every few seconds</span></div>
        <div class="disclaimer">The room resets if the server restarts (free hosting). Copy anything important somewhere safe. Spark gives general guidance, not professional legal or financial advice.</div>
    </aside>
    <main>
        <div id="chat"></div>
        <div id="typing" class="thinking" style="display:none"></div>
        <div class="input-box">
            <div class="input-inner">
                <textarea id="p" rows="1" placeholder="Message the room…" oninput="autoGrow(this)"></textarea>
                <button class="send-btn" id="sendBtn" onclick="send()">Send</button>
            </div>
        </div>
    </main>
<script>
    let myName = "";
    let accessCode = "";
    let lastId = 0;
    let busy = false;

    function autoGrow(el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }

    function ensureName() {
        while (!myName) {
            myName = (window.prompt("Your name (so your co-founder and Spark know who's talking):") || "").trim().slice(0, 30);
        }
        document.getElementById('whoami').textContent = myName;
    }
    function changeName() { myName = ""; ensureName(); }

    function render(m) {
        const c = document.getElementById('chat');
        const w = document.createElement('div');
        w.className = 'msg-wrap';
        const isSpark = m.role === 'model';
        const isMe = !isSpark && m.name === myName;
        const icon = document.createElement('div');
        icon.className = 'icon' + (isSpark ? '' : (isMe ? ' me' : ' partner'));
        icon.textContent = isSpark ? 'S' : (m.name[0] || '?').toUpperCase();
        const stack = document.createElement('div');
        stack.className = 'stack';
        const author = document.createElement('div');
        author.className = 'author';
        author.textContent = isSpark ? 'Spark' : (isMe ? m.name + ' (you)' : m.name);
        const content = document.createElement('div');
        content.className = 'content';
        if (isSpark) {
            content.innerHTML = DOMPurify.sanitize(marked.parse(m.text));
        } else {
            content.classList.add('bubble', isMe ? 'me' : 'partner');
            content.textContent = m.text;
        }
        stack.appendChild(author); stack.appendChild(content);
        w.appendChild(icon); w.appendChild(stack);
        c.appendChild(w);
        c.scrollTop = c.scrollHeight;
    }

    async function poll() {
        try {
            const r = await fetch('/messages', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({since: lastId, code: accessCode})
            });
            const d = await r.json();
            if (d.need_code) {
                accessCode = window.prompt('This is a private room. Enter the access code:') || '';
                return;
            }
            (d.messages || []).forEach(m => { render(m); lastId = Math.max(lastId, m.id); });
            const typing = document.getElementById('typing');
            if (d.busy_with) {
                typing.style.display = '';
                typing.textContent = 'Spark is thinking (answering ' + d.busy_with + ')…';
            } else {
                typing.style.display = 'none';
            }
        } catch (e) { /* transient network issue - next poll will catch up */ }
    }

    async function send() {
        if (busy) return;
        const i = document.getElementById('p');
        const m = i.value.trim();
        if (!m) return;
        busy = true;
        document.getElementById('sendBtn').disabled = true;
        i.value = ''; i.style.height = 'auto';
        try {
            const r = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: m, name: myName, code: accessCode})
            });
            const d = await r.json();
            if (d.need_code) {
                accessCode = window.prompt('This is a private room. Enter the access code:') || '';
                i.value = m; autoGrow(i);
            }
            if (d.error && !d.need_code) alert(d.error);
        } catch (e) { alert('Connection error - try again.'); }
        finally {
            busy = false;
            document.getElementById('sendBtn').disabled = false;
            await poll();
            i.focus();
        }
    }

    async function clearRoom() {
        if (!window.confirm('Clear the whole room for BOTH of you?')) return;
        await fetch('/clear', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code: accessCode}) });
        document.getElementById('chat').innerHTML = '';
        lastId = 0;
        await poll();
    }

    document.getElementById('p').addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });

    ensureName();
    poll();
    setInterval(poll, 2500);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
