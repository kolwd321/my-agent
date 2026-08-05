import os, json
from flask import Flask, request, jsonify
from google import genai
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Setup Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Model and Debug settings
MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Professional system prompt
BASE_SYSTEM = (
    "You are a premium, enterprise-grade AI Assistant named Spark.\n"
    "Personality: Helpful, precise, calm, and professional.\n\n"
    "Rules:\n"
    "1. Use Markdown for structure.\n"
    "2. If you don't know an answer, say so.\n"
    "3. Keep a professional tone."
)

# Memory
HISTORY = []

@app.route("/")
def index():
    return HTML

@app.route("/chat", methods=["POST"])
def chat():
    try:
        d = request.get_json()
        msg = (d.get("message") or "").strip()
        if not msg:
            return jsonify({"error": "Empty message."}), 400

        # Add to history
        HISTORY.append({"role": "user", "parts": [{"text": msg}]})

        # Generate response
        response = client.models.generate_content(
            model=MODEL,
            config={"system_instruction": BASE_SYSTEM},
            contents=HISTORY,
        )
        
        reply = response.text
        HISTORY.append({"role": "model", "parts": [{"text": reply}]})

        if len(HISTORY) > 20:
            HISTORY.pop(0)

        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Enterprise AI Platform</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root { --bg: #ffffff; --sidebar: #f8fafc; --brand: #2563eb; --text: #1e293b; --border: #e2e8f0; }
        body { font-family: sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: var(--text); }
        aside { width: 260px; background: var(--sidebar); border-right: 1px solid var(--border); padding: 24px; display: flex; flex-direction: column; }
        main { flex: 1; display: flex; flex-direction: column; position: relative; }
        #chat { flex: 1; overflow-y: auto; padding: 60px 20px; }
        .msg-wrap { max-width: 800px; margin: 0 auto 40px auto; display: flex; gap: 20px; }
        .icon { width: 36px; height: 36px; border-radius: 8px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .ai-icon { background: #eff6ff; color: var(--brand); }
        .user-icon { background: #f1f5f9; color: #64748b; }
        .content { font-size: 16px; line-height: 1.7; color: #334155; flex: 1; }
        .content pre { background: #f3f4f6; padding: 15px; border-radius: 8px; overflow-x: auto; }
        .input-box { padding: 30px; position: sticky; bottom: 0; background: white; }
        .input-inner { max-width: 800px; margin: 0 auto; position: relative; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-radius: 12px; }
        textarea { width: 100%; border: 1px solid var(--border); border-radius: 12px; padding: 16px 50px 16px 16px; font-size: 16px; resize: none; outline: none; font-family: inherit; }
        .send-btn { position: absolute; right: 10px; bottom: 10px; background: var(--brand); color: white; border: none; padding: 8px 15px; border-radius: 8px; cursor: pointer; font-weight: bold; }
        .copy-btn { margin-top: 10px; background: none; border: 1px solid #e2e8f0; padding: 4px 8px; font-size: 11px; color: #94a3b8; cursor: pointer; border-radius: 4px; }
        .thinking { color: #94a3b8; font-style: italic; }
        .dot { display: inline-block; animation: blink 1.2s infinite; }
        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes blink { 0%,80%,100% {opacity:0.2} 40% {opacity:1} }
    </style>
</head>
<body>
    <aside>
        <div style="background:white; border:1px solid #e2e8f0; padding:10px; border-radius:8px; text-align:center; cursor:pointer; font-size:14px;" onclick="location.reload()">+ New Chat</div>
        <div style="font-size:11px; font-weight:bold; color:#94a3b8; margin: 20px 0 10px 0;">WORKSPACE</div>
        <div style="font-size:13px; color:#64748b;">Active Session</div>
    </aside>
    <main>
        <div id="chat">
            <div class="msg-wrap">
                <div class="icon ai-icon">✧</div>
                <div class="content">Professional systems active. How can I assist you today?</div>
            </div>
        </div>
        <div class="input-box">
            <form class="input-inner" onsubmit="send(event)">
                <textarea id="p" rows="1" placeholder="Enter request..." autocomplete="off"></textarea>
                <button type="submit" class="send-btn">Send</button>
            </form>
        </div>
    </main>
<script>
    async function send(e) {
        if(e) e.preventDefault();
        const i = document.getElementById('p');
        const m = i.value.trim();
        if(!m) return;
        add('user', m);
        i.value = '';
        const think = add('thinking');
        try {
            const r = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: m})
            });
            const d = await r.json();
            if(d.error) {
                think.innerHTML = '<span style="color:#ef4444;">' + d.error + '</span>';
            } else {
                const w = think.closest('.msg-wrap');
                w.innerHTML = '<div class="icon ai-icon">✧</div>' +
                              '<div class="content">' + marked.parse(d.reply) +
                              '<button class="copy-btn" onclick="copy(this)">Copy Text</button></div>';
                w.dataset.raw = d.reply;
            }
        } catch(err) {
            think.innerHTML = '<span style="color:#ef4444;">Failed to connect.</span>';
        }
        document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
    }
    function add(role, text) {
        const c = document.getElementById('chat');
        const w = document.createElement('div');
        w.className = 'msg-wrap';
        if(role === 'thinking') {
            w.innerHTML = '<div class="icon ai-icon">✧</div><div class="content thinking">Thinking<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></div>';
        } else if(role === 'user') {
            w.innerHTML = '<div class="icon user-icon">U</div><div class="content">' + text + '</div>';
        } else {
            w.innerHTML = '<div class="icon ai-icon">✧</div><div class="content">' + marked.parse(text) + '<button class="copy-btn" onclick="copy(this)">Copy Text</button></div>';
            w.dataset.raw = text;
        }
        c.appendChild(w);
        c.scrollTop = c.scrollHeight;
        return w;
    }
    function copy(btn) {
        const text = btn.closest('.msg-wrap').dataset.raw;
        navigator.clipboard.writeText(text);
        btn.innerText = 'Copied!';
        setTimeout(function(){ btn.innerText = 'Copy Text'; }, 2000);
    }
    document.getElementById('p').addEventListener('keydown', function(e) {
        if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
