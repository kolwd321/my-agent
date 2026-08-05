import os, json, html as htmlmod
from flask import Flask, request, jsonify
from google import genai
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Setup Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Professional system prompt for that "Claude" feel
BASE_SYSTEM = (
    "You are a premium, enterprise-grade AI Assistant named Spark.\n"
    "Personality: Helpful, precise, calm, and professional. Never sycophantic.\n\n"
    "Rules:\n"
    "1. Answer accurately. If you don't know, SAY SO instead of guessing.\n"
    "2. Use Markdown: bold key terms, headings, and bullet lists for structure.\n"
    "3. For complex tasks, think step by step and show your reasoning briefly.\n"
    "4. If a request is vague or ambiguous, ASK ONE clarifying question.\n"
    "5. Keep tone professional but warm. No emojis unless asked.\n"
    "6. Respect boundaries: never provide harmful, unethical, or illegal content.\n"
)

# Conversation history (Memory)
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

        # Add user message to history
        HISTORY.append({"role": "user", "parts": [msg]})

        # Generate response using full history
        response = client.models.generate_content(
            model=MODEL,
            config={"system_instruction": BASE_SYSTEM},
            contents=HISTORY,
        )
        
        reply = response.text
        
        # Add assistant reply to history
        HISTORY.append({"role": "model", "parts": [reply]})

        # Keep history manageable (last 40 messages)
        if len(HISTORY) > 40:
            HISTORY[:] = HISTORY[-40:]

        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

HTML = """<!DOCTYPE html>
<html
