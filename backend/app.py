# app.py — MailMan.ai Flask backend
# Run with: python app.py
# Requires: pip install flask flask-cors

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Brave blocks cross-origin requests to localhost from extensions UNLESS the
# server explicitly allows the extension origin. We allow all origins here
# since this server only runs locally and is not exposed to the internet.
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": ["Content-Type"],
    "methods": ["GET", "POST", "OPTIONS"]
}})

# Handle preflight OPTIONS requests explicitly (belt-and-suspenders for Brave)
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# ─── Health check ─────────────────────────────────────────────────────────────
@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok"})


# ─── Stats ────────────────────────────────────────────────────────────────────
@app.route("/stats", methods=["GET"])
def stats():
    # TODO: replace with real Gmail API / DB query
    return jsonify({
        "total":         70,
        "high_priority": 5,
        "spam":          3,
        "subscriptions": 12,
        "work":          20,
        "travel":        4,
        "otp":           6
    })


# ─── OTPs ─────────────────────────────────────────────────────────────────────
@app.route("/otps", methods=["GET"])
def otps():
    # TODO: replace with real OTP extraction logic
    return jsonify({
        "otps": [
            {
                "service": "Google",
                "code":    "482910",
                "expires": "10 mins",
                "emailId": "msg_001"
            },
            {
                "service": "GitHub",
                "code":    "739204",
                "expires": "5 mins",
                "emailId": "msg_002"
            }
        ]
    })


# ─── Analyze email ────────────────────────────────────────────────────────────
@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    data = request.get_json(silent=True) or {}
    # TODO: replace with real ML/LLM classification
    return jsonify({
        "category":       "work",
        "priority":       2,
        "is_spam":        False,
        "is_phishing":    False,
        "is_subscription":False
    })


# ─── Summarize email ──────────────────────────────────────────────────────────
@app.route("/summarize", methods=["POST", "OPTIONS"])
def summarize():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    data = request.get_json(silent=True) or {}
    subject = data.get("subject", "")
    body    = data.get("body",    data.get("snippet", ""))

    # TODO: replace stub with real LLM call (OpenAI, Gemini, local model, etc.)
    summary = f"This email is about: \"{subject}\". " \
              f"Body preview: {body[:200]}..." if body else \
              f"Subject: {subject}. No body content available."

    return jsonify({"summary": summary})


# ─── Delete email ─────────────────────────────────────────────────────────────
@app.route("/delete_email", methods=["POST", "OPTIONS"])
def delete_email():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    data     = request.get_json(silent=True) or {}
    email_id = data.get("id", "")
    # TODO: call Gmail API to trash the email by ID
    print(f"[MailMan.ai] Delete requested for email ID: {email_id}")
    return jsonify({"success": True})


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Bind to 127.0.0.1 explicitly — Brave allows loopback on this address.
    # Do NOT use 0.0.0.0 as it exposes the server on your network.
    print("[MailMan.ai] Backend running at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)