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

from services.notification_service import (
    notify_owner_new_booking,
    notify_owner_cancel
)

# ==================================================
# SLOT GENERATOR
# ==================================================

def generate_slots_by_duration(open_time, close_time, duration):

    if not open_time or not close_time:
        return []

    slots = []

    try:
        start = datetime.strptime(open_time, "%H:%M")
        end = datetime.strptime(close_time, "%H:%M")

        current = start

        while current + timedelta(minutes=duration) <= end:
            slots.append(current.strftime("%H:%M"))
            current += timedelta(minutes=duration)
    except:
        return []

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
# AUTO EMPLOYEE ASSIGNMENT
# ==================================================

def auto_assign_employee(employees, time_slot):

    if not employees:
        return None

    # simple load balancing using time slot hash
    index = abs(hash(time_slot)) % len(employees)

    return employees[index]


# ==================================================
# SALON PAGE SENDER (helper)
# ==================================================

def _send_salon_page(user_id, all_salons, page):
    """Send one page of salons (9 per page) with a 'See More' row if needed."""

    PAGE_SIZE = 9
    start = page * PAGE_SIZE
    page_salons = all_salons[start: start + PAGE_SIZE]

    rows = []

    for salon in page_salons:
        title = (salon.get("name") or salon.get("salonName") or "Salon")[:24]
        row = {"id": str(salon.get("id")), "title": title}
        description = (salon.get("address") or "")[:72]
        if description:
            row["description"] = description
        rows.append(row)

    # Add 'See More' if there are more salons beyond this page
    if start + PAGE_SIZE < len(all_salons):
        rows.append({
            "id": "MORE_SALONS",
            "title": "➡️ See More",
            "description": f"Showing {start+1}–{start+len(page_salons)} of {len(all_salons)}"
        })

    total_pages = (len(all_salons) + PAGE_SIZE - 1) // PAGE_SIZE
    header = f"💇 Select a Salon or Spa (Page {page+1}/{total_pages})"

    return send_whatsapp_list(user_id, header, rows)


def _send_service_page(user_id, all_services, page):
    """Send one page of services (9 per page) with a 'See More' row if needed."""

    PAGE_SIZE = 9
    start = page * PAGE_SIZE
    page_items = all_services[start: start + PAGE_SIZE]

    rows = []

    for s in page_items:

        title = (s.get("serviceName") or "Service")[:24]

        price = s.get("price", 0)
        duration = s.get("duration", 30)

        desc = f"₹{price} | {duration} min"

        rows.append({
            "id": str(s.get("serviceId")),
            "title": title,
            "description": desc
        })

    # Add 'See More' if there are more services beyond this page
    if start + PAGE_SIZE < len(all_services):
        rows.append({
            "id": "MORE_SERVICES",
            "title": "➡️ See More Services",
            "description": f"Showing {start+1}–{start+len(page_items)} of {len(all_services)}"
        })

    total_pages = (len(all_services) + PAGE_SIZE - 1) // PAGE_SIZE
    header = f"💆 Select Service (Page {page+1}/{total_pages})"

    return send_whatsapp_list(user_id, header, rows)


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
# GLOBAL RESTART — any greeting resets the session
# ==================================================

    RESTART_KEYWORDS = {"HI", "HII", "HIII", "HELLO", "HEY", "START", "RESTART", "MENU", "HOME"}

    if msg_upper in RESTART_KEYWORDS:

        SESSIONS.pop(user_id, None)   # clear any existing session

        SESSIONS[user_id] = {"state": "MAIN_MENU", "data": {}}

        send_whatsapp_buttons(
            user_id,
            "✨ *Welcome to NexSalon* ✨\n\nYour personal salon booking assistant 💇‍♀️",
            [
                {"id": "BOOK",   "title": "Book Appointment"},
                {"id": "CANCEL", "title": "Cancel Appointment"}
            ]
        )

        return ""


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
                {"id": "BOOK",   "title": "Book Appointment"},
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
        data["salon_page"] = 0               # start at page 0

        all_salons = find_salons_by_city(msg_lower)

        print("CITY ENTERED:", msg_lower)
        print("SALONS FROM FIREBASE:", all_salons)

        if not all_salons:
            return "❌ No salons found in this city. Please try another city name."

        data["salons"] = all_salons          # store ALL salons, paginate on display

        result = _send_salon_page(user_id, all_salons, page=0)

        if not result:
            return "⚠️ Could not show salon list. Please try again or type a different city."

        # Only advance state after successful send
        session["state"] = "SELECT_SALON"
        SESSIONS[user_id] = session

        return ""




# ==================================================
# SALON SELECT
# ==================================================

    if state == "SELECT_SALON":

        # ── Handle "See More" pagination ──
        if msg_upper == "MORE_SALONS":

            data["salon_page"] = data.get("salon_page", 0) + 1
            SESSIONS[user_id] = session

            result = _send_salon_page(user_id, data["salons"], page=data["salon_page"])

            if not result:
                return "⚠️ Could not load next page. Please try again."

            return ""

        # ── Normal salon selection ──
        salon = None

        for s in data["salons"]:
            if str(s["id"]).upper() == msg_upper:
                salon = s
                break

        if not salon:
            return "❌ Invalid selection. Please pick a salon from the list, or tap ➡️ See More."

        data["salon"] = salon
        data["service_page"] = 0

        business_type = salon.get('type', 'salon')  # "salon" or "spa"
        collection_plural = f"{business_type}s"     # "salons" or "spas"
        
        all_services = find_services_by_salon(salon["id"], collection=collection_plural)

        print("SERVICES FOUND:", all_services)

        if not all_services:
            return "❌ This salon has no active services available for booking right now."

        data["services"] = all_services
        data["business_type"] = business_type
        data["collection"] = collection_plural

        result = _send_service_page(user_id, all_services, page=0)

        if not result:
            return "⚠️ Could not show service list. Please try selecting the salon again."

        session["state"] = "SELECT_SERVICE"
        SESSIONS[user_id] = session

        return ""


# ==================================================
# SERVICE SELECT
# ==================================================

    if state == "SELECT_SERVICE":

        # ── Handle "See More" pagination ──
        if msg_upper == "MORE_SERVICES":

            data["service_page"] = data.get("service_page", 0) + 1
            SESSIONS[user_id] = session

            result = _send_service_page(user_id, data["services"], page=data["service_page"])

            if not result:
                return "⚠️ Could not load next page. Please try again."

            return ""

        # ── Normal service selection ──
        service = None

        for s in data["services"]:
            if str(s["serviceId"]).upper() == msg_upper:
                service = s
                break

        if not service:
            return "❌ Invalid selection. Please pick a service from the list, or tap ➡️ See More."

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

        collection = data.get("collection", "salons")

        timings = get_salon_timings(salon["id"], day_name, collection=collection)

        if not timings or not timings.get("isOpen"):
            return "Salon is closed that day."

        duration = int(service.get("duration", 30))

        slots = generate_slots_by_duration(
            timings["open"],
            timings["close"],
            duration
        )

        booked = get_booked_slots_from_salon_node(
            salon["id"],
            msg,
            collection=collection
        )

        free_slots = []

        for slot_start in slots:
            
            # Check if this slot overlaps with ANY booked slot
            is_overlap = False
            
            s_dt = datetime.strptime(slot_start, "%H:%M")
            s_end_dt = s_dt + timedelta(minutes=duration)

            for b in booked:
                b_start_dt = datetime.strptime(b["start"], "%H:%M")
                b_end_dt = datetime.strptime(b["end"], "%H:%M")

                if s_dt < b_end_dt and b_start_dt < s_end_dt:
                    is_overlap = True
                    break
            
            if not is_overlap:
                free_slots.append(slot_start)

        if not free_slots:
            return "❌ No available slots for this service on this date. Please try another date."

        data["generated_slots"] = free_slots

        session["state"] = "SELECT_SLOT"
        SESSIONS[user_id] = session

        rows = []

        for slot in free_slots:
            rows.append({
                "id": slot,
                "title": slot
            })

        result = send_whatsapp_list(
            user_id,
            "⏰ Select Time Slot",
            rows
        )

        if not result:
            return "⚠️ Could not show time slots. Please try selecting the date again."

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

    send_whatsapp_buttons(
        user_id,
        "Select Gender",
        [
            {"id": "MALE", "title": "Male"},
            {"id": "FEMALE", "title": "Female"},
            {"id": "OTHER", "title": "Other"}
        ]
    )

    return ""


# ==================================================
# GENDER
# ==================================================

    if state == "GENDER":

     gender_map = {
        "MALE": "Male",
        "FEMALE": "Female",
        "OTHER": "Other"
    }

    if msg.upper() not in gender_map:
        return "Please select gender using the buttons."

    data["gender"] = gender_map[msg.upper()]

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

            business_type = data.get("business_type", "salon")
            collection_plural = data.get("collection", "salons")

            employees = find_employees_by_salon(salon["id"], collection=collection_plural)

            # AUTO EMPLOYEE ASSIGNMENT
            employee = auto_assign_employee(employees, data["time"])

            owner_uid = find_owner_uid_by_salon(salon["id"])

            booking = {

                "customer": {
                    "name": data["name"],
                    "phone": data["phone"],
                    "gender": data["gender"],
                    "age": data["age"]
                },

                "placeId": salon["id"],
                "salonName": salon.get("name") or salon.get("salonName"),
                "branch": salon.get("branch") or salon.get("address"),
                "employeeId": employee["employeeId"] if employee else "auto",
                "employeeName": employee["name"] if employee else "Auto-Assign",
                "services": [service],
                "totalDuration": int(service.get("duration", 30)),
                "date": data["date"],
                "startTime": data["time"],
                "status": "confirmed",
                "ownerUid": owner_uid
            }

            result = save_whatsapp_booking(salon["id"], booking, collection=business_type)

            if isinstance(result, dict) and result.get("success") == False:
                return result["message"]

            # 🔔 NOTIFY OWNER
            notify_owner_new_booking(booking)

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

        data["cancel_name"] = msg

    session["state"] = "CANCEL_DATE"
    SESSIONS[user_id] = session

    return "Enter appointment date (DD-MM-YYYY)"


  
    if state == "CANCEL_DATE":

      data["cancel_date"] = msg

    session["state"] = "CANCEL_TIME"
    SESSIONS[user_id] = session

    return "Enter appointment time (HH:MM)"


    if state == "CANCEL_TIME":

     data["cancel_time"] = msg

     result = find_latest_active_booking_by_customer(
        phone=data["cancel_phone"],
        name=data["cancel_name"]
    )

    if not result:
        return "❌ No booking found."

    # verify date and time match
    if result["date"] != data["cancel_date"] or result["startTime"] != data["cancel_time"]:
        return "❌ Booking details do not match."

    cancel_appointment_and_cleanup(
        salon_id=result["salonId"],
        appointment_id=result["appointmentId"],
        date=result["date"],
        collection=result.get("collection", "salons")
    )

    # 🔔 NOTIFY OWNER
    if result.get("ownerUid"):
        notify_owner_cancel(result, result["ownerUid"])

    SESSIONS.pop(user_id, None)

    return "✅ Appointment cancelled successfully."


# ==================================================
# FALLBACK
# ==================================================

    return "Type HI to start."