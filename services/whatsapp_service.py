# services/whatsapp_service.py

import time

try:
    import pywhatkit
    PYWHATKIT_AVAILABLE = True
    print("✅ pywhatkit loaded successfully")
except Exception as e:
    print("⚠️ pywhatkit not available, WhatsApp disabled:", e)
    PYWHATKIT_AVAILABLE = False


def format_phone(phone: str):
    """
    Convert '9619901999' -> '919619901999'
    """
    phone = phone.strip()
    if phone.startswith("91"):
        return phone
    return "91" + phone


def send_whatsapp_message(phone: str, message: str):
    # If pywhatkit not usable, don't crash the app
    if not PYWHATKIT_AVAILABLE:
        print("⚠️ WhatsApp sending skipped (no internet / pywhatkit error)")
        print("📨 Message was:\n", message)
        return

    try:
        phone = format_phone(phone)

        pywhatkit.sendwhatmsg_instantly(
            phone_no=f"+{phone}",
            message=message,
            wait_time=10,
            tab_close=True
        )

        time.sleep(5)
        print(f"WhatsApp sent to {phone}")

    except Exception as e:
        print("❌ WhatsApp Error:", e)
