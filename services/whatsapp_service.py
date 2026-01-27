# services/whatsapp_service.py

import time

try:
    import pywhatkit
    PYWHATKIT_AVAILABLE = True
    print("✅ pywhatkit loaded successfully")
except Exception as e:
    print("⚠️ pywhatkit not available, WhatsApp disabled:", e)
    PYWHATKIT_AVAILABLE = False


def format_phone(phone):
    """
    Accepts int or str.
    Converts:
      9619901999  -> 919619901999
      "9619901999" -> 919619901999
      "919619901999" -> 919619901999
    """

    # 🔥 ALWAYS convert to string first
    phone = str(phone).strip()

    # Remove any spaces or +
    phone = phone.replace(" ", "").replace("+", "")

    # Add country code if missing
    if not phone.startswith("91"):
        phone = "91" + phone

    return phone


def send_whatsapp_message(phone, message):
    # If pywhatkit not usable, don't crash the app
    if not PYWHATKIT_AVAILABLE:
        print("⚠️ WhatsApp sending skipped (pywhatkit not available)")
        print("📨 Message was:\n", message)
        return

    try:
        # 🔥 Safe formatting
        phone = format_phone(phone)

        print("📤 Sending WhatsApp to:", phone)

        pywhatkit.sendwhatmsg_instantly(
            phone_no=f"+{phone}",
            message=message,
            wait_time=10,
            tab_close=True
        )

        time.sleep(5)
        print(f"WhatsApp sent successfully to +{phone}")

    except Exception as e:
        print("❌ WhatsApp Error:", e)
