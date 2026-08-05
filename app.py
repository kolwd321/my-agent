import os, json
from flask import Flask, request, jsonify
from google import genai
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Setup Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Spark's personality stays the same
BASE_SYSTEM = (
    "You are Spark, a professional AI Assistant. "
    "Use headings, bold text, and bullet points."
)

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

        # STABLE LOOP: This is what made it work, so we keep it!
        last_error = "Unknown error"
        for name in ["gemini-1.5-flash-latest", "gemini-flash-latest", "gemini-1.5-flash"]:
            try:
                response = client.models.generate_content(
                    model=name, 
                    config={'system_instruction': BASE_SYSTEM}, 
                    contents=msg
                )
                return jsonify({"reply": response.text})
            except Exception as e:
                last_error = str(e)
                continue
        
        return jsonify({"error": f"Connection failed: {last_error}"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Spark AI | Professional</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        /* NEW THEME: Professional "Midnight" Claude Style */
        :root { 
            --bg: #0f172a; 
            --sidebar: #1e293b; 
            --brand: #38bdf8; 
            --text: #f1f5f9; 
            --text-muted: #94a3b8;
            --border: #334155; 
            --ai-msg: #1e293b;
            --user-msg: #334155;
        }
        
        body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: var(--text); }
        
        aside { 
            width: 260px; background: var(--sidebar); border-right: 1px solid var(--border); 
            padding: 24px; display: flex; flex-direction: column; gap: 20px;
        }
        
        main { flex: 1; display: flex; flex-direction: column; position: relative; }
        
        #chat { flex: 1; overflow-y: auto; padding: 60px 20px; scroll-behavior: smooth; }
        
        .msg-wrap { max-width: 800px; margin: 0 auto 30px auto; display: flex; gap: 15px; }
        
        .icon { 
            width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0; 
            display: flex; align-items: center; justify-content: center; font-weight: bold; 
        }
        .ai-icon { background: var(--brand); color: #0f172a; }
        .user-icon { background: var(--text-muted); color: #0f172a; }
        
        .content { font-size: 15px; line-height: 1.6; color: var(--text); flex: 1; }
        .content pre { background: #000; padding: 15px; border-radius: 8px; border: 1px solid var(--border); overflow-x: auto; color: #38bdf8; }
        
        .input-box { padding: 25px; background: var(--bg); border-top: 1px solid var(--border); }
        .input-inner { max-width: 800px; margin: 0 auto; position: relative; }
        
        textarea { 
            width: 100%; border: 1px solid var(--border); border-radius: 12px; 
            padding: 14px; font-size: 15px; resize: none; outline: none; 
            background: var(--sidebar); color: var(--text); font-family: inherit;
        }
        
        /* Sidebar Buttons */
        .side-btn { 
            background: var(--brand); color: #0f172a; border: none; padding: 12px; 
            border-radius: 8px; cursor: pointer; font-weight: bold; transition: 0.2s; 
            text-align: center; font-size: 14px;
        }
        .side-btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .clear-btn { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
        .clear-btn:hover { border-color: #ef4444; color: #ef4444; }

        .thinking { color: var(--text-muted); font-style: italic; font-size: 13px; margin-top: 5px; }
    </style>
</head>
<body>
    <aside>
        <div style="font-size: 20px; font-weight: bold; margin-bottom: 10px;">✧ Spark AI</div>
        <button class="side-btn" onclick="location.reload()">+ New Session</button>
        <button class="side-btn clear-btn" onclick="clearChat()">🗑 Clear Screen</button>
        <div style="margin-top: auto; font-size: 11px; color: var(--text-muted);">v2.1 | Stable Mode</div>
    </aside>
    
    <main>
        <div id="chat">
            <div class="msg-wrap">
                <div class="icon ai-icon">✧</div>
                <div class="content">Spark online. System status is green. How can I help?</div>
            </div>
        </div>
        
        <div class="input-box">
            <form class="input-inner" onsubmit="send(event)">
                <textarea id="p" rows="1" placeholder="Type your request..."></textarea>
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
            if(d.error) add('ai', '⚠️ Error: ' + d.error);
            else add('ai', d.reply);
        } catch(err) { t.remove(); add('ai', '⚠️ Connection lost.'); }
    }

    function add(role, text) {
        const c = document.getElementById('chat');
        const w = document.createElement('div');
        w.className = 'msg-wrap';
        if(role === 'thinking') {
            w.innerHTML = '<div class="icon ai-icon">✧</div><div class="content thinking">Spark is processing...</div>';
        } else {
            w.innerHTML = '<div class="icon '+(role==='user'?'user-icon':'ai-icon')+'">'+(role==='user'?'U':'✧')+'</div>' + 
                          '<div class="content">'+(role==='user'?text:marked.parse(text))+'</div>';
        }
        c.appendChild(w);
        c.scrollTop = c.scrollHeight;
        return w;
    }

    function clearChat() {
        const c = document.getElementById('chat');
        c.innerHTML = '<div class="msg-wrap"><div class="icon ai-icon">✧</div><div class="content">Chat history cleared.</div></div>';
    }

    document.getElementById('p').addEventListener('keydown', function(e) {
        if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
</script>
</body>
</html>
