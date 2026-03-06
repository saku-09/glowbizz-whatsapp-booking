import os
import requests
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

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
        "to": to,
        "type": "text",
        "text": {
            "body": message
        }
    }

    requests.post(GRAPH_URL, headers=headers, json=payload)


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
                "id": btn["id"],
                "title": btn["title"]
            }
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
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

    requests.post(GRAPH_URL, headers=headers, json=payload)


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
        "to": to,
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

    requests.post(GRAPH_URL, headers=headers, json=payload)