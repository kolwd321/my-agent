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
# Verify current model IDs at https://docs.claude.com/en/docs/about-claude/models
MODELS = [
    os.getenv("SPARK_MODEL", "claude-haiku-4-5-20251001"),
    "claude-sonnet-5",
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
   # Replace the existing BASE_SYSTEM block in app.py with everything below.

BASE_SYSTEM = (
    "You are Spark, a private advisor to Avrosios. You work across two areas: "
    "Hauz (his startup) and general business and strategy questions.\n\n"

    "## Hauz — what you already know\n"
    "Hauz is a platform for UK university students to host and discover house "
    "parties. Hosts create a listing (date, time, theme, capacity, vibe); guests "
    "browse by city, university and date, and RSVP. The platform's job is trust "
    "and discovery — decentralising nightlife into people's living rooms.\n"
    "- Access is gated to verified students via .ac.uk email.\n"
    "- A host's exact address stays hidden until a guest is confirmed. Only an "
    "approximate area is shown before that. This is the core safety mechanic.\n"
    "- No paid ticketing in the MVP. Charging for entry to a private residence "
    "raises licensing, tax and liability problems.\n"
    "- Stack: Next.js (TypeScript, Tailwind, App Router), Supabase for database, "
    "auth and row-level security, hosted on Vercel.\n"
    "- Mobile-first. Most users are on a phone the night of the party.\n"
    "Treat the three rules above as fixed. If a suggestion would break one, say "
    "so plainly and propose something that doesn't.\n\n"

    "## How you answer\n"
    "1. Be direct and specific. No filler, no flattery, no restating the question.\n"
    "2. Lead with the answer, then the reasoning. Use short Markdown headers, bold "
    "for key points, tables for comparisons.\n"
    "3. If a request is missing something you actually need — budget, timeframe, "
    "which university, what stage the feature is at — ask at most TWO sharp "
    "questions before answering. Otherwise just answer.\n"
    "4. Quantify where you can and state your assumptions out loud.\n"
    "5. Disagree when you think he's wrong, and say why. He is building this "
    "alone and needs a second opinion, not agreement.\n"
    "6. Keep explanations plain. Short sentences beat clever ones.\n\n"

    "## What you cannot do\n"
    "You have no internet access, no access to the Hauz codebase, no files, and "
    "no live data. Say so when it matters, and never invent statistics, market "
    "figures or competitor details. If something needs looking up, say what to "
    "look up rather than guessing at it.\n\n"

    "## Regulated territory\n"
    "Hauz touches licensing, public liability, alcohol, safeguarding of young "
    "adults, and UK GDPR. Give the general picture and flag the risk clearly, "
    "then recommend a qualified professional for the final call. Never present "
    "your view as legal advice."
)
)

MAX_MESSAGE_CHARS = 4000
MAX_HISTORY_MESSAGES = 20  # most recent turns sent back to the model

# --- Simple per-IP rate limit: 20 requests per minute (in-memory) ---
_hits: dict = defaultdict(deque)
RATE_LIMIT = 20
RATE_WINDOW = 60.0
_last_sweep = 0.0


def _sweep_rate_table(now: float) -> None:
    """Drop IPs that have gone quiet so the table can't grow forever."""
    global _last_sweep
    if now - _last_sweep < 300:
        return
    _last_sweep = now
    for key in [k for k, q in _hits.items() if not q or now - q[-1] > RATE_WINDOW]:
        del _hits[key]


def rate_limited(ip: str) -> bool:
    now = time.time()
    _sweep_rate_table(now)
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


# NOTE: raw string (r""") - the JS below contains \n inside template literals,
# and a normal triple-quoted string would turn those into real newlines and
# break the script.
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spark - Executive Consulting</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
<style>
:root{
  --ink:#0A0E15;
  --panel:#111725;
  --raised:#182131;
  --line:#222D40;
  --line-soft:#1A2333;
  --text:#E7ECF4;
  --muted:#8593A9;
  --faint:#5D6B80;
  --brand:#3FC7EE;
  --ember:#F5A742;
  --danger:#F87171;
  --ok:#34D399;
  --rail:264px;
  --col:themeless;
  --radius:10px;
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0;display:flex;height:100dvh;overflow:hidden;
  background:var(--ink);color:var(--text);
  font-family:Inter,system-ui,-apple-system,sans-serif;
  font-size:15px;-webkit-font-smoothing:antialiased;
}
button{font-family:inherit}
:focus-visible{outline:2px solid var(--brand);outline-offset:2px;border-radius:6px}

/* ---------- spark mark ---------- */
.mark{width:1em;height:1em;flex:none;fill:currentColor}
@keyframes pulse{0%,100%{opacity:.35;transform:scale(.86)}50%{opacity:1;transform:scale(1)}}
.pulsing .mark{animation:pulse 1.1s ease-in-out infinite;transform-origin:center}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

/* ---------- rail ---------- */
aside{
  width:var(--rail);flex:none;background:var(--panel);
  border-right:1px solid var(--line-soft);
  display:flex;flex-direction:column;
}
.brand{
  display:flex;align-items:center;gap:9px;padding:20px 18px 16px;
  font-family:'Space Grotesk',Inter,sans-serif;font-weight:700;
  font-size:16px;letter-spacing:.13em;color:var(--text);
}
.brand .mark{font-size:17px;color:var(--ember)}
.rail-pad{padding:0 14px}
.new-btn{
  width:100%;display:flex;align-items:center;justify-content:center;gap:8px;
  background:var(--brand);color:#08121A;border:none;border-radius:var(--radius);
  padding:11px;font-weight:600;font-size:14px;cursor:pointer;
  transition:filter .15s ease;
}
.new-btn:hover{filter:brightness(1.08)}
.rail-scroll{flex:1;overflow-y:auto;padding:18px 8px 8px;min-height:0}
.rail-scroll::-webkit-scrollbar{width:8px}
.rail-scroll::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px}
.group{
  font-family:'Space Grotesk',Inter,sans-serif;
  font-size:10.5px;font-weight:500;letter-spacing:.14em;text-transform:uppercase;
  color:var(--faint);padding:14px 10px 6px;
}
.group:first-child{padding-top:0}
.thread{
  display:flex;align-items:center;gap:8px;width:100%;
  padding:9px 10px;border-radius:8px;cursor:pointer;border:none;
  background:transparent;color:var(--muted);text-align:left;
  font-size:13.5px;font-family:inherit;
}
.thread:hover{background:var(--raised);color:var(--text)}
.thread.on{background:var(--raised);color:var(--text)}
.thread.on .tick{background:var(--brand)}
.tick{width:2px;height:15px;border-radius:2px;background:transparent;flex:none}
.thread .label{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kill{
  border:none;background:transparent;color:var(--faint);cursor:pointer;
  padding:2px 4px;border-radius:5px;font-size:15px;line-height:1;opacity:0;
}
.thread:hover .kill,.thread:focus-within .kill{opacity:1}
.kill:hover{color:var(--danger);background:rgba(248,113,113,.1)}
.rail-empty{padding:12px 10px;font-size:12.5px;color:var(--faint);line-height:1.6}
.rail-foot{padding:14px 18px 18px;border-top:1px solid var(--line-soft);display:flex;flex-direction:column;gap:10px}
.status{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok)}
.dot.bad{background:var(--danger)}
.fineprint{font-size:11px;color:var(--faint);line-height:1.55}

/* ---------- main ---------- */
main{flex:1;display:flex;flex-direction:column;min-width:0}
.topbar{
  height:54px;flex:none;display:flex;align-items:center;gap:10px;
  padding:0 18px;border-bottom:1px solid var(--line-soft);
}
.hamburger{display:none;background:transparent;border:none;color:var(--muted);cursor:pointer;padding:6px;font-size:18px;line-height:1}
.topbar h1{
  flex:1;margin:0;font-size:14.5px;font-weight:500;color:var(--text);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:text;
}
.topbar h1:hover{color:var(--brand)}
.bar-btn{
  background:transparent;border:1px solid var(--line);color:var(--muted);
  border-radius:7px;padding:6px 11px;font-size:12.5px;cursor:pointer;
}
.bar-btn:hover{border-color:var(--brand);color:var(--brand)}
.bar-btn[hidden]{display:none}

#scroll{flex:1;overflow-y:auto;padding:32px 20px 8px}
#scroll::-webkit-scrollbar{width:10px}
#scroll::-webkit-scrollbar-thumb{background:var(--line);border-radius:5px}
.turn{max-width:760px;margin:0 auto 24px;display:flex;gap:14px}
.av{
  width:29px;height:29px;flex:none;border-radius:8px;
  display:flex;align-items:center;justify-content:center;font-size:15px;
  background:var(--raised);color:var(--ember);border:1px solid var(--line);
}
.turn.user .av{background:transparent;color:var(--faint);font-size:11px;font-weight:600;letter-spacing:.06em}
.body{flex:1;min-width:0;line-height:1.7;overflow-wrap:break-word}
.turn.user .body{
  background:var(--panel);border:1px solid var(--line-soft);
  border-radius:var(--radius);padding:11px 14px;white-space:pre-wrap;
}
.body>*:first-child{margin-top:0}
.body>*:last-child{margin-bottom:0}
.body h1,.body h2,.body h3{
  font-family:'Space Grotesk',Inter,sans-serif;
  margin:22px 0 8px;line-height:1.3;font-weight:700;
}
.body h1{font-size:19px}.body h2{font-size:17px}.body h3{font-size:15.5px;color:var(--brand)}
.body p{margin:0 0 12px}
.body ul,.body ol{margin:0 0 12px;padding-left:22px}
.body li{margin-bottom:5px}
.body strong{color:#fff;font-weight:600}
.body a{color:var(--brand)}
.body table{border-collapse:collapse;margin:14px 0;width:100%;font-size:13.5px}
.body th,.body td{border:1px solid var(--line);padding:8px 11px;text-align:left}
.body th{background:var(--panel);font-weight:600;color:var(--text)}
.body blockquote{margin:14px 0;padding:2px 0 2px 14px;border-left:2px solid var(--ember);color:var(--muted)}
.body pre{
  background:#070B12;border:1px solid var(--line);border-radius:9px;
  padding:13px;overflow-x:auto;margin:14px 0;
}
.body code{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:13px;background:#070B12;border-radius:4px;padding:1.5px 5px}
.body pre code{background:none;padding:0}
.body hr{border:none;border-top:1px solid var(--line);margin:20px 0}

.tools{display:flex;gap:6px;margin-top:9px;opacity:0;transition:opacity .15s ease}
.turn:hover .tools,.turn:focus-within .tools{opacity:1}
.tool{background:transparent;border:none;color:var(--faint);font-size:11.5px;cursor:pointer;padding:3px 6px;border-radius:5px}
.tool:hover{color:var(--brand);background:var(--panel)}
.thinking{color:var(--muted);font-size:14px}
.errline{color:var(--danger);font-size:14px}

/* ---------- empty state ---------- */
.blank{max-width:760px;margin:0 auto;padding:6vh 4px 0}
.blank .mark{font-size:30px;color:var(--ember)}
.blank h2{
  font-family:'Space Grotesk',Inter,sans-serif;font-size:25px;font-weight:700;
  margin:18px 0 7px;letter-spacing:-.01em;
}
.blank p{color:var(--muted);margin:0 0 26px;font-size:14.5px;line-height:1.6;max-width:52ch}
.seed-label{
  font-family:'Space Grotesk',Inter,sans-serif;font-size:10.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--faint);margin-bottom:10px;
}
.seeds{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.seed{
  text-align:left;background:var(--panel);border:1px solid var(--line-soft);
  color:var(--muted);border-radius:var(--radius);padding:12px 14px;
  font-size:13.5px;line-height:1.5;cursor:pointer;font-family:inherit;
  transition:border-color .15s ease,color .15s ease;
}
.seed:hover{border-color:var(--brand);color:var(--text)}

/* ---------- composer ---------- */
.composer{flex:none;padding:14px 20px 16px;border-top:1px solid var(--line-soft)}
.composer-inner{max-width:760px;margin:0 auto}
.field{
  display:flex;gap:9px;align-items:flex-end;background:var(--panel);
  border:1px solid var(--line);border-radius:13px;padding:8px 8px 8px 14px;
  transition:border-color .15s ease;
}
.field:focus-within{border-color:var(--brand)}
textarea{
  flex:1;border:none;background:transparent;color:var(--text);resize:none;
  outline:none;font-size:15px;font-family:inherit;line-height:1.6;
  padding:6px 0;max-height:190px;
}
textarea::placeholder{color:var(--faint)}
.send{
  background:var(--brand);color:#08121A;border:none;border-radius:9px;
  padding:9px 15px;font-weight:600;cursor:pointer;font-size:13.5px;flex:none;
}
.send:disabled{opacity:.4;cursor:default}
.undertext{
  display:flex;justify-content:space-between;gap:14px;
  margin-top:8px;font-size:11px;color:var(--faint);line-height:1.5;
}
.undertext .count.warn{color:var(--ember)}

/* ---------- mobile ---------- */
.scrim{display:none;position:fixed;inset:0;background:rgba(4,7,12,.62);z-index:8}
@media (max-width:820px){
  aside{
    position:fixed;inset:0 auto 0 0;z-index:9;
    transform:translateX(-100%);transition:transform .22s ease;
  }
  body.rail-open aside{transform:translateX(0)}
  body.rail-open .scrim{display:block}
  .hamburger{display:block}
  #scroll{padding:22px 14px 8px}
  .composer{padding:12px 14px 14px}
  .blank{padding-top:4vh}
  .seeds{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="scrim" onclick="toggleRail(false)"></div>

<aside>
  <div class="brand">
    <svg class="mark" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 1.6l2.2 7.9c.1.4.4.7.8.8l7.4 1.7-7.4 1.7c-.4.1-.7.4-.8.8L12 22.4l-2.2-7.9c-.1-.4-.4-.7-.8-.8L1.6 12l7.4-1.7c.4-.1.7-.4.8-.8z"/></svg>
    SPARK
  </div>
  <div class="rail-pad">
    <button class="new-btn" onclick="startNew()">New consultation</button>
  </div>
  <div class="rail-scroll" id="rail"></div>
  <div class="rail-foot">
    <div class="status"><span class="dot" id="dot"></span><span id="statusText">Checking service…</span></div>
    <div class="fineprint">General guidance only - not legal, tax or financial advice. Conversations are stored in this browser.</div>
  </div>
</aside>

<main>
  <div class="topbar">
    <button class="hamburger" onclick="toggleRail(true)" aria-label="Show conversations">☰</button>
    <h1 id="title" onclick="renameActive()" title="Click to rename">New consultation</h1>
    <button class="bar-btn" id="exportBtn" onclick="exportActive()" hidden>Export</button>
  </div>

  <div id="scroll"></div>

  <div class="composer">
    <div class="composer-inner">
      <div class="field">
        <textarea id="input" rows="1" placeholder="Describe the business question - context, constraints, what you're deciding." oninput="grow(this)"></textarea>
        <button class="send" id="send" onclick="send()">Send</button>
      </div>
      <div class="undertext">
        <span>Enter to send &middot; Shift+Enter for a new line</span>
        <span class="count" id="count"></span>
      </div>
    </div>
  </div>
</main>

<script>
const STORE_KEY = 'spark.threads.v1';
const ACTIVE_KEY = 'spark.active.v1';
const MAX_CHARS = 4000;

const SEEDS = [
  "We're pricing a new service line and have no benchmark. How should I approach it?",
  "Two suppliers, similar quotes, different risk profiles. Help me build a comparison.",
  "Our lead volume is fine but conversion dropped. Where do I start diagnosing?",
  "Draft the agenda for a quarterly review with the leadership team."
];

let threads = [];
let activeId = null;
let busy = false;

/* ---------- storage ---------- */
function load(){
  try{
    threads = JSON.parse(localStorage.getItem(STORE_KEY) || '[]');
    if(!Array.isArray(threads)) threads = [];
  }catch(e){ threads = []; }
  activeId = localStorage.getItem(ACTIVE_KEY) || null;
  if(activeId && !threads.some(t => t.id === activeId)) activeId = null;
}

function save(){
  try{
    localStorage.setItem(STORE_KEY, JSON.stringify(threads));
    if(activeId) localStorage.setItem(ACTIVE_KEY, activeId);
    else localStorage.removeItem(ACTIVE_KEY);
  }catch(e){
    // Almost always the ~5MB quota. Shed the oldest thread and retry once.
    if(threads.length > 1){
      threads = threads.slice(0, -1);
      try{ localStorage.setItem(STORE_KEY, JSON.stringify(threads)); }catch(_){}
      renderRail();
    }
  }
}

const active = () => threads.find(t => t.id === activeId) || null;

function titleFrom(text){
  const clean = text.replace(/\s+/g,' ').trim();
  return clean.length > 46 ? clean.slice(0,46).trimEnd() + '…' : (clean || 'Untitled');
}

/* ---------- rail ---------- */
function bucket(ts){
  const now = new Date();
  const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if(ts >= dayStart) return 'Today';
  if(ts >= dayStart - 6*86400000) return 'Previous 7 days';
  if(ts >= dayStart - 29*86400000) return 'Previous 30 days';
  return 'Earlier';
}

function renderRail(){
  const rail = document.getElementById('rail');
  rail.innerHTML = '';
  if(!threads.length){
    const p = document.createElement('div');
    p.className = 'rail-empty';
    p.textContent = 'Saved consultations appear here once you send a first message.';
    rail.appendChild(p);
    return;
  }
  const sorted = [...threads].sort((a,b) => b.updatedAt - a.updatedAt);
  let current = '';
  for(const t of sorted){
    const b = bucket(t.updatedAt);
    if(b !== current){
      current = b;
      const h = document.createElement('div');
      h.className = 'group';
      h.textContent = b;
      rail.appendChild(h);
    }
    const row = document.createElement('button');
    row.className = 'thread' + (t.id === activeId ? ' on' : '');
    row.onclick = () => open(t.id);

    const tick = document.createElement('span');
    tick.className = 'tick';

    const label = document.createElement('span');
    label.className = 'label';
    label.textContent = t.title;

    const kill = document.createElement('span');
    kill.className = 'kill';
    kill.textContent = '×';
    kill.setAttribute('role','button');
    kill.title = 'Delete';
    kill.onclick = (e) => { e.stopPropagation(); remove(t.id); };

    row.append(tick, label, kill);
    rail.appendChild(row);
  }
}

function open(id){
  activeId = id;
  save(); renderRail(); renderThread(); toggleRail(false);
}

function remove(id){
  const t = threads.find(x => x.id === id);
  if(!t) return;
  if(!confirm('Delete "' + t.title + '"? This cannot be undone.')) return;
  threads = threads.filter(x => x.id !== id);
  if(activeId === id) activeId = null;
  save(); renderRail(); renderThread();
}

function startNew(){
  activeId = null;
  save(); renderRail(); renderThread(); toggleRail(false);
  document.getElementById('input').focus();
}

function renameActive(){
  const t = active();
  if(!t) return;
  const next = prompt('Rename consultation', t.title);
  if(next === null) return;
  t.title = next.trim() || t.title;
  t.updatedAt = Date.now();
  save(); renderRail();
  document.getElementById('title').textContent = t.title;
}

function toggleRail(on){ document.body.classList.toggle('rail-open', on); }

/* ---------- rendering ---------- */
function renderThread(){
  const scroll = document.getElementById('scroll');
  const t = active();
  scroll.innerHTML = '';
  document.getElementById('title').textContent = t ? t.title : 'New consultation';
  document.getElementById('exportBtn').hidden = !t;

  if(!t){ scroll.appendChild(blankState()); return; }
  for(const m of t.messages) scroll.appendChild(turnEl(m.role, m.text));
  scroll.scrollTop = scroll.scrollHeight;
}

function blankState(){
  const wrap = document.createElement('div');
  wrap.className = 'blank';
  wrap.innerHTML =
    '<svg class="mark" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 1.6l2.2 7.9c.1.4.4.7.8.8l7.4 1.7-7.4 1.7c-.4.1-.7.4-.8.8L12 22.4l-2.2-7.9c-.1-.4-.4-.7-.8-.8L1.6 12l7.4-1.7c.4-.1.7-.4.8-.8z"/></svg>' +
    '<h2>What are you deciding?</h2>' +
    '<p>Give the context, the constraint and the call you need to make. Spark will ask before it assumes.</p>' +
    '<div class="seed-label">Start from</div>';
  const grid = document.createElement('div');
  grid.className = 'seeds';
  for(const s of SEEDS){
    const b = document.createElement('button');
    b.className = 'seed';
    b.textContent = s;
    b.onclick = () => {
      const i = document.getElementById('input');
      i.value = s; grow(i); i.focus(); updateCount();
    };
    grid.appendChild(b);
  }
  wrap.appendChild(grid);
  return wrap;
}

function turnEl(role, text, opts = {}){
  const wrap = document.createElement('div');
  wrap.className = 'turn' + (role === 'user' ? ' user' : '') + (opts.thinking ? ' pulsing' : '');

  const av = document.createElement('div');
  av.className = 'av';
  if(role === 'user'){ av.textContent = 'YOU'; }
  else{
    av.innerHTML = '<svg class="mark" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 1.6l2.2 7.9c.1.4.4.7.8.8l7.4 1.7-7.4 1.7c-.4.1-.7.4-.8.8L12 22.4l-2.2-7.9c-.1-.4-.4-.7-.8-.8L1.6 12l7.4-1.7c.4-.1.7-.4.8-.8z"/></svg>';
  }

  const body = document.createElement('div');
  body.className = 'body' + (opts.thinking ? ' thinking' : '') + (opts.error ? ' errline' : '');
  if(role === 'user' || opts.thinking || opts.error){
    body.textContent = text;                                        // plain text, no injection
  }else{
    body.innerHTML = DOMPurify.sanitize(marked.parse(text));        // model markdown, sanitised
    const tools = document.createElement('div');
    tools.className = 'tools';
    const copy = document.createElement('button');
    copy.className = 'tool';
    copy.textContent = 'Copy';
    copy.onclick = () => {
      navigator.clipboard.writeText(text).then(() => {
        copy.textContent = 'Copied';
        setTimeout(() => { copy.textContent = 'Copy'; }, 1400);
      });
    };
    tools.appendChild(copy);
    body.appendChild(tools);
  }

  wrap.append(av, body);
  return wrap;
}

/* ---------- composer ---------- */
function grow(el){ el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 190) + 'px'; }

function updateCount(){
  const n = document.getElementById('input').value.length;
  const el = document.getElementById('count');
  if(n > MAX_CHARS * 0.8){
    el.textContent = n + ' / ' + MAX_CHARS;
    el.classList.toggle('warn', n > MAX_CHARS);
  }else{
    el.textContent = '';
    el.classList.remove('warn');
  }
}

async function send(){
  if(busy) return;
  const input = document.getElementById('input');
  const text = input.value.trim();
  if(!text) return;
  if(text.length > MAX_CHARS){ alert('Message is too long (max ' + MAX_CHARS + ' characters).'); return; }

  let t = active();
  if(!t){
    t = { id: 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2,7),
          title: titleFrom(text), createdAt: Date.now(), updatedAt: Date.now(), messages: [] };
    threads.unshift(t);
    activeId = t.id;
    document.getElementById('scroll').innerHTML = '';
  }

  const prior = t.messages.map(m => ({role: m.role, text: m.text}));   // everything before this turn

  busy = true;
  document.getElementById('send').disabled = true;
  t.messages.push({role:'user', text});
  t.updatedAt = Date.now();
  save(); renderRail();
  document.getElementById('title').textContent = t.title;
  document.getElementById('exportBtn').hidden = false;

  const scroll = document.getElementById('scroll');
  scroll.appendChild(turnEl('user', text));
  input.value = ''; grow(input); updateCount();
  const pending = turnEl('model', 'Working through it…', {thinking:true});
  scroll.appendChild(pending);
  scroll.scrollTop = scroll.scrollHeight;

  try{
    const r = await fetch('/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message: text, history: prior})
    });
    const d = await r.json();
    pending.remove();
    if(d.reply){
      t.messages.push({role:'model', text:d.reply});
      t.updatedAt = Date.now();
      save(); renderRail();
      scroll.appendChild(turnEl('model', d.reply));
    }else{
      scroll.appendChild(turnEl('model', d.error || 'Something went wrong.', {error:true}));
    }
  }catch(err){
    pending.remove();
    scroll.appendChild(turnEl('model', 'Connection error - check your network and retry.', {error:true}));
  }finally{
    busy = false;
    document.getElementById('send').disabled = false;
    scroll.scrollTop = scroll.scrollHeight;
    input.focus();
  }
}

function exportActive(){
  const t = active();
  if(!t) return;
  const lines = ['# ' + t.title, '', '_' + new Date(t.createdAt).toLocaleString() + '_', ''];
  for(const m of t.messages){
    lines.push('## ' + (m.role === 'user' ? 'You' : 'Spark'), '', m.text, '');
  }
  const blob = new Blob([lines.join('\n')], {type:'text/markdown'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = t.title.replace(/[^a-z0-9]+/gi,'-').toLowerCase().slice(0,50) + '.md';
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------- boot ---------- */
document.getElementById('input').addEventListener('keydown', e => {
  if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); send(); }
});
document.getElementById('input').addEventListener('input', updateCount);

fetch('/health').then(r => r.json()).then(d => {
  const ok = d.status === 'ok' && d.key_configured;
  document.getElementById('dot').classList.toggle('bad', !ok);
  document.getElementById('statusText').textContent = ok ? 'Service online' : 'API key not configured';
}).catch(() => {
  document.getElementById('dot').classList.add('bad');
  document.getElementById('statusText').textContent = 'Service unreachable';
});

load(); renderRail(); renderThread();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
