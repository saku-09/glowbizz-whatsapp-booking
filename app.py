from flask import Flask, request, jsonify
from services.conversation_service import handle_conversation
from services.whatsapp_service import send_whatsapp_message
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ============================================
# HEALTH CHECK
# ============================================

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "running",
        "message": "WhatsApp Automation Backend Active"
    })


# ============================================
# MANUAL TEST API (POSTMAN)
# ============================================

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON body required"}), 400

        user_id = data.get("user_id")
        message = data.get("message")
        phone = data.get("phone")

        if not user_id or not message or not phone:
            return jsonify({
                "error": "user_id, message, phone required"
            }), 400

        reply = handle_conversation(user_id, message)

        wa_response = None

        if reply and reply.strip() != "":
            wa_response = send_whatsapp_message(phone, reply)

        return jsonify({
            "status": "success",
            "reply": reply,
            "whatsapp_response": wa_response
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================
# WHATSAPP WEBHOOK
# ============================================

@app.route("/webhook", methods=["GET", "POST" , "HEAD"])
def webhook():
    # Handle HEAD request (Render health check)
    if request.method == "HEAD":
     return "", 200

    # ----------------------------------------
    # WEBHOOK VERIFICATION (META)
    # ----------------------------------------

    if request.method == "GET":

        verify_token = os.getenv("VERIFY_TOKEN", "nexsalon_verify_123")

        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        print("🔐 Webhook Verification Request")

        if mode == "subscribe" and token == verify_token:
            print("✅ Webhook verified successfully")
            return challenge, 200
        else:
            print("❌ Webhook verification failed")
            return "Verification failed", 403


    # ----------------------------------------
    # RECEIVE MESSAGE FROM WHATSAPP
    # ----------------------------------------

    if request.method == "POST":

        data = request.get_json()

        print("\n" + "="*60)
        print("🔥 FULL WEBHOOK PAYLOAD:")
        print(data)
        print("="*60 + "\n")

        try:

            if not data or "entry" not in data:
                return "EVENT_RECEIVED", 200

            entry = data["entry"][0]

            if "changes" not in entry:
                return "EVENT_RECEIVED", 200

            change = entry["changes"][0]
            value = change.get("value", {})

            # --------------------------------
            # HANDLE INCOMING MESSAGE
            # --------------------------------

            if "messages" in value:

                msg_obj = value["messages"][0]

                phone = msg_obj.get("from")

                message_type = msg_obj.get("type")

                if message_type == "text":

                    message = msg_obj["text"]["body"]

                    print(f"📩 Incoming message: {message}")
                    print(f"📞 From: {phone}")

                    # ----------------------------
                    # PROCESS CONVERSATION
                    # ----------------------------

                    reply = handle_conversation(phone, message)

                    print(f"🤖 Bot Reply: {reply}")

                    # ----------------------------
                    # SEND WHATSAPP MESSAGE
                    # ----------------------------

                    if reply and reply.strip() != "":
                        print("📤 Sending WhatsApp reply...")
                        send_whatsapp_message(phone, reply)

                else:
                    print(f"ℹ️ Unsupported message type: {message_type}")


            # --------------------------------
            # DELIVERY / READ STATUS
            # --------------------------------

            elif "statuses" in value:

                print("ℹ️ Status update received")

        except Exception as e:

            print("❌ Webhook error:", str(e))

        return "EVENT_RECEIVED", 200


# ============================================
# RUN SERVER
# ============================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )