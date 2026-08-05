import os
from flask import Flask, request, jsonify
from google import genai
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Setup Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# UPGRADED: The Executive System Prompt
# This tells the AI exactly how to behave like a pro (no fluff, high logic)
BASE_SYSTEM = (
    "You are Spark, an Elite Executive AI Assistant. "
    "Your tone is professional, precise, and sophisticated. "
    "Rules: 1. Use structured Markdown (headers, bolding, tables) for clarity. "
    "2. If a request is complex, break it into logical steps. "
    "3. Never use emojis unless specifically asked. "
    "4. Be concise; avoid filler words like 'Okay' or 'I understand.' "
    "5. Provide high-value insights in every response."
)

@app.route("/")
def index():
    return HTML

@app.route("/chat", methods=["POST"])
def chat():
    try:
        d = request.get_json()
        msg = d.get("message", "").strip()
        
        # STABLE CORE: We are NOT touching this loop because it works!
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
        
        return jsonify({"error": "Spark is currently handling high volume. Please try again."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spark | Enterprise AI</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root { 
            --bg: #0b0f1a; 
            --sidebar: #161b2a; 
            --brand: #38bdf8; 
            --text: #f1f5f9; 
            --border: #2d3748; 
        }
        
        body { font-family: 'Inter', -apple-system, sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: var(--text); }
        
        /* SLEEK SIDEBAR */
        aside { width: 260px; background: var(--sidebar); border-right: 1px solid var(--border); padding: 30px 20px; display: flex; flex-direction: column; gap: 15px; }
        .logo { font-size: 22px; font-weight: 800; letter-spacing: -1px; color: var(--brand); margin-bottom: 20px; }
        
        main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        
        /* CHAT AREA */
        #chat { flex: 1; overflow-y: auto; padding: 40px 10px; scroll-behavior: smooth; }
        .msg-wrap { max-width: 750px; margin: 0 auto 40px auto; display: flex; gap: 20px; animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        
        .icon { width: 35px; height: 35px; border-radius: 10px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-weight: bold; background: var(--brand); color: #0b0f1a; font-size: 18px; }
        .user-icon { background: #475569; color: white; }
        
        .content { font-size: 16px; line-height: 1.7; flex: 1; color: #e2e8f0; }
        .content h1, .content h2 { color: var(--brand); margin-top: 0; }
        .content pre { background: #000; padding: 20px; border-radius: 12px; border: 1px solid var(--border); overflow-x: auto; font-family: 'Fira Code', monospace; }
        
        /* AUTO-EXPANDING INPUT */
        .input-container { padding: 30px; background: linear-gradient(transparent, var(--bg) 20%); }
        .input-inner { max-width: 750px; margin: 0 auto; position: relative; background: var(--sidebar); border: 1px solid var(--border); border-radius: 16px; padding: 10px; transition: border-color 0.2s; }
        .input-inner:focus-within { border-color: var(--brand); }
        
        textarea { 
            width: 100%; border: none; background: transparent; color: white; padding: 10px 45px 10px 10px; 
            font-size: 16px; resize: none; outline: none; font-family: inherit; max-height: 200px;
        }

        .side-btn { background: #1e293b; color: #f1f5f9; border: 1px solid var(--border); padding: 12px; border-radius: 10px; cursor: pointer; font-size: 14px; text-align: left; transition: 0.2s; }
        .side-btn:hover { background: #2d3748; border-color: var(--brand); }
        
        .thinking { color: #64748b; font-style: italic; font-size: 14px; display: flex; align-items: center; gap: 8px; }
    </style>
</head>
<body>
    <aside>
        <div class="logo">✧ SPARK</div>
        <button class="side-btn" onclick="location.reload()">+ New Intelligence Session</button>
        <button class="side-btn" onclick="document.getElementById('chat').innerHTML=''">Clear Console</button>
        <div style="margin-top: auto; color: #475569; font-size: 12px;">Secure Enterprise v3.0</div>
    </aside>
    
    <main>
        <div id="chat">
            <div class="msg-wrap">
                <div class="icon">S</div>
                <div class="content">Spark Intelligence Systems online. Welcome. How can I assist your objectives today?</div>
            </div>
        </div>
        
        <div class="input-container">
            <div class="input-inner">
                <textarea id="p" rows="1" placeholder="Enter command or request..." oninput="this.style.height='auto';this.style.height=this.scrollHeight+'px'"></textarea>
            </div>
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
        i.style.height = 'auto'; // Reset height after send
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
        } catch(err) { t.remove(); add('ai', 'System connection timeout.'); }
        document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
    }

    function add(role, text) {
        const c = document.getElementById('chat');
        const w = document.createElement('div');
        w.className = 'msg-wrap';
        if(role === 'thinking') {
            w.innerHTML = '<div class="icon">S</div><div class="content thinking">Spark is processing...</div>';
        } else {
            w.innerHTML = '<div class="icon '+(role==='user'?'user-icon':'')+'">'+(role==='user'?'U':'S')+'</div>' + 
                          '<div class="content">'+(role==='user'?text:marked.parse(text))+'</div>';
        }
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
