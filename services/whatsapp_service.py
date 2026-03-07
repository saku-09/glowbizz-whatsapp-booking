import os
import requests
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
    raise Exception("Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID in environment variables")

GRAPH_URL = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"


# =====================================================
# SEND TEXT MESSAGE
# =====================================================

def send_whatsapp_message(to, message):

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to),
        "type": "text",
        "text": {
            "body": message
        }
    }

    try:

        response = requests.post(GRAPH_URL, headers=headers, json=payload)

        print("📤 Sending text message")
        print("Status:", response.status_code)
        print("Response:", response.text)

        return response.json()

    except Exception as e:

        print("❌ WhatsApp Text Send Error:", str(e))
        return None


# =====================================================
# SEND BUTTON MESSAGE
# =====================================================

def send_whatsapp_buttons(to, body_text, buttons):

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    button_list = []

    for btn in buttons:

        button_list.append({
            "type": "reply",
            "reply": {
                "id": str(btn["id"]),
                "title": btn["title"]
            }
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": body_text
            },
            "action": {
                "buttons": button_list
            }
        }
    }

    try:

        response = requests.post(GRAPH_URL, headers=headers, json=payload)

        print("📤 Sending button message")
        print("Status:", response.status_code)
        print("Response:", response.text)

        return response.json()

    except Exception as e:

        print("❌ WhatsApp Button Send Error:", str(e))
        return None


# =====================================================
# SEND LIST MESSAGE
# =====================================================

def send_whatsapp_list(to, body_text, rows):

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to),
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": body_text
            },
            "action": {
                "button": "Select",
                "sections": [
                    {
                        "title": "Options",
                        "rows": rows
                    }
                ]
            }
        }
    }

    try:

        response = requests.post(GRAPH_URL, headers=headers, json=payload)

        print("📤 Sending list message")
        print("Status:", response.status_code)
        print("Response:", response.text)

        if response.status_code != 200:
            print("❌ WhatsApp List API Error:", response.status_code, response.text)
            return None

        return response.json()

    except Exception as e:

        print("❌ WhatsApp List Send Error:", str(e))
        return None