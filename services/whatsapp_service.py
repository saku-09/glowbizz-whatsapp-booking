import os
import requests
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
    raise ValueError("Missing required environment variables: WHATSAPP_TOKEN and PHONE_NUMBER_ID")


def format_phone_number(phone: str) -> str:
    """
    Format phone number for WhatsApp API.
    Removes spaces, dashes, and ensures it has country code.
    Example: '+91 98765 43210' -> '919876543210'
    """
    # Remove spaces, dashes, parentheses
    cleaned = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # Remove leading + if present
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    
    return cleaned


def send_whatsapp_message(to_number, message):
    if not to_number or not message:
        return {
            "success": False,
            "error": "Missing phone number or message"
        }
    
    # Format phone number
    formatted_number = format_phone_number(to_number)
    
    print(f"📱 Sending WhatsApp to: {formatted_number}")
    print(f"💬 Message: {message}")

    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "to": formatted_number,
        "type": "text",
        "text": {
            "body": message
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response_data = response.json()
        
        print(f"✅ WhatsApp API Response: {response_data}")
        
        # Check if the request was successful
        if response.status_code == 200:
            return {
                "success": True,
                "message_id": response_data.get("messages", [{}])[0].get("id"),
                "response": response_data
            }
        else:
            error_msg = response_data.get("error", {}).get("message", "Unknown error")
            print(f"❌ WhatsApp Error: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "response": response_data
            }
    
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timeout"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}