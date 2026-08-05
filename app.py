import os
from flask import Flask, request, jsonify
from google import genai
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Setup Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Professional Instructions
BASE_SYSTEM = (
    "You are Spark, an Elite Executive AI Assistant. "
    "Use structured Markdown (headers, bolding, tables) for clarity. "
    "Be professional, precise, and sophisticated."
)

@app.route("/")
def index():
    return HTML

@app.route("/chat", methods=["POST"])
def chat():
    try:
        d = request.get_json()
        msg = d.get("message", "").strip()
        
        # This is the stable loop that worked for you!
        for name in ["gemini-1.5-flash-latest", "gemini-flash-latest", "gemini-1.5-flash"]:
            try:
                response = client.models.generate_content(
                    model=name, 
                    config={'system_instruction': BASE_SYSTEM}, 
                    contents=msg
                )
                return jsonify({"reply": response.text})
            except: 
                continue
        
        return jsonify({"error": "System busy. Please retry."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Spark AI</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root { 
            --bg: #0f172a; 
            --sidebar: #1e293b; 
            --brand: #38bdf8; 
            --text: #f1f5f9; 
            --border: #334155; 
        }
        body { font-family: sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: var(--text); }
        aside { width: 260px; background: var(--sidebar); border-right: 1px solid var(--border); padding: 25px; display: flex; flex-direction: column; gap: 15px; }
        main { flex: 1; display: flex; flex-direction: column; }
        #chat { flex: 1; overflow-y: auto; padding: 40px 20px; }
        .msg-wrap { max-width: 800px; margin: 0 auto 30px auto; display: flex; gap: 15px; }
        .icon { width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-weight: bold; background: var(--brand); color: #0f172a; }
        .user-icon { background: #94a3b8; }
        .content { font-size: 16px; line-height: 1.6; flex: 1; }
        .input-box { padding: 25px; background: var(--bg); border-top: 1px solid var(--border); }
        textarea { 
            width: 100%; max-width: 800px; margin: 0 auto; display: block; border: 1px solid var(--border); 
            border-radius: 12px; padding: 12px; background: var(--sidebar); color: var(--text); 
            resize: none; outline: none; font-size: 16px; font-family: inherit;
        }
        .side-btn { background: var(--brand); color: #0f172a; border: none; padding: 12px; border-radius: 8px; cursor: pointer; font-weight: bold; text-align: center; }
        .thinking { color: #94a3b8; font-style: italic; font-size: 14px; }
    </style>
</head>
<body>
    <aside>
        <div style="font-size: 20px; font-weight: bold; color: var(--brand);">SPARK AI</div>
        <button class="side-btn" onclick="location.reload()">New Session</button>
        <button class="side-btn" style="background:transparent; border: 1px solid var(--border); color:#94a3b8;" onclick="clearChat()">Clear Screen</button>
    </aside>
    <main>
        <div id="chat"><div class="msg-wrap"><div class="icon">S</div><div class="content">Spark Intelligence Systems online. How can I assist you?</div></div></div>
        <div class="input-box">
            <form onsubmit="send(event)">
                <textarea id="p" rows="1" placeholder="Enter request..." oninput="autoGrow(this)"></textarea>
            </form>
        </div>
    </main>
<script>
    function autoGrow(element) {
        element.style.height = "auto";
        element.style.height = (element.scrollHeight) + "px";
    }

    function clearChat() {
        document.getElementById('chat').innerHTML = '<div class="msg-wrap"><div class="icon">S</div><div class="content">Session cleared.</div></div>';
    }

    async function send(e) {
        if(e) e.preventDefault();
        const i = document.getElementById('p');
        const m = i.value.trim();
        if(!m) return;
        add('user', m);
        i.value = '';
        i.style.height = 'auto';
        const t = add('thinking');
        try {
            const r = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: m})
            });
            const d = await r.json();
            t.remove();
            add('ai', d.reply || d.error);
        } catch(err) { t.remove(); add('ai', 'Connection error.'); }
        document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
    }

    function add(role, text) {
        const c = document.getElementById('chat');
        const w = document.createElement('div');
        w.className = 'msg-wrap';
        if(role === 'thinking') w.innerHTML = '<div class="icon">S</div><div class="content thinking">Spark is processing...</div>';
        else w.innerHTML = '<div class="icon '+(role==='user'?'user-icon':'')+'">'+(role==='user'?'U':'S')+'</div><div class="content">'+(role==='user'?text:marked.parse(text))+'</div>';
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
