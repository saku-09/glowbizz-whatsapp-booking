from flask import Flask, request, jsonify, render_template
from services.conversation_service import handle_conversation

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_id = data.get("user_id")
    message = data.get("message")

    reply = handle_conversation(user_id, message)

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(debug=True)
