from flask import Flask, request, jsonify
from services.conversation_service import handle_conversation
from services.whatsapp_service import send_whatsapp_message
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "running",
        "message": "WhatsApp Automation Backend Active"
    })


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
                "error": "user_id, message, and phone are required"
            }), 400

        reply = handle_conversation(user_id, message)
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


# ✅ WEBHOOK MUST BE ABOVE app.run()
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        verify_token = os.getenv("VERIFY_TOKEN", "nexsalon_verify_123")
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        print(f"🔐 Webhook Verification - Mode: {mode}, Token Match: {token == verify_token}")

        if mode == "subscribe" and token == verify_token:
            print("✅ Webhook verified successfully!")
            return challenge, 200
        else:
            print("❌ Verification failed - Token mismatch")
            return "Verification failed", 403

    if request.method == "POST":
        data = request.get_json()
        print("\n" + "="*60)
        print("🔥 FULL WEBHOOK PAYLOAD:", data)
        print("="*60 + "\n")

        try:
            # Validate basic structure
            if not data or "entry" not in data:
                print("⚠️  No 'entry' in webhook data")
                return "EVENT_RECEIVED", 200

            entry = data["entry"][0]
            if "changes" not in entry:
                print("⚠️  No 'changes' in entry")
                return "EVENT_RECEIVED", 200

            changes = entry["changes"][0]
            value = changes.get("value", {})

            # Check if this is a message event (not delivery/read status)
            if "messages" in value and len(value["messages"]) > 0:
                msg_obj = value["messages"][0]
                
                # Extract message details safely
                phone = msg_obj.get("from")
                message_type = msg_obj.get("type", "text")
                
                if message_type == "text":
                    text_obj = msg_obj.get("text", {})
                    message = text_obj.get("body", "")
                    
                    if phone and message:
                        print(f"📩 Incoming message: '{message}'")
                        print(f"📞 From: {phone}")
                        print(f"⏰ Timestamp: {msg_obj.get('timestamp')}")

                        # Process and reply
                        reply = handle_conversation(phone, message)
                        print(f"🤖 Reply: {reply}\n")

                        send_whatsapp_message(phone, reply)
                    else:
                        print("⚠️  Missing phone or message body")
                else:
                    print(f"ℹ️  Message type '{message_type}' not handled")
                    
            elif "statuses" in value:
                # This is a delivery/read status update, not a message
                print("ℹ️  Status update received (delivery/read receipt)")
                
            else:
                print("⚠️  No messages or statuses in webhook")

        except Exception as e:
            print(f"❌ Webhook error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        return "EVENT_RECEIVED", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)