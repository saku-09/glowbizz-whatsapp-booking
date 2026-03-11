# services/notification_service.py

from services.firebase_service import get_owner_phone, get_appointments_for_reminder
from services.whatsapp_service import send_whatsapp_message, send_whatsapp_template
from firebase_admin import db

import time
import threading



# =====================================================
# 🔔 BUILD CONFIRMATION MESSAGE
# =====================================================

def build_appointment_message(booking: dict):
    """
    Build message for new appointment
    """

    customer = booking.get("customer", {})
    services = booking.get("services", [])

    customer_name = customer.get("name", "N/A")
    phone = customer.get("phone", "N/A")
    age = customer.get("age", "N/A")
    gender = customer.get("gender", "N/A")

    salon_name = booking.get("salonName", "N/A")
    branch = booking.get("branch", "N/A")
    employee_name = booking.get("employeeName", "N/A")

    service_name = services[0].get("serviceName", "N/A") if services else "N/A"

    slot_time = booking.get("startTime", "N/A")
    date = booking.get("date", "N/A")

    message = (
        "📢 *New Appointment Confirmed*\n\n"
        f"👤 Customer: {customer_name}\n"
        f"📞 Phone: {phone}\n"
        f"⚧ Gender: {gender}\n"
        f"🎂 Age: {age}\n\n"
        f"🏬 Salon: {salon_name}\n"
        f"📍 Branch: {branch}\n"
        f"👨‍💼 Staff: {employee_name}\n"
        f"💆 Service: {service_name}\n"
        f"📅 Date: {date}\n"
        f"⏰ Time: {slot_time}\n\n"
        "Please prepare for the appointment.\n"
        "— NexSalon System"
    )

    return message


# =====================================================
# ❌ BUILD CANCEL MESSAGE
# =====================================================

def build_cancel_message(cancel_data: dict):

    customer_name = cancel_data.get("customerName", "N/A")
    phone = cancel_data.get("customerPhone", "N/A")

    salon_name = cancel_data.get("salonName", "N/A")
    service_name = cancel_data.get("serviceName", "N/A")

    date = cancel_data.get("date", "N/A")
    slot_time = cancel_data.get("startTime", "N/A")

    message = (
        "❌ *Appointment Cancelled*\n\n"
        f"👤 Customer: {customer_name}\n"
        f"📞 Phone: {phone}\n\n"
        f"🏬 Salon: {salon_name}\n"
        f"💆 Service: {service_name}\n"
        f"📅 Date: {date}\n"
        f"⏰ Time: {slot_time}\n\n"
        "This appointment has been cancelled by the customer.\n"
        "— NexSalon System"
    )

    return message


# =====================================================
# 📲 SEND OWNER NOTIFICATION
# =====================================================

def notify_owner_new_booking(booking: dict):
    """
    Send booking notification to salon owner
    """

    owner_uid = booking.get("ownerUid")

    if not owner_uid:
        print("⚠️ ownerUid missing in booking")
        return

    owner_phone = get_owner_phone(owner_uid)

    if not owner_phone:
        print("⚠️ Owner phone not found")
        return

    message = build_appointment_message(booking)

    send_whatsapp_message(owner_phone, message)

    print("📲 Owner notified about new booking")


# =====================================================
# 📲 SEND OWNER CANCEL NOTIFICATION
# =====================================================

def notify_owner_cancel(cancel_data: dict, owner_uid: str):

    owner_phone = get_owner_phone(owner_uid)

    if not owner_phone:
        print("⚠️ Owner phone not found")
        return

    message = build_cancel_message(cancel_data)

    send_whatsapp_message(owner_phone, message)

    print("📲 Owner notified about cancellation")
 # ============================================
# SEND CUSTOMER REMINDER
# ============================================

def notify_customers_for_reminders():

    appointments = get_appointments_for_reminder()

    for appt in appointments:

        booking = appt["booking"]

        customer = booking.get("customer", {})
        phone = str(customer.get("phone", "")).strip()

        # remove + if user stored it
        phone = phone.replace("+", "")

        # add India country code if missing
        if not phone.startswith("91"):
            phone = "91" + phone

        print("📞 Sending reminder to:", phone)
        if len(phone) != 12:
            print("❌ Invalid phone number:", phone)
            continue

        customer_name = customer.get("name") or "Customer"
        salon_name = booking.get("salonName") or "Salon"
        
        services = booking.get("services") or []
        
        # Concatenate all service names
        service_names = [s.get("serviceName") or s.get("name") or "Service" for s in services]
        service_text = ", ".join(service_names) if service_names else "Service"
        
        # Calculate total price correctly
        total_price = 0
        for s in services:
            try:
                price_val = s.get("price")
                if price_val is not None:
                    total_price += int(price_val)
            except (ValueError, TypeError):
                continue

        staff_name = booking.get("employeeName") or "Staff"
        date = booking.get("date") or "Scheduled Date"
        time = booking.get("startTime") or "Scheduled Time"

        print("📋 Reminder Data:")
        print("Customer:", customer_name)
        print("Salon:", salon_name)
        print("Services:", service_text)
        print("Staff:", staff_name)
        print("Total Price:", total_price)
        print("Date:", date)
        print("Time:", time)

        success = send_whatsapp_template(
            phone,
            customer_name,
            salon_name,
            service_text,
            staff_name,
            total_price,
            date,
            time
        )
        if success:

            db.reference(
                f"salonandspa/appointments/{appt['collection']}/{appt['salonId']}/{appt['appointmentId']}"
            ).update({
                "reminderSent": True
            })

            print("✅ Reminder sent:", phone)  
        else:
            print("❌ Reminder failed:", phone) 
# =====================================================
# 🔁 REMINDER LOOP
# =====================================================


def reminder_loop():

    while True:

        try:
            notify_customers_for_reminders()
        except Exception as e:
            print("❌ Reminder loop error:", e)

        time.sleep(600)  # run every 10 minutes

print("🚀 Reminder service initialized")
# Start reminder thread automatically
threading.Thread(target=reminder_loop, daemon=True).start()           