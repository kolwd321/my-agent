import os, re, io, json
from flask import Flask, request, jsonify, send_file
from google import genai
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Setup Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

BASE_SYSTEM = (
    "You are a premium, enterprise-grade AI Assistant. "
    "Use professional formatting, bolding, and clear headings."
)

@app.route("/")
def index():
    return HTML

@app.route("/chat", methods=["POST"])
def chat():
    try:
        d = request.get_json()
        msg = d.get("message", "").strip()
        # Try confirmed stable models
        for name in ["gemini-1.5-flash-latest", "gemini-flash-latest", "gemini-1.5-flash"]:
            try:
                response = client.models.generate_content(
                    model=name, 
                    config={'system_instruction': BASE_SYSTEM}, 
                    contents=msg
                )
                return jsonify({"reply": response.text})
            except: continue
        return jsonify({"error": "Service connection failed."}), 500
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
        try {
            const r = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: m})
            });
            const d = await r.json();
            if(d.error) alert(d.error);
            else add('assistant', d.reply);
        } catch(err) { alert('Connection failed.'); }
    }
    function add(role, text) {
        const c = document.getElementById('chat');
        const w = document.createElement('div');
        w.className = 'msg-wrap';
        
        let body = (role === 'assistant') ? marked.parse(text) : text;
        let btn = (role === 'assistant') ? '<button class="copy-btn" onclick="copy(this)">Copy Text</button>' : '';
        
        w.innerHTML = '<div class="icon ' + (role==='user'?'user-icon':'ai-icon') + '">' + (role==='user'?'U':'✧') + '</div>' +
                      '<div class="content">' + body + btn + '</div>';
        
        // Hidden text storage for the copy button
        if(role === 'assistant') w.dataset.raw = text;

        c.appendChild(w);
        c.scrollTop = c.scrollHeight;
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
    app.run(debug=True)
