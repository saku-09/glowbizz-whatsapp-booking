# app.py

from flask import Flask, request, jsonify
from services.conversation_service import handle_conversation

app = Flask(__name__)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_id = data.get("user_id")
    message = data.get("message")

    if not user_id or not message:
        return jsonify({"error": "user_id and message required"}), 400

    reply = handle_conversation(user_id, message)

    return jsonify({
        "user_id": user_id,
        "reply": reply
    })

@app.route("/", methods=["GET"])
def health():
    return "Glowbizz Bot Running ✅"

if __name__ == "__main__":
    app.run(debug=True, port=5000)
