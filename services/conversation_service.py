from data.store import SESSIONS

from services.firebase_service import get_employee_by_id
from services.booking_service import (
    find_salons_by_city,
    find_services_by_salon,
    find_employees_by_salon
)

from services.firebase_service import (
    save_owner_lead,
    save_whatsapp_booking,
    is_slot_available,
    get_salon_timings,
    get_booked_slots_from_salon_node,
    get_owner_phone,
    cancel_appointment_and_cleanup,
    find_latest_active_booking_by_customer,
    find_owner_uid_by_salon          # 🔥 FIXED IMPORT
)

from services.notification_service import (
    build_appointment_message,
    build_cancel_message
)

from services.whatsapp_service import send_whatsapp_message
from datetime import datetime, timedelta


# =====================================================
# 🔥 Generate slots by SERVICE DURATION
# =====================================================
def generate_slots_by_duration(open_time: str, close_time: str, service_duration: int):
    slots = []
    start = datetime.strptime(open_time, "%H:%M")
    end = datetime.strptime(close_time, "%H:%M")

    current = start
    while current + timedelta(minutes=service_duration) <= end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=service_duration)

    return slots


# =====================================================
# MAIN CONVERSATION HANDLER
# =====================================================
def handle_conversation(user_id: str, message: str):

    session = SESSIONS.get(user_id, {
        "state": "START",
        "data": {}
    })

    state = session["state"]
    data = session["data"]
    msg = message.strip()

    # 🔍 Debug log
    print("DEBUG:", user_id, "STATE:", state, "MSG:", msg)

    # =====================================================
    # ❌ GLOBAL CANCEL COMMAND
    # =====================================================
    cancel_keywords = ["cancel", "cancelled", "i want to cancel", "stop", "stop booking"]

    if any(word in msg.lower() for word in cancel_keywords):
        session["state"] = "CANCEL_PHONE"
        session["data"] = {}
        SESSIONS[user_id] = session
        return (
            "❌ Sure, I can help you cancel your appointment.\n\n"
            "Please enter your registered mobile number."
        )

    # =====================================================
    # START
    # =====================================================
    if state == "START":
        session["state"] = "ROLE_SELECTION"
        SESSIONS[user_id] = session
        return (
            "Welcome to Glowbizz 👋\n\n"
            "Who are you?\n"
            "1️⃣ Salon Owner – Manage my salon\n"
            "2️⃣ Customer – Book an appointment\n\n"
            "Reply with 1 or 2"
        )

    # =====================================================
    # ROLE SELECTION
    # =====================================================
    if state == "ROLE_SELECTION":
        if msg == "1":
            data["role"] = "OWNER"
            session["state"] = "OWNER_ENTRY"
            SESSIONS[user_id] = session
            return (
                "Welcome, Salon Owner 👋\n"
                "Are you already using Glowbizz?\n"
                "1️⃣ Yes, Login\n"
                "2️⃣ No, I want to register"
            )

        elif msg == "2":
            data["role"] = "CUSTOMER"
            session["state"] = "CUSTOMER_CITY"
            SESSIONS[user_id] = session
            return "Great! Please enter your City (e.g. Mumbai, Navi Mumbai)."

        else:
            return "Please reply with 1 (Owner) or 2 (Customer)."

    # =====================================================
    # 🧑‍💼 OWNER FLOW
    # =====================================================
    if state == "OWNER_ENTRY":
        if msg == "1":
            return "Login feature coming soon. Please register first 🙂"
        elif msg == "2":
            session["state"] = "OWNER_COLLECT_NAME"
            SESSIONS[user_id] = session
            return "Great! Please enter your Salon Name."
        else:
            return "Please reply with 1 or 2."

    if state == "OWNER_COLLECT_NAME":
        data["salon_name"] = msg
        session["state"] = "OWNER_COLLECT_CITY"
        SESSIONS[user_id] = session
        return "Please enter your City."

    if state == "OWNER_COLLECT_CITY":
        data["city"] = msg
        session["state"] = "OWNER_COLLECT_MOBILE"
        SESSIONS[user_id] = session
        return "Please enter your Mobile Number."

    if state == "OWNER_COLLECT_MOBILE":
        data["mobile"] = msg
        session["state"] = "SHOW_PLANS"
        SESSIONS[user_id] = session
        return (
            "🎉 Registration almost complete!\n\n"
            "✨ Glowbizz Plans ✨\n\n"
            "1️⃣ Starter – ₹1,999 / month\n"
            "2️⃣ Professional – ₹9,999 / 6 months\n"
            "3️⃣ Premium – ₹19,999 / yearly\n\n"
            "Reply with 1, 2, or 3 to choose your plan."
        )

    if state == "SHOW_PLANS":
        if msg in ["1", "2", "3"]:
            plan_map = {
                "1": "Starter – ₹1,999",
                "2": "Professional – ₹9,999",
                "3": "Premium – ₹19,999"
            }

            data["plan"] = plan_map[msg]

            lead = {
                "salonName": data["salon_name"],
                "city": data["city"],
                "mobile": data["mobile"],
                "plan": data["plan"]
            }

            save_owner_lead(lead)
            SESSIONS.pop(user_id, None)

            return (
                f"✅ You selected: {data['plan']}\n\n"
                "Our team will contact you shortly for onboarding.\n"
                "Thank you for registering with Glowbizz 💼"
            )
        else:
            return "Please reply with 1, 2, or 3."

    # =====================================================
    # 👩‍💼 CUSTOMER BOOKING FLOW
    # =====================================================
    if state == "CUSTOMER_CITY":
        data["city"] = msg.lower()
        session["state"] = "CUSTOMER_SELECT_SALON"
        SESSIONS[user_id] = session

        salons = find_salons_by_city(data["city"])

        if not salons:
            return (
                f"Sorry 😔 No salons found in {data['city'].title()}.\n\n"
                "Please try another city."
            )

        data["salons"] = salons

        response = "Here are salons near you:\n\n"
        for idx, salon in enumerate(salons, start=1):
            response += f"{idx}️⃣ {salon['name']} - {salon['address']}\n"

        response += "\nReply with the number to select a salon."
        return response

    if state == "CUSTOMER_SELECT_SALON":
        try:
            choice = int(msg) - 1
            salon = data["salons"][choice]

            data["salon"] = salon
            session["state"] = "CUSTOMER_SELECT_SERVICE"
            SESSIONS[user_id] = session

            services = find_services_by_salon(salon["id"])

            if not services:
                return "Sorry 😔 This salon has no active services."

            data["services"] = services

            response = f"Services at {salon['name']}:\n\n"
            for idx, s in enumerate(services, start=1):
                response += f"{idx}️⃣ {s['serviceName']} – ₹{s['price']} ({s['duration']} min)\n"

            response += "\nReply with the number to select a service."
            return response

        except:
            return "Please reply with a valid number."

    if state == "CUSTOMER_SELECT_SERVICE":
        try:
            choice = int(msg) - 1
            service = data["services"][choice]

            data["service"] = service
            session["state"] = "CUSTOMER_DATE"
            SESSIONS[user_id] = session

            return "Please enter appointment date (DD-MM-YYYY)."

        except:
            return "Please reply with a valid number."

    # =====================================================
    # DATE + SLOT
    # =====================================================
    if state == "CUSTOMER_DATE":
        data["date"] = msg

        salon = data["salon"]
        salon_id = salon["id"]
        service = data["service"]

        try:
            dt = datetime.strptime(msg, "%d-%m-%Y")
        except:
            return "⛔ Invalid date format. Please use DD-MM-YYYY."

        day_name = dt.strftime("%A").lower()
        normalized_date = dt.strftime("%d-%m-%Y")

        timings = get_salon_timings(salon_id, day_name)

        if not timings or not timings.get("isOpen"):
            return "Sorry 😔 This salon is closed on this day."

        all_slots = generate_slots_by_duration(
            open_time=timings.get("open"),
            close_time=timings.get("close"),
            service_duration=int(service["duration"])
        )

        booked_slots = get_booked_slots_from_salon_node(
            salon_id=salon_id,
            date=normalized_date
        )

        blocked_times = set(b["startTime"] for b in booked_slots)
        free_slots = [t for t in all_slots if t not in blocked_times]

        if not free_slots:
            return "Sorry 😔 No free slots available on this date."

        data["normalized_date"] = normalized_date
        data["generated_slots"] = free_slots
        session["state"] = "CUSTOMER_SELECT_SLOT"
        SESSIONS[user_id] = session

        response = f"Available time slots on {msg}:\n\n"
        for idx, t in enumerate(free_slots, start=1):
            response += f"{idx}️⃣ {t}\n"

        response += "\nReply with the number to select time."
        return response

    if state == "CUSTOMER_SELECT_SLOT":
        try:
            choice = int(msg) - 1
            data["time"] = data["generated_slots"][choice]
            session["state"] = "CUSTOMER_NAME"
            SESSIONS[user_id] = session
            return "Great 👍\n\nPlease enter your Full Name."
        except:
            return "Please reply with a valid number."

    # =====================================================
    # CUSTOMER DETAILS (WITH GENDER + AGE)
    # =====================================================
    if state == "CUSTOMER_NAME":
        data["customer_name"] = msg
        session["state"] = "CUSTOMER_PHONE"
        SESSIONS[user_id] = session
        return "Please enter your Mobile Number."

    if state == "CUSTOMER_PHONE":
        data["customer_phone"] = msg
        session["state"] = "CUSTOMER_GENDER"
        SESSIONS[user_id] = session
        return "Please select your Gender:\n1️⃣ Male\n2️⃣ Female\n3️⃣ Other"

    if state == "CUSTOMER_GENDER":
        if msg == "1":
            data["customer_gender"] = "male"
        elif msg == "2":
            data["customer_gender"] = "female"
        elif msg == "3":
            data["customer_gender"] = "other"
        else:
            return "Please reply with:\n1️⃣ Male\n2️⃣ Female\n3️⃣ Other"

        session["state"] = "CUSTOMER_AGE"
        SESSIONS[user_id] = session
        return "Please enter your Age (in years)."

    if state == "CUSTOMER_AGE":
        try:
            age = int(msg)
            if age <= 0 or age > 120:
                return "Please enter a valid age."

            data["customer_age"] = age
            session["state"] = "CUSTOMER_EMAIL"
            SESSIONS[user_id] = session
            return "Please enter your Email (or type NA)."
        except:
            return "Please enter a valid numeric age."

    if state == "CUSTOMER_EMAIL":
        data["customer_email"] = "" if msg.lower() == "na" else msg
        session["state"] = "CUSTOMER_CONFIRM"
        SESSIONS[user_id] = session

        salon = data["salon"]
        service = data["service"]

        return (
            "Please confirm your booking:\n\n"
            f"Name: {data['customer_name']}\n"
            f"Phone: {data['customer_phone']}\n"
            f"Gender: {data.get('customer_gender', 'NA')}\n"
            f"Age: {data.get('customer_age', 'NA')}\n"
            f"Email: {data['customer_email'] or 'NA'}\n\n"
            f"Salon: {salon['name']}\n"
            f"Service: {service['serviceName']}\n"
            f"Date: {data['date']}\n"
            f"Time: {data['time']}\n\n"
            "Reply YES to confirm or NO to cancel."
        )

    
    # =====================================================
    # FINAL BOOKING
    # =====================================================
    if state == "CUSTOMER_CONFIRM":

     if msg.lower() == "yes":

        salon = data["salon"]
        service = data["service"]

        employees = find_employees_by_salon(salon["id"])

        assigned_employee = None
        for emp in employees:
            ok = is_slot_available(
                salon_id=salon["id"],
                employee_id=emp["employeeId"],
                date=data["normalized_date"],
                start_time=data["time"],
                duration=service["duration"]
            )
            if ok:
                assigned_employee = emp
                break

        if not assigned_employee:
            session["state"] = "CUSTOMER_DATE"
            SESSIONS[user_id] = session
            return "⛔ Slot just booked. Please choose another time."

        # 🔥 FIND OWNER UID CORRECTLY
        owner_uid = find_owner_uid_by_salon(salon["id"])
        print("DEBUG: owner_uid found =", owner_uid)

        booking = {
            "customer": {
                "name": data["customer_name"],
                "phone": data["customer_phone"],
                "email": data.get("customer_email", ""),
                "gender": data.get("customer_gender"),
                "age": data.get("customer_age")
            },

            "placeId": salon["id"],
            "employeeId": assigned_employee["employeeId"],

            "services": [
                {
                    "serviceId": service["serviceId"],
                    "serviceName": service["serviceName"],
                    "price": service["price"],
                    "duration": service["duration"]
                }
            ],

            "date": data["normalized_date"],
            "startTime": data["time"],

            "totalAmount": service["price"],
            "totalDuration": service["duration"],

            "paymentMode": "online",
            "paymentStatus": "pending",
            "status": "confirmed",

            "mode": "whatsapp",
            "type": "salon",

            "ownerUid": owner_uid,
            "salonName": salon["name"],
            "branch": salon["address"],
            "employeeName": assigned_employee["name"]
        }

        save_whatsapp_booking(salon["id"], booking)

        # 🔔 SEND CONFIRM NOTIFICATION TO OWNER
        confirm_msg = build_appointment_message(booking)

        owner_phone = get_owner_phone(owner_uid)
        if owner_phone:
            send_whatsapp_message(owner_phone, confirm_msg)

        # 🔥 FETCH EMPLOYEE FROM GLOBAL EMPLOYEES NODE
        employee_full = get_employee_by_id(
            assigned_employee["employeeId"]

        )

        if employee_full:
            emp_phone = employee_full.get("phone")
            print("📞 DEBUG: Final employee phone =", emp_phone)

            if emp_phone and str(emp_phone) != "0000000000":
                send_whatsapp_message(emp_phone, confirm_msg)
            else:
                print("⚠️ Employee phone missing or dummy, skipping WhatsApp")
        else:
            print("⚠️ Could not fetch employee from Firebase, skipping WhatsApp")

        SESSIONS.pop(user_id, None)
        return "🎉 Your appointment is confirmed! Thank you for booking with Glowbizz ✨"

    else:
        SESSIONS.pop(user_id, None)
        return "Booking cancelled. You can start again anytime."


    # =====================================================
    # ❌ CANCEL FLOW
    # =====================================================
    if state == "CANCEL_PHONE":
        data["cancel_phone"] = msg
        session["state"] = "CANCEL_NAME"
        SESSIONS[user_id] = session
        return "Please enter your Full Name used for booking."

    if state == "CANCEL_NAME":
        data["cancel_name"] = msg

        result = find_latest_active_booking_by_customer(
            phone=data["cancel_phone"],
            name=data["cancel_name"]
        )

        if not result:
            SESSIONS.pop(user_id, None)
            return (
                "⚠️ Sorry, I could not find any active appointment with these details.\n\n"
                "Please check your name and phone number and try again."
            )

        data["cancel_booking"] = result
        session["state"] = "CANCEL_CONFIRM"
        SESSIONS[user_id] = session

        return (
            "🔎 I found your appointment:\n\n"
            f"🏬 Salon: {result['salonName']}\n"
            f"💆 Service: {result['serviceName']}\n"
            f"📅 Date: {result['date']}\n"
            f"⏰ Time: {result['startTime']}\n\n"
            "Reply YES to cancel this appointment or NO to keep it."
        )

    if state == "CANCEL_CONFIRM":

        if msg.lower() == "yes":

            booking = data["cancel_booking"]

            cancel_appointment_and_cleanup(
                salon_id=booking["salonId"],
                appointment_id=booking["appointmentId"],
                date=booking["date"]
            )

            cancel_msg = build_cancel_message({
                "customerName": booking["customerName"],
                "customerPhone": booking["customerPhone"],
                "salonName": booking["salonName"],
                "serviceName": booking["serviceName"],
                "date": booking["date"],
                "startTime": booking["startTime"]
            })

            owner_phone = get_owner_phone(booking["ownerUid"])
            if owner_phone:
                send_whatsapp_message(owner_phone, cancel_msg)

            if booking.get("employeePhone"):
                send_whatsapp_message(booking["employeePhone"], cancel_msg)

            SESSIONS.pop(user_id, None)
            return "✅ Your appointment has been cancelled successfully."

        else:
            SESSIONS.pop(user_id, None)
            return "👍 Okay, your appointment is safe. No changes made."

    # =====================================================
    # FALLBACK
    # =====================================================
    return "Sorry, I did not understand. Please type HI to start again."
