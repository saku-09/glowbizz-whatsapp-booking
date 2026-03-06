from data.store import SESSIONS
from datetime import datetime, timedelta

from services.booking_service import (
    find_salons_by_city,
    find_services_by_salon,
    find_employees_by_salon
)

from services.firebase_service import (
    save_whatsapp_booking,
    get_salon_timings,
    get_booked_slots_from_salon_node,
    cancel_appointment_and_cleanup,
    find_latest_active_booking_by_customer,
    find_owner_uid_by_salon
)

from services.whatsapp_service import (
    send_whatsapp_buttons,
    send_whatsapp_list,
    send_whatsapp_message
)


# ==================================================
# SLOT GENERATOR
# ==================================================

def generate_slots_by_duration(open_time, close_time, duration):

    slots = []

    start = datetime.strptime(open_time, "%H:%M")
    end = datetime.strptime(close_time, "%H:%M")

    current = start

    while current + timedelta(minutes=duration) <= end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=duration)

    return slots


# ==================================================
# CALENDAR DATE PICKER
# ==================================================

def generate_calendar_dates():

    today = datetime.now()

    rows = []

    for i in range(7):

        d = today + timedelta(days=i)

        rows.append({
            "id": d.strftime("%d-%m-%Y"),
            "title": d.strftime("%A"),
            "description": d.strftime("%d %B %Y")
        })

    return rows


# ==================================================
# MAIN CONVERSATION HANDLER
# ==================================================

def handle_conversation(user_id, message):

    session = SESSIONS.get(user_id, {"state": "START", "data": {}})

    state = session["state"]
    data = session["data"]

    msg = message.strip()
    msg_upper = msg.upper()
    msg_lower = msg.lower()
    print("MESSAGE RECEIVED:", msg)

    print("DEBUG:", user_id, state, msg)


# ==================================================
# START MENU
# ==================================================

    if state == "START":

        session["state"] = "MAIN_MENU"
        SESSIONS[user_id] = session

        send_whatsapp_buttons(
            user_id,
            "✨ *Welcome to NexSalon* ✨\n\nYour personal salon booking assistant 💇‍♀️",
            [
                {"id": "BOOK", "title": "Book Appointment"},
                {"id": "CANCEL", "title": "Cancel Appointment"}
            ]
        )

        return ""


# ==================================================
# MAIN MENU
# ==================================================

    if state == "MAIN_MENU":

        if msg_upper in ["BOOK", "BOOK APPOINTMENT"]:

            session["state"] = "CITY"
            SESSIONS[user_id] = session

            return "📍 Please enter your City"

        elif msg_upper in ["CANCEL", "CANCEL APPOINTMENT"]:

            session["state"] = "CANCEL_PHONE"
            SESSIONS[user_id] = session

            return "Please enter your registered phone number"

        else:
            return "Please select a valid option."


# ==================================================
# CITY
# ==================================================

    if state == "CITY":

        data["city"] = msg

        salons = find_salons_by_city(msg_lower)
        
        print("CITY ENTERED:", msg_lower)
        print("SALONS FROM FIREBASE:", salons)

        if not salons:
            return "❌ No salons found in this city."

        data["salons"] = salons

        session["state"] = "SELECT_SALON"
        SESSIONS[user_id] = session

        rows = []

        for salon in salons:

            rows.append({
                "id": salon["id"],
                "title": salon["name"],
                "description": salon["address"]
            })

        send_whatsapp_list(
            user_id,
            "💇 Select a Salon",
            rows
        )

        return ""


# ==================================================
# SALON SELECT
# ==================================================

    if state == "SELECT_SALON":

        salon = None

        for s in data["salons"]:
            if str(s["id"]).upper() == msg_upper:
                salon = s
                break

        if not salon:
            return "Invalid salon."

        data["salon"] = salon

        services = find_services_by_salon(salon["id"])

        data["services"] = services

        session["state"] = "SELECT_SERVICE"
        SESSIONS[user_id] = session

        rows = []

        for s in services:

            rows.append({
                "id": s["serviceId"],
                "title": s["serviceName"],
                "description": f"₹{s['price']} | {s['duration']} min"
            })

        send_whatsapp_list(
            user_id,
            "Select Service",
            rows
        )

        return ""


# ==================================================
# SERVICE SELECT
# ==================================================

    if state == "SELECT_SERVICE":

        service = None

        for s in data["services"]:
            if str(s["serviceId"]) == msg:
                service = s
                break

        if not service:
            return "Invalid service."

        data["service"] = service

        session["state"] = "SELECT_DATE"
        SESSIONS[user_id] = session

        rows = generate_calendar_dates()

        send_whatsapp_list(
            user_id,
            "📅 Select Appointment Date",
            rows
        )

        return ""


# ==================================================
# DATE SELECT
# ==================================================

    if state == "SELECT_DATE":

        data["date"] = msg

        salon = data["salon"]
        service = data["service"]

        dt = datetime.strptime(msg, "%d-%m-%Y")

        day_name = dt.strftime("%A").lower()

        timings = get_salon_timings(salon["id"], day_name)

        if not timings or not timings.get("isOpen"):
            return "Salon is closed that day."

        slots = generate_slots_by_duration(
            timings["open"],
            timings["close"],
            int(service["duration"])
        )

        booked = get_booked_slots_from_salon_node(
            salon["id"],
            msg
        )

        blocked = set(b["startTime"] for b in booked)

        free_slots = [s for s in slots if s not in blocked]

        if not free_slots:
            return "No slots available."

        data["generated_slots"] = free_slots

        session["state"] = "SELECT_SLOT"
        SESSIONS[user_id] = session

        rows = []

        for slot in free_slots:
            rows.append({
                "id": slot,
                "title": slot
            })

        send_whatsapp_list(
            user_id,
            "⏰ Select Time Slot",
            rows
        )

        return ""


# ==================================================
# SLOT SELECT
# ==================================================

    if state == "SELECT_SLOT":

        data["time"] = msg

        session["state"] = "NAME"
        SESSIONS[user_id] = session

        return "Please enter your Name"


# ==================================================
# NAME
# ==================================================

    if state == "NAME":

        data["name"] = msg

        session["state"] = "GENDER"
        SESSIONS[user_id] = session

        return "Select Gender:\n1️⃣ Male\n2️⃣ Female\n3️⃣ Other"


# ==================================================
# GENDER
# ==================================================

    if state == "GENDER":

        gender_map = {"1": "Male", "2": "Female", "3": "Other"}

        if msg not in gender_map:
            return "Please select 1,2 or 3."

        data["gender"] = gender_map[msg]

        session["state"] = "AGE"
        SESSIONS[user_id] = session

        return "Enter your Age"


# ==================================================
# AGE
# ==================================================

    if state == "AGE":

        try:

            age = int(msg)

            if age < 1 or age > 120:
                return "Enter valid age."

            data["age"] = age

            session["state"] = "PHONE"
            SESSIONS[user_id] = session

            return "Enter Phone Number"

        except:
            return "Enter valid age."


# ==================================================
# PHONE
# ==================================================

    if state == "PHONE":

        if not msg.isdigit() or len(msg) != 10:
            return "Enter valid 10 digit phone."

        data["phone"] = msg

        salon = data["salon"]
        service = data["service"]

        summary = (
            f"📋 *Appointment Summary*\n\n"
            f"Name: {data['name']}\n"
            f"Phone: {data['phone']}\n"
            f"Gender: {data['gender']}\n"
            f"Age: {data['age']}\n\n"
            f"Salon: {salon['name']}\n"
            f"Service: {service['serviceName']}\n"
            f"Date: {data['date']}\n"
            f"Time: {data['time']}"
        )

        session["state"] = "CONFIRM"
        SESSIONS[user_id] = session

        send_whatsapp_buttons(
            user_id,
            summary,
            [
                {"id": "CONFIRM", "title": "Confirm"},
                {"id": "CANCEL_BOOKING", "title": "Cancel"}
            ]
        )

        return ""


# ==================================================
# CONFIRM BOOKING
# ==================================================

    if state == "CONFIRM":

        if msg in ["CONFIRM", "CONFIRM BOOKING"]:

            salon = data["salon"]
            service = data["service"]

            employees = find_employees_by_salon(salon["id"])

            employee = employees[0]

            owner_uid = find_owner_uid_by_salon(salon["id"])

            booking = {

                "customer": {
                    "name": data["name"],
                    "phone": data["phone"],
                    "gender": data["gender"],
                    "age": data["age"]
                },

                "placeId": salon["id"],
                "employeeId": employee["employeeId"],
                "services": [service],
                "date": data["date"],
                "startTime": data["time"],
                "status": "confirmed",
                "ownerUid": owner_uid
            }

            save_whatsapp_booking(salon["id"], booking)

            SESSIONS.pop(user_id, None)

            return "🎉 Appointment confirmed! Thank you for choosing NexSalon."

        else:

            SESSIONS.pop(user_id, None)

            return "Booking cancelled."


# ==================================================
# CANCEL FLOW
# ==================================================

    if state == "CANCEL_PHONE":

        data["cancel_phone"] = msg

        session["state"] = "CANCEL_NAME"
        SESSIONS[user_id] = session

        return "Enter booking name"


    if state == "CANCEL_NAME":

        result = find_latest_active_booking_by_customer(
            phone=data["cancel_phone"],
            name=msg
        )

        if not result:
            return "No booking found."

        cancel_appointment_and_cleanup(
            salon_id=result["salonId"],
            appointment_id=result["appointmentId"],
            date=result["date"]
        )

        SESSIONS.pop(user_id, None)

        return "✅ Appointment cancelled."


# ==================================================
# FALLBACK
# ==================================================

    return "Type HI to start."