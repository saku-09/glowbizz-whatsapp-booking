# services/notification_service.py

# =====================================================
# 🔔 BUILD CONFIRMATION MESSAGE
# =====================================================

def build_appointment_message(booking: dict):
    """
    Builds WhatsApp notification message for NEW APPOINTMENT confirmation
    Sent to owner & employee
    """

    customer = booking.get("customer", {})
    services = booking.get("services", [])

    customer_name = customer.get("name", "N/A")
    phone = customer.get("phone", "N/A")
    email = customer.get("email", "N/A")
    age = customer.get("age", "N/A")

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
        f"📧 Email: {email}\n"
        f"🎂 Age: {age}\n\n"
        f"🏬 Salon: {salon_name}\n"
        f"📍 Branch: {branch}\n"
        f"👨‍💼 Staff: {employee_name}\n"
        f"💆 Service: {service_name}\n"
        f"📅 Date: {date}\n"
        f"⏰ Time: {slot_time}\n\n"
        "Please prepare for the appointment.\n"
        "— Glowbizz System"
    )

    return message


# =====================================================
# ❌ BUILD CANCELLATION MESSAGE
# =====================================================

def build_cancel_message(cancel_data: dict):
    """
    Builds WhatsApp notification message for APPOINTMENT CANCELLATION
    Sent to owner & employee
    """

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
        "— Glowbizz System"
    )

    return message
