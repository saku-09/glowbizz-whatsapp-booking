from data.store import SESSIONS

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
    get_owner_phone          # 🔥 IMPORTANT
)

# 🔔 Notification services
from services.notification_service import build_appointment_message
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
# MAIN CONVERSATION HANDLER (NO AUTH UID, FIREBASE PUSH STYLE)
# =====================================================
def handle_conversation(user_id: str, message: str):
    """
    user_id -> whatsapp session id / phone
    """

    session = SESSIONS.get(user_id, {
        "state": "START",
        "data": {}
    })

    state = session["state"]
    data = session["data"]
    msg = message.strip()

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
            return (
                "Welcome, Salon Owner 👋\n"
                "Are you already using Glowbizz?\n"
                "1️⃣ Yes, Login\n"
                "2️⃣ No, I want to register"
            )

        elif msg == "2":
            data["role"] = "CUSTOMER"
            session["state"] = "CUSTOMER_CITY"
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
            return "Great! Please enter your Salon Name."
        else:
            return "Please reply with 1 or 2."

    if state == "OWNER_COLLECT_NAME":
        data["salon_name"] = msg
        session["state"] = "OWNER_COLLECT_CITY"
        return "Please enter your City."

    if state == "OWNER_COLLECT_CITY":
        data["city"] = msg
        session["state"] = "OWNER_COLLECT_MOBILE"
        return "Please enter your Mobile Number."

    if state == "OWNER_COLLECT_MOBILE":
        data["mobile"] = msg
        session["state"] = "SHOW_PLANS"
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
    # 👩‍💼 CUSTOMER FLOW
    # =====================================================

    # Step 1 – City
    if state == "CUSTOMER_CITY":
        data["city"] = msg.lower()
        session["state"] = "CUSTOMER_SELECT_SALON"

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

    # Step 2 – Select Salon
    if state == "CUSTOMER_SELECT_SALON":
        try:
            choice = int(msg) - 1
            salon = data["salons"][choice]

            data["salon"] = salon
            session["state"] = "CUSTOMER_SELECT_SERVICE"

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

    # Step 3 – Select Service
    if state == "CUSTOMER_SELECT_SERVICE":
        try:
            choice = int(msg) - 1
            service = data["services"][choice]

            data["service"] = service
            session["state"] = "CUSTOMER_DATE"

            return "Please enter appointment date (DD-MM-YYYY)."

        except:
            return "Please reply with a valid number."

    # =====================================================
    # Step 4 – Date & SLOT GENERATION
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
            return (
                "Sorry 😔 This salon is closed on this day.\n\n"
                "Please choose another date."
            )

        open_time = timings.get("open")
        close_time = timings.get("close")

        service_duration = int(service["duration"])

        all_slots = generate_slots_by_duration(
            open_time=open_time,
            close_time=close_time,
            service_duration=service_duration
        )

        booked_slots = get_booked_slots_from_salon_node(
            salon_id=salon_id,
            date=normalized_date
        )

        blocked_times = set(b["startTime"] for b in booked_slots)
        free_slots = [t for t in all_slots if t not in blocked_times]

        if not free_slots:
            return (
                "Sorry 😔 No free slots available on this date.\n\n"
                "Please choose another date."
            )

        data["normalized_date"] = normalized_date
        data["generated_slots"] = free_slots
        session["state"] = "CUSTOMER_SELECT_SLOT"

        response = f"Available time slots on {msg}:\n\n"
        for idx, t in enumerate(free_slots, start=1):
            response += f"{idx}️⃣ {t}\n"

        response += "\nReply with the number to select time."
        return response

    # Step 5 – Select Slot
    if state == "CUSTOMER_SELECT_SLOT":
        try:
            slots = data.get("generated_slots", [])
            choice = int(msg) - 1

            if choice < 0 or choice >= len(slots):
                return "Please reply with a valid number."

            data["time"] = slots[choice]
            session["state"] = "CUSTOMER_NAME"
            return "Great 👍\n\nPlease enter your Full Name."

        except:
            return "Please reply with a valid number."

    # =====================================================
    # CUSTOMER DETAILS
    # =====================================================

    if state == "CUSTOMER_NAME":
        data["customer_name"] = msg
        session["state"] = "CUSTOMER_PHONE"
        return "Please enter your Mobile Number."

    if state == "CUSTOMER_PHONE":
        data["customer_phone"] = msg
        session["state"] = "CUSTOMER_EMAIL"
        return "Please enter your Email (or type NA)."

    if state == "CUSTOMER_EMAIL":
        data["customer_email"] = "" if msg.lower() == "na" else msg
        session["state"] = "CUSTOMER_AGE"
        return "Please enter your Age (or type NA)."

    if state == "CUSTOMER_AGE":
        data["customer_age"] = "" if msg.lower() == "na" else msg
        session["state"] = "CUSTOMER_GENDER"
        return (
            "Please select your Gender:\n\n"
            "1️⃣ Male\n"
            "2️⃣ Female\n"
            "3️⃣ Other\n\n"
            "Reply with 1, 2, or 3."
        )

    if state == "CUSTOMER_GENDER":
        gender_map = {"1": "Male", "2": "Female", "3": "Other"}

        if msg not in gender_map:
            return "Please reply with 1, 2, or 3."

        data["customer_gender"] = gender_map[msg]
        session["state"] = "CUSTOMER_CONFIRM"

        salon = data["salon"]
        service = data["service"]

        return (
            "Please confirm your booking:\n\n"
            f"Name: {data['customer_name']}\n"
            f"Phone: {data['customer_phone']}\n"
            f"Email: {data['customer_email'] or 'NA'}\n"
            f"Age: {data['customer_age'] or 'NA'}\n"
            f"Gender: {data['customer_gender']}\n\n"
            f"Salon: {salon['name']}\n"
            f"Service: {service['serviceName']}\n"
            f"Date: {data['date']}\n"
            f"Time: {data['time']}\n\n"
            "Reply YES to confirm or NO to cancel."
        )

    # =====================================================
    # FINAL CONFIRM (WITH NOTIFICATION)
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
                return "⛔ Slot just booked. Please choose another time."

            # 🔥 FINAL BOOKING OBJECT
            booking = {
                "customer": {
                    "name": data["customer_name"],
                    "phone": data["customer_phone"],
                    "email": data.get("customer_email", ""),
                    "age": data.get("customer_age", ""),
                    "gender": data.get("customer_gender", "")
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

                # Metadata
                "ownerUid": salon.get("ownerUid"),
                "salonName": salon["name"],
                "branch": salon["address"],
                "employeeName": assigned_employee["name"]
            }

            # 🔥 SAVE BOOKING
            save_whatsapp_booking(salon["id"], booking)

            # =====================================================
            # 🔔 SEND NOTIFICATIONS (CORRECT OWNER PHONE FLOW)
            # =====================================================
            print("🔔 Building notification message...")
            notification_msg = build_appointment_message(booking)
            print("🔔 Notification message built:\n", notification_msg)

            # 🔥 FETCH OWNER PHONE USING ownerUid
            owner_uid = salon.get("ownerUid")
            print("👤 Owner UID:", owner_uid)

            owner_phone = None
            if owner_uid:
                owner_phone = get_owner_phone(owner_uid)

            print("📞 Owner phone (from admin node):", owner_phone)

            if owner_phone:
                send_whatsapp_message(owner_phone, notification_msg)
            else:
                print("⚠️ Owner phone not found in admin node")

            # 🔥 SEND TO EMPLOYEE (ONLY IF VALID)
            employee_phone = assigned_employee.get("phone")
            print("📞 Employee phone:", employee_phone)

            if employee_phone and employee_phone != "0000000000":
                send_whatsapp_message(employee_phone, notification_msg)
            else:
                print("⚠️ Valid employee phone not found, skipping employee notification")

            # Clear session
            SESSIONS.pop(user_id, None)

            return (
                "🎉 Your appointment is confirmed!\n\n"
                f"📍 Salon: {salon['name']}\n"
                f"💆 Service: {service['serviceName']}\n"
                f"👨‍💼 Staff: {assigned_employee['name']}\n"
                f"📅 Date: {data['date']}\n"
                f"⏰ Time: {data['time']}\n"
                f"💰 Amount: ₹{service['price']}\n\n"
                "📲 The salon and staff have been notified on WhatsApp.\n"
                "Thank you for booking through Glowbizz ✨"
            )

        else:
            SESSIONS.pop(user_id, None)
            return "Booking cancelled. You can start again anytime."

    # =====================================================
    # FALLBACK
    # =====================================================

    return "Sorry, I did not understand. Please type HI to start again."
