import os, json, time
from flask import Flask, request, jsonify
from google import genai
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Setup Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Use the model that we KNOW works on your account
MODEL_ID = "gemini-2.0-flash"

BASE_SYSTEM = (
    "You are Spark, a professional AI. Use bold text and bullet points. "
    "Be concise to save API quota."
)

# Shared memory
HISTORY = []

@app.route("/")
def index():
    return HTML

@app.route("/chat", methods=["POST"])
def chat():
    global HISTORY
    try:
        d = request.get_json()
        msg = (d.get("message") or "").strip()
        if not msg:
            return jsonify({"error": "Empty message."}), 400

        # Add user message
        HISTORY.append({"role": "user", "parts": [{"text": msg}]})

        # Try to get a response
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                config={"system_instruction": BASE_SYSTEM},
                contents=HISTORY,
            )
            
            reply = response.text
            HISTORY.append({"role": "model", "parts": [{"text": reply}]})

            # Keep history VERY short (last 6 messages) to avoid 429/Resource errors
            if len(HISTORY) > 6:
                HISTORY = HISTORY[-6:]

            return jsonify({"reply": reply})

        except Exception as e:
            error_msg = str(e)
            # If we hit the '429' Resource limit, clear memory and try one last time
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                HISTORY = [{"role": "user", "parts": [{"text": msg}]}]
                response = client.models.generate_content(
                    model=MODEL_ID,
                    config={"system_instruction": BASE_SYSTEM},
                    contents=HISTORY
                )
                return jsonify({"reply": response.text + "\\n\\n*(Note: Memory was cleared to save quota)*"})
            
            return jsonify({"error": error_msg}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Spark AI</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root { --bg: #ffffff; --brand: #2563eb; --text: #1e293b; --border: #e2e8f0; }
        body { font-family: sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: var(--text); }
        aside { width: 260px; background: #f8fafc; border-right: 1px solid var(--border); padding: 24px; }
        main { flex: 1; display: flex; flex-direction: column; }
        #chat { flex: 1; overflow-y: auto; padding: 40px 20px; }
        .msg-wrap { max-width: 800px; margin: 0 auto 30px auto; display: flex; gap: 15px; }
        .icon { width: 30px; height: 30px; border-radius: 6px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-weight: bold; }
        .ai-icon { background: #eff6ff; color: var(--brand); }
        .user-icon { background: #f1f5f9; color: #64748b; }
        .content { font-size: 15px; line-height: 1.6; flex: 1; }
        .input-box { padding: 20px; background: white; border-top: 1px solid var(--border); }
        .input-inner { max-width: 800px; margin: 0 auto; position: relative; }
        textarea { width: 100%; border: 1px solid var(--border); border-radius: 10px; padding: 12px; font-size: 15px; resize: none; outline: none; }
        .thinking { color: #94a3b8; font-style: italic; font-size: 13px; }
    </style>
</head>
<body>
    <aside><strong>Spark Agent</strong><br><small>Ready</small></aside>
    <main>
        <div id="chat"><div class="msg-wrap"><div class="icon ai-icon">✧</div><div class="content">Spark online. How can I help?</div></div></div>
        <div class="input-box">
            <form class="input-inner" onsubmit="send(event)">
                <textarea id="p" rows="1" placeholder="Type here..."></textarea>
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
        const t = add('thinking');
        try {
            const r = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: m})
            });
            const d = await r.json();
            t.remove();
            if(d.error) add('ai', 'Error: ' + d.error);
            else add('ai', d.reply);
        } catch(err) { t.remove(); add('ai', 'Connection failed.'); }
    }
    function add(role, text) {
        const c = document.getElementById('chat');
        const w = document.createElement('div');
        w.className = 'msg-wrap';
        if(role === 'thinking') w.innerHTML = '<div class="icon ai-icon">✧</div><div class="content thinking">Spark is thinking...</div>';
        else w.innerHTML = '<div class="icon '+(role==='user'?'user-icon':'ai-icon')+'">'+(role==='user'?'U':'✧')+'</div><div class="content">'+(role==='user'?text:marked.parse(text))+'</div>';
        c.appendChild(w);
        c.scrollTop = c.scrollHeight;
        return w;
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
