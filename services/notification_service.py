# services/notification_service.py

def build_appointment_message(data: dict):
    """
    Builds WhatsApp notification message for owner & employee
    """

    customer_name = data.get("customer_name", "N/A")
    age = data.get("age", "N/A")
    phone = data.get("customer_phone", "N/A")
    email = data.get("email", "N/A")

    salon_name = data.get("salon_name", "N/A")
    branch = data.get("branch", "N/A")
    employee_name = data.get("employee_name", "N/A")
    service_name = data.get("service_name", "N/A")
    slot_time = data.get("slot_time", "N/A")
    date = data.get("date", "N/A")

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
