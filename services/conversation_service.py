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
    is_slot_available,
    get_available_slots,
    cancel_appointment_and_cleanup,
    find_latest_active_booking_by_customer,
    find_owner_uid_by_salon,
    get_customer_active_bookings
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
    header = (
    f"🏬 *Choose a Salon*\n"
    f"Page {page+1}/{total_pages}\n\n"
    f"Select a salon near you 👇"
)

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
    header = (
    f"💆 *Choose a Service*\n"
    f"Page {page+1}/{total_pages}\n\n"
    f"Select the service you want 👇"
)

    return send_whatsapp_list(user_id, header, rows)


# ==================================================
# SLOT PAGE SENDER
# ==================================================

def _send_slot_page(user_id, all_slots, page):

    PAGE_SIZE = 9

    start = page * PAGE_SIZE
    page_slots = all_slots[start:start + PAGE_SIZE]

    rows = []

    for slot in page_slots:
        rows.append({
            "id": slot,
            "title": slot
        })

    # Add see more button
    if start + PAGE_SIZE < len(all_slots):
        rows.append({
            "id": "MORE_SLOTS",
            "title": "➡️ See More Slots"
        })

    return send_whatsapp_list(
        user_id,
        f"⏰ *Available Time Slots*\nPage {page+1}\n\nChoose a convenient time 👇",
        rows
    )


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
            "✨ *Welcome to NexSalon* ✨\n\nBook your Salon & Spa appointment in seconds.\n\n"
            "Choose an option below 👇",
            [
                {"id": "BOOK",   "title": "Book Appointment"},
                {"id": "REBOOK", "title": "Rebook Last"},
                {"id": "RESCHEDULE", "title": "Reschedule"},
                {"id": "CANCEL", "title": "Cancel Appointment"},
                {"id": "MY_BOOKINGS", "title": "My Bookings"}
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
                {"id": "REBOOK", "title": "Rebook Last"},
                {"id": "RESCHEDULE", "title": "Reschedule"},
                {"id": "CANCEL", "title": "Cancel Appointment"},
                {"id": "MY_BOOKINGS", "title": "My Bookings"}
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

        elif msg_upper in ["REBOOK", "REBOOK LAST", "REBOOK LAST APPOINTMENT"]:

            session["state"] = "REBOOK_PHONE"
            SESSIONS[user_id] = session

            return "📱 Please enter your registered phone number to find your last booking"

        elif msg_upper in ["RESCHEDULE", "RESCHEDULE APPOINTMENT"]:

            session["state"] = "RESCHEDULE_PHONE"
            SESSIONS[user_id] = session

            return "📱 Please enter the phone number used for booking."

        elif msg_upper in ["CANCEL", "CANCEL APPOINTMENT"]:

            session["state"] = "CANCEL_PHONE"
            SESSIONS[user_id] = session

            return "Please enter your registered phone number"

        elif msg_upper in ["MY_BOOKINGS", "MY BOOKINGS"]:

            session["state"] = "MY_BOOKINGS_PHONE"
            SESSIONS[user_id] = session

            return "📱 Please enter your phone number to view your appointments"

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
        data["selected_services"] = []  # Clear previous selections

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

        # store multiple services
        data.setdefault("selected_services", []).append(service)

        service_list = "\n".join(
            f"• {s['serviceName']}" for s in data["selected_services"]
        )

        send_whatsapp_buttons(
            user_id,
            f"✅ *Service Added*\n\n"
            f"Selected Services:\n{service_list}\n\n"
            f"Add another service or continue 👇",
            [
                {"id": "ADD_MORE_SERVICE", "title": "Add Another"},
                {"id": "DONE_SERVICE", "title": "Continue"}
            ]
        )

        session["state"] = "SERVICE_CONFIRM"
        SESSIONS[user_id] = session

        return ""


# ==================================================
# SERVICE CONFIRM
# ==================================================

    if state == "SERVICE_CONFIRM":

        if msg_upper == "ADD_MORE_SERVICE":

            session["state"] = "SELECT_SERVICE"
            SESSIONS[user_id] = session

            return _send_service_page(user_id, data["services"], page=0)

        elif msg_upper == "DONE_SERVICE":

            session["state"] = "SELECT_DATE"
            SESSIONS[user_id] = session

            rows = generate_calendar_dates()

            send_whatsapp_list(
                user_id,
                "📅 *Choose Appointment Date*\n\nSelect your preferred day 👇",
                rows
            )

            return ""

        else:
            return "Please choose an option."


# ==================================================
# DATE SELECT
# ==================================================

    if state == "SELECT_DATE":

        data["date"] = msg

        salon = data["salon"]
        services = data.get("selected_services", [])
        total_duration = sum(int(s.get("duration", 30)) for s in services)

        dt = datetime.strptime(msg, "%d-%m-%Y")
        collection = data.get("collection", "salons")

        # ✅ Backend-driven slot generation & filtering in one call
        free_slots = get_available_slots(
            salon["id"],
            msg,
            duration=total_duration,
            collection=collection
        )

        # ❌ NO SLOTS
        if not free_slots:

            send_whatsapp_list(
                user_id,
                "❌ No slots available on this date.\n\nPlease choose another date.",
                generate_calendar_dates()
            )

            session["state"] = "SELECT_DATE"
            SESSIONS[user_id] = session
            return ""

        # ✅ SHOW SLOTS
        data["generated_slots"] = free_slots
        data["slot_page"] = 0

        session["state"] = "SELECT_SLOT"
        SESSIONS[user_id] = session

        _send_slot_page(user_id, free_slots, 0)

        return ""
# ==================================================
# SLOT SELECT
# ==================================================

    if state == "SELECT_SLOT":

        # pagination
        if msg_upper == "MORE_SLOTS":

            data["slot_page"] = data.get("slot_page", 0) + 1
            SESSIONS[user_id] = session

            return _send_slot_page(
                user_id,
                data["generated_slots"],
                data["slot_page"]
            )

        selected_slot = msg.strip()

        if selected_slot not in data.get("generated_slots", []):
            available = data.get("generated_slots", [])

            if available:
                suggestions = "\n".join(available[:3])  # show next 3 slots

                return (
                    "❌ That slot is not available.\n\n"
                    "Here are the next available slots:\n"
                    f"{suggestions}\n\n"
                    "Please select one from the list."
                )

            return "❌ No slots available. Please choose another date."

        data["time"] = selected_slot

        session["state"] = "NAME"
        SESSIONS[user_id] = session

        return "👤 Please enter your *Full Name*"

# ==================================================
# NAME
# ==================================================
    if state == "NAME":
        data["name"] = msg
        session["state"] = "GENDER"
        SESSIONS[user_id] = session

        send_whatsapp_buttons(
            user_id,
            "⚧ *Select Your Gender*",
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

        return "🎂 Please enter your Age"

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

            return "📱 Enter your 10 digit phone number"

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
        services = data.get("selected_services", [])
        services_text = "\n".join([f"• {s['serviceName']}" for s in services])
        total_amount = sum(int(s.get("price", 0)) for s in services)

        summary = (
            "📋 *Appointment Summary*\n\n"
            f"👤 Name: {data['name']}\n"
            f"📱 Phone: {data['phone']}\n"
            f"⚧ Gender: {data['gender']}\n"
            f"🎂 Age: {data['age']}\n\n"
            f"🏬 Salon: {salon['name']}\n"
            f"💆 Services:\n{services_text}\n"
            f"💰 Total: ₹{total_amount}\n"
            f"📅 Date: {data['date']}\n"
            f"⏰ Time: {data['time']}\n\n"
            "Please confirm your booking 👇"
        )

        session["state"] = "CONFIRM"
        SESSIONS[user_id] = session

        send_whatsapp_buttons(
            user_id,
            summary,
            [
                {"id": "CONFIRM", "title": "Confirm"}
            ]
        )

        return ""


# ==================================================
# CONFIRM BOOKING
# ==================================================

    if state == "CONFIRM":

        if msg_upper in ["CONFIRM", "CONFIRM BOOKING"]:

            salon = data["salon"]
            services = data.get("selected_services", [])
            total_duration = sum(int(s.get("duration", 30)) for s in services)
            total_amount = sum(int(s.get("price", 0)) for s in services)

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
                "services": services,
                "totalDuration": total_duration,
                "totalAmount": total_amount,
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

            send_whatsapp_buttons(
                user_id,
                "🎉 *Booking Confirmed!*\n\n"
                "Your appointment has been successfully booked.\n"
                "Thank you for choosing NexSalon 💇‍♀️\n\n"
                "What would you like to do next? 👇",
                [
                    {"id": "BOOK", "title": "Book Another"},
                    {"id": "MY_BOOKINGS", "title": "My Bookings"}
                ]
            )

            return ""
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
            collection=result.get("collection", "salon")
        )

        # 🔔 NOTIFY OWNER
        if result.get("ownerUid"):
            notify_owner_cancel(result, result["ownerUid"])

        SESSIONS.pop(user_id, None)
        return (
        "❌ *Appointment Cancelled*\n\n"
        "Your booking has been cancelled successfully."
        )


# ==================================================
# FALLBACK
# ==================================================

# ==================================================
# REBOOK FLOW
# ==================================================

    if state == "REBOOK_PHONE":
        data["rebook_phone"] = msg
        session["state"] = "REBOOK_NAME"
        SESSIONS[user_id] = session
        return "👤 Please enter your *Full Name*"

    if state == "REBOOK_NAME":
        booking = find_latest_active_booking_by_customer(
            phone=data["rebook_phone"],
            name=msg
        )

        if not booking:
            return "❌ No previous booking found for this name and phone."

        data["last_booking"] = booking
        data["selected_services"] = booking.get("services", [])
        data["salon"] = {"id": booking["salonId"], "name": booking["salonName"]}
        
        # Determine collection type from booking info if possible, else default
        data["collection"] = f"{booking.get('collection', 'salon')}s"
        data["business_type"] = booking.get('collection', 'salon')

        services_text = "\n".join(
            f"• {s['serviceName']}" for s in data["selected_services"]
        )

        send_whatsapp_buttons(
            user_id,
            f"🔁 *Rebook Last Appointment*\n\n"
            f"Previous Services:\n{services_text}\n\n"
            f"What would you like to do?",
            [
                {"id": "REBOOK_SAME", "title": "Rebook Same"},
                {"id": "CHANGE_SERVICE", "title": "Choose Different"},
                {"id": "CANCEL", "title": "Cancel"}
            ]
        )

        session["state"] = "REBOOK_CONFIRM"
        SESSIONS[user_id] = session
        return ""

    if state == "REBOOK_CONFIRM":
        if msg_upper == "REBOOK_SAME":
            session["state"] = "SELECT_DATE"
            SESSIONS[user_id] = session

            rows = generate_calendar_dates()
            send_whatsapp_list(
                user_id,
                "📅 *Choose Appointment Date*\n\nSelect your preferred day 👇",
                rows
            )
            return ""

        elif msg_upper == "CHANGE_SERVICE":
            data["selected_services"] = []
            
            # We need services list for this salon to show the page
            all_services = find_services_by_salon(data["salon"]["id"], collection=data["collection"])
            if not all_services:
                return "❌ Could not fetch services for this salon."
            
            data["services"] = all_services
            data["service_page"] = 0
            
            session["state"] = "SELECT_SERVICE"
            SESSIONS[user_id] = session

            return _send_service_page(user_id, all_services, 0)

        elif msg_upper == "CANCEL":
            SESSIONS.pop(user_id, None)
            return "Rebooking cancelled."
        else:
            return "Please choose an option."


# ==================================================
# RESCHEDULE FLOW
# ==================================================

    if state == "RESCHEDULE_PHONE":
        data["reschedule_phone"] = msg
        session["state"] = "RESCHEDULE_NAME"
        SESSIONS[user_id] = session
        return "👤 Please enter the *Full Name* used for booking."

    if state == "RESCHEDULE_NAME":
        booking = find_latest_active_booking_by_customer(
            phone=data["reschedule_phone"],
            name=msg
        )

        if not booking:
            return "❌ No active booking found."

        data["reschedule_booking"] = booking
        # Store essential data for slot checking
        data["salon"] = {"id": booking["salonId"], "name": booking["salonName"]}
        data["selected_services"] = booking.get("services", [])
        data["collection"] = f"{booking.get('collection', 'salon')}s"

        session["state"] = "RESCHEDULE_DATE"
        SESSIONS[user_id] = session

        send_whatsapp_list(
            user_id,
            "📅 *Choose New Appointment Date*",
            generate_calendar_dates()
        )
        return ""

    if state == "RESCHEDULE_DATE":
        data["reschedule_date"] = msg
        
        booking = data["reschedule_booking"]
        total_duration = int(booking.get("totalDuration", 30))

        free_slots = get_available_slots(
            booking["salonId"],
            msg,
            duration=total_duration,
            collection=f"{booking.get('collection', 'salon')}s"
        )

        if not free_slots:
            return "❌ No slots available for this date."

        data["generated_slots"] = free_slots
        data["slot_page"] = 0

        session["state"] = "RESCHEDULE_SLOT"
        SESSIONS[user_id] = session

        _send_slot_page(user_id, free_slots, 0)
        return ""

    if state == "RESCHEDULE_SLOT":
        if msg_upper == "MORE_SLOTS":
            data["slot_page"] = data.get("slot_page", 0) + 1
            SESSIONS[user_id] = session
            return _send_slot_page(user_id, data["generated_slots"], data["slot_page"])

        if msg not in data.get("generated_slots", []):
            available = data.get("generated_slots", [])

            if available:
                suggestions = "\n".join(available[:3])

                return (
                    "❌ That slot is not available.\n\n"
                    "Next available slots:\n"
                    f"{suggestions}\n\n"
                    "Please choose one."
                )

            return "❌ No slots available."

        booking = data["reschedule_booking"]
        
        # Cancel old
        cancel_appointment_and_cleanup(
            salon_id=booking["salonId"],
            appointment_id=booking["appointmentId"],
            date=booking["date"],
            collection=booking.get("collection", "salon")
        )

        # Create new
        new_booking = booking.copy()
        new_booking["date"] = data["reschedule_date"]
        new_booking["startTime"] = msg
        new_booking["status"] = "confirmed"
        
        # Clean up keys not needed for save_whatsapp_booking or ensure they match what it expects
        # save_whatsapp_booking expects salon_id, booking_data, collection="salon"
        # It creates a new customer record from booking_data["customer"]
        
        result = save_whatsapp_booking(
            booking["salonId"],
            new_booking,
            collection=booking.get("collection", "salon")
        )

        if isinstance(result, dict) and result.get("success") == False:
            return result["message"]

        SESSIONS.pop(user_id, None)
        return "✅ *Appointment Rescheduled Successfully!*\n\nYour new appointment is confirmed."


# ==================================================
# MY BOOKINGS FLOW
# ==================================================

    if state == "MY_BOOKINGS_PHONE":
        bookings = get_customer_active_bookings(msg)

        if not bookings:
            SESSIONS.pop(user_id, None)
            return "❌ No upcoming appointments found for this phone number."

        response = "📋 *Your Upcoming Appointments*\n\n"
        for i, b in enumerate(bookings):
            response += f"{i+1}. {b['date']} at {b['time']}\n"
            response += f"   🏬 {b.get('salonName', 'Salon')}\n"
            # Display primary service or list of services if available
            services_list = b.get('services', [])
            if services_list:
                services_str = ", ".join([s.get('serviceName', 'Service') for s in services_list])
            else:
                services_str = b.get('service', 'Service')
            response += f"   💆 {services_str}\n\n"
        
        response += "To cancel or reschedule, please use the main menu options."
        
        SESSIONS.pop(user_id, None)
        return response

    return "Type HI to start."