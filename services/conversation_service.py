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
    get_available_employees_for_slot,
    cancel_appointment_and_cleanup,
    find_latest_active_booking_by_customer,
    find_owner_uid_by_salon,
    get_customer_active_bookings,
    normalize_phone
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
    """
    Randomly assigns an employee from the provided list.
    'employees' should now be pre-filtered to include only those FREE at 'time_slot'.
    """
    if not employees:
        return None

    # Load balancing using time slot hash
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
# GLOBAL RESTART & COMMAND INTERCEPTOR
# ==================================================

    RESTART_KEYWORDS = {"HI", "HII", "HIII", "HELLO", "HEY", "START", "RESTART", "MENU", "HOME"}
    
    # Direct button IDs or explicit commands
    DIRECT_COMMAND_MAP = {
        "BOOK": "CITY",
        "REBOOK": "MAIN_MENU",
        "RESCHEDULE": "RESCHEDULE_PHONE",
        "CANCEL": "CANCEL_PHONE",
        "MY_BOOKINGS": "MY_BOOKINGS_PHONE",
        "MORE_MENU": "MAIN_MENU"
    }

    if msg_upper in DIRECT_COMMAND_MAP:
        target_state = DIRECT_COMMAND_MAP[msg_upper]
        session["data"] = {} # Reset data for new flow
        
        # ⚡ Management Flows (Proactive Lookup)
        if msg_upper in ["CANCEL", "RESCHEDULE", "MY_BOOKINGS"]:
            phone = normalize_phone(user_id)
            has_booking = False
            
            if msg_upper == "MY_BOOKINGS":
                bookings = get_customer_active_bookings(phone)
                if bookings: has_booking = True
            else:
                booking = find_latest_active_booking_by_customer(phone=phone)
                if booking: has_booking = True

            if has_booking:
                session["state"] = target_state
                SESSIONS[user_id] = session
                # Safe recursion (phone number is not a command keyword)
                return handle_conversation(user_id, phone)
            
            # Fallback to manual entry prompt
            session["state"] = target_state
            SESSIONS[user_id] = session
            prompts = {
                "CANCEL": "Please enter your registered phone number to find your booking:",
                "RESCHEDULE": "📱 Please enter the phone number you used for your booking:",
                "MY_BOOKINGS": "📱 Please enter your phone number to view your appointments:"
            }
            return prompts.get(msg_upper, "Please enter your phone number:")

        # ⚡ Direct Navigation (BOOK)
        if msg_upper == "BOOK":
            session["state"] = "CITY"
            SESSIONS[user_id] = session
            return "📍 Please enter your City"

        # ⚡ Menu Navigation (Fallthrough)
        if msg_upper in ["REBOOK", "MORE_MENU"]:
            # Set state and message to fall through to the MAIN_MENU block below
            state = "MAIN_MENU"
            msg = msg_upper
            msg_upper = msg_upper
            session["state"] = "MAIN_MENU"
            SESSIONS[user_id] = session
        else:
            # For any other command, set state and return empty to let the engine handle it
            session["state"] = target_state
            SESSIONS[user_id] = session
            return ""

    if msg_upper in RESTART_KEYWORDS:

        SESSIONS.pop(user_id, None)   # clear any existing session
        SESSIONS[user_id] = {"state": "MAIN_MENU", "data": {}}

        result = send_whatsapp_buttons(
            user_id,
            "✨ *Welcome to NexSalon* ✨\n\nYour personal salon booking assistant 💇‍♀️\n\nChoose an option below 👇",
            [
                {"id": "BOOK", "title": "Book Appointment"},
                {"id": "CANCEL", "title": "Cancel Appointment"},
                {"id": "MORE_MENU", "title": "More Options"}
            ]
        )

        if not result:
            return "⚠️ Service temporarily unavailable. Please type HOME again."

        return ""


# ==================================================
# START MENU
# ==================================================

    if state == "START":

        session["state"] = "MAIN_MENU"
        SESSIONS[user_id] = session

        result = send_whatsapp_buttons(
            user_id,
            "✨ *Welcome to NexSalon* ✨\n\nYour personal salon booking assistant 💇‍♀️\n\nChoose an option below 👇",
            [
                {"id": "BOOK", "title": "Book Appointment"},
                {"id": "CANCEL", "title": "Cancel Appointment"},
                {"id": "MORE_MENU", "title": "More Options"}
            ]
        )

        if not result:
            return "⚠️ Service temporarily unavailable. Please type START."

        return ""


# ==================================================
# MAIN MENU
# ==================================================

    if state == "MAIN_MENU":

        if msg_upper == "MORE_MENU":
            send_whatsapp_buttons(
                user_id,
                "More options 👇",
                [
                    {"id": "MY_BOOKINGS", "title": "My Bookings"},
                    {"id": "REBOOK", "title": "Rebook Last"},
                    {"id": "RESCHEDULE", "title": "Reschedule"}
                ]
            )
            return ""

        if msg_upper in ["BOOK", "BOOK APPOINTMENT"]:

            session["state"] = "CITY"
            SESSIONS[user_id] = session

            return "📍 Please enter your City"

        elif msg_upper in ["REBOOK", "REBOOK LAST", "REBOOK LAST APPOINTMENT"]:

            # ⚡ 1-CLICK REBOOK IMPROVEMENT
            print(f"⚡ ATTEMPTING 1-CLICK REBOOK FOR {user_id}")
            booking = find_latest_active_booking_by_customer(phone=user_id)            
            if booking:
                data["last_booking"] = booking
                services = booking.get("services", [])
                
                # Fix Firebase dict structure
                if isinstance(services, dict):
                    services = list(services.values())
                
                data["selected_services"] = services
                data["salon"] = {"id": booking["salonId"], "name": booking["salonName"]}
                data["is_rebook"] = True
                data["collection"] = f"{booking.get('collection', 'salon')}s"
                data["business_type"] = booking.get('collection', 'salon')

                services_text_items = []
                for s in services:
                    if isinstance(s, dict) and s.get("serviceName"):
                        services_text_items.append(f"• {s['serviceName']}")
                    elif isinstance(s, str):
                        services_text_items.append(f"• {s}")
                
                services_text = "\n".join(services_text_items) if services_text_items else "No services"

                send_whatsapp_buttons(
                    user_id,
                    f"🔁 *Rebook Last Appointment*\n\n"
                    f"Previous Services:\n{services_text}\n\n"
                    f"What would you like to do?",
                    [
                        {"id": "AUTO_REBOOK", "title": "⚡ Quick Rebook"},
                        {"id": "CHANGE_SERVICE", "title": "Change Service"},
                        {"id": "NEW_BOOKING", "title": "New Booking"}
                    ]
                )
                session["state"] = "REBOOK_CONFIRM"
                SESSIONS[user_id] = session
                return ""

            # Fallback if no booking found for WhatsApp number
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

        if msg_upper == "SELECT_DATE_BACK":
            rows = generate_calendar_dates()
            return send_whatsapp_list(
                user_id,
                "📅 *Choose Appointment Date*\n\nSelect your preferred day 👇",
                rows
            )

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

        # ❌ NO SLOTS -> SMART DATE SUGGESTION
        if not free_slots:
            # Search for the nearest date with slots
            suggested_date = None
            for i in range(1, 8): # Check next 7 days
                check_dt = dt + timedelta(days=i)
                d_str = check_dt.strftime("%d-%m-%Y")
                alt_slots = get_available_slots(salon["id"], d_str, duration=total_duration, collection=collection)
                if alt_slots:
                    suggested_date = d_str
                    break
            
            if suggested_date:
                # Format date for display
                s_dt = datetime.strptime(suggested_date, "%d-%m-%Y")
                readable_date = s_dt.strftime("%A, %d %b")
                
                send_whatsapp_buttons(
                    user_id,
                    f"❗ *No slots available on {msg}.*\n\n"
                    f"Good news! We found available slots on *{readable_date}*.\n\n"
                    f"Would you like to check {readable_date} instead? 👇",
                    [
                        {"id": suggested_date, "title": f"See {readable_date}"},
                        {"id": "SELECT_DATE_BACK", "title": "Pick Another Date"}
                    ]
                )
                session["state"] = "SELECT_DATE" # Stay here to catch the button click as a date
            else:
                send_whatsapp_list(
                    user_id,
                    "❌ No slots available for the next 7 days. Please try a different salon or city.",
                    generate_calendar_dates()
                )

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

        # If this is rebook flow, skip personal questions
        if data.get("is_rebook"):

            booking = data["last_booking"]

            data["name"] = booking["customerName"]
            data["phone"] = booking["customerPhone"]
            data["gender"] = booking.get("customer", {}).get("gender", "Other")
            data["age"] = booking.get("customer", {}).get("age", "")

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
        services_text = "\n".join([f"• {s.get('serviceName', 'Service')}" for s in services if s and isinstance(s, dict)])
        
        def safe_int(val, default=0):
            try:
                if val is None: return default
                return int(float(str(val).replace(',', '')))
            except:
                return default

        total_amount = sum(safe_int(s.get("price")) for s in services if s and isinstance(s, dict))

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
            total_duration = sum(int(s.get("duration", 30)) for s in services if s and isinstance(s, dict))
            total_amount = sum(int(s.get("price", 0)) for s in services if s and isinstance(s, dict))

            business_type = data.get("business_type", "salon")
            collection_plural = data.get("collection", "salons")

            # 🛠️ OPTIMIZED MULTI-STAFF ASSIGNMENT
            # 1. Fetch all booked slots for this date
            booked_slots = get_booked_slots_from_salon_node(
                salon["id"], 
                data["date"], 
                collection=collection_plural
            )

            # 2. Get active employees for this salon
            active_employees = find_employees_by_salon(
                salon["id"], 
                collection=collection_plural
            )

            # 3. Identify who is specifically FREE for this time slot
            free_employees = get_available_employees_for_slot(
                salon["id"],
                data["date"],
                data["time"],
                duration=total_duration,
                collection=collection_plural,
                booked_slots=booked_slots,
                active_employees=active_employees
            )

            # 4. Auto Assignment from the FREE pool
            employee = auto_assign_employee(free_employees, data["time"])

            if not employee:
                return "⚠️ Sorry, all staff members have just been booked at this time. Please choose another slot."

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
                "employeeId": employee["employeeId"],
                "employeeName": employee["name"],
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
                    {"id": "REBOOK", "title": "Rebook Last"},
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
        print(f"\n🔍 DEBUG REBOOK PHONE: {msg}")
        
        booking = find_latest_active_booking_by_customer(
            phone=msg
        )

        print(f"🔍 BOOKING RESULT FOUND: {True if booking else False}")

        if not booking:
            return "❌ No previous booking found for this phone number."

        data["last_booking"] = booking
        services = booking.get("services", [])

        if isinstance(services, dict):
            services = list(services.values())

        data["selected_services"] = services
        data["salon"] = {"id": booking["salonId"], "name": booking["salonName"]}
        
        data["is_rebook"] = True  # Flag to skip personal questions later

        # Determine collection type from booking info if possible, else default
        data["collection"] = f"{booking.get('collection', 'salon')}s"
        data["business_type"] = booking.get('collection', 'salon')

        services_list = data.get("selected_services", [])
        services_text_items = []
        for s in services_list:
            if isinstance(s, dict) and s.get("serviceName"):
                services_text_items.append(f"• {s['serviceName']}")
            elif isinstance(s, str):
                services_text_items.append(f"• {s}")
        
        services_text = "\n".join(services_text_items) if services_text_items else "No services"

        result = send_whatsapp_buttons(
            user_id,
            f"🔁 *Rebook Last Appointment*\n\n"
            f"Previous Services:\n{services_text}\n\n"
            f"What would you like to do?",
            [
                {"id": "AUTO_REBOOK", "title": "⚡ Quick Rebook"},
                {"id": "CHANGE_SERVICE", "title": "Change Service"},
                {"id": "NEW_BOOKING", "title": "New Booking"}
            ]
        )

        if not result:
            return "⚠️ Service temporarily unavailable. Please try REBOOK again."

        session["state"] = "REBOOK_CONFIRM"
        SESSIONS[user_id] = session
        return ""

    if state == "REBOOK_NAME":
        print(f"\n🔍 DEBUG REBOOK PHONE: {data.get('rebook_phone')}")
        print(f"🔍 DEBUG REBOOK NAME: {msg}")

        booking = find_latest_active_booking_by_customer(
            phone=data["rebook_phone"],
            name=msg
        )

        print(f"🔍 BOOKING RESULT FOUND: {True if booking else False}")

        if not booking:
            return "❌ No previous booking found for this name and phone."

        data["last_booking"] = booking
        services = booking.get("services", [])

        # Fix Firebase dict structure
        if isinstance(services, dict):
            services = list(services.values())

        data["selected_services"] = services
        data["salon"] = {"id": booking["salonId"], "name": booking["salonName"]}
        
        data["is_rebook"] = True  # Flag to skip personal questions later

        # Determine collection type from booking info if possible, else default
        data["collection"] = f"{booking.get('collection', 'salon')}s"
        data["business_type"] = booking.get('collection', 'salon')

        services_text = "\n".join(
            f"• {s['serviceName']}" for s in data["selected_services"]
        )

        result = send_whatsapp_buttons(
            user_id,
            f"🔁 *Rebook Last Appointment*\n\n"
            f"Previous Services:\n{services_text}\n\n"
            f"What would you like to do?",
            [
                {"id": "AUTO_REBOOK", "title": "⚡ Rebook Same (Auto)"},
                {"id": "CHANGE_SERVICE", "title": "Choose Another Service"},
                {"id": "NEW_BOOKING", "title": "Book Completely New"}
            ]
        )

        if not result:
            return "⚠️ Service temporarily unavailable. Please try REBOOK again."

        session["state"] = "REBOOK_CONFIRM"
        SESSIONS[user_id] = session
        return ""

    if state == "REBOOK_CONFIRM":

        # 1️⃣ AUTO REBOOK (automatic date + slot)
        if msg_upper == "AUTO_REBOOK":

            booking = data["last_booking"]
            salon_id = booking["salonId"]
            collection = f"{booking.get('collection','salon')}s"
            
            services = booking.get("services", [])

            # Fix Firebase dict structure
            if isinstance(services, dict):
                services = list(services.values())

            duration = int(booking.get("totalDuration", 30))

            # check next 7 days automatically
            found_date = None
            found_slot = None

            for i in range(7):
                date_str = (datetime.now() + timedelta(days=i)).strftime("%d-%m-%Y")
                slots = get_available_slots(
                    salon_id,
                    date_str,
                    duration=duration,
                    collection=collection
                )
                if slots:
                    found_date = date_str
                    found_slot = slots[0]
                    break

            if not found_date:
                return "❌ No slots available in the next 7 days."

            data["date"] = found_date
            data["time"] = found_slot

            # Skip questions and show summary directly
            data["name"] = booking["customerName"]
            data["phone"] = booking["customerPhone"]
            data["gender"] = booking.get("customer", {}).get("gender", "Other")
            data["age"] = booking.get("customer", {}).get("age", "")

            services_text_items = []
            for s in services:
                if isinstance(s, dict) and s.get("serviceName"):
                    services_text_items.append(f"• {s['serviceName']}")
                elif isinstance(s, str):
                    services_text_items.append(f"• {s}")
            
            services_text = "\n".join(services_text_items) if services_text_items else "No services"
            total_amount = 0
            for s in services:
                if isinstance(s, dict):
                    total_amount += int(s.get("price", 0))

            summary = (
                "⚡ *Auto Slot Found*\n\n"
                "📋 *Appointment Summary*\n\n"
                f"👤 Name: {data['name']}\n"
                f"📱 Phone: {data['phone']}\n"
                f"⚧ Gender: {data['gender']}\n"
                f"🎂 Age: {data['age']}\n\n"
                f"🏬 Salon: {booking['salonName']}\n"
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
                [{"id": "CONFIRM", "title": "Confirm"}]
            )
            return ""

        # 2️⃣ CHANGE SERVICE
        elif msg_upper == "CHANGE_SERVICE":

            data["selected_services"] = []
            all_services = find_services_by_salon(data["salon"]["id"], collection=data["collection"])
            
            if not all_services:
                return "❌ Could not fetch services for this salon."
            
            data["services"] = all_services
            data["service_page"] = 0
            
            session["state"] = "SELECT_SERVICE"
            SESSIONS[user_id] = session

            return _send_service_page(user_id, all_services, 0)

        # 3️⃣ COMPLETELY NEW BOOKING
        elif msg_upper == "NEW_BOOKING":
            data.pop("is_rebook", None)
            session["state"] = "CITY"
            SESSIONS[user_id] = session
            return "📍 Please enter your City"

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
        
        # cancel old booking
        cancel_appointment_and_cleanup(
            salon_id=booking["salonId"],
            appointment_id=booking["appointmentId"],
            date=booking["date"],
            collection=booking.get("collection", "salon")
        )

        services = booking.get("services", [])
        total_duration = int(booking.get("totalDuration", 30))
        total_amount = sum(int(s.get("price", 0)) for s in services)
        owner_uid = find_owner_uid_by_salon(booking["salonId"])

        # 🛠️ OPTIMIZED MULTI-STAFF ASSIGNMENT FOR RESCHEDULE
        # 1. Fetch data
        collection_plural = f"{booking.get('collection', 'salon')}s"
        booked_slots = get_booked_slots_from_salon_node(
            booking["salonId"], 
            data["reschedule_date"], 
            collection=collection_plural
        )
        active_employees = find_employees_by_salon(
            booking["salonId"], 
            collection=collection_plural
        )

        # 2. Identify specifically FREE staff for the new time
        free_employees = get_available_employees_for_slot(
            booking["salonId"],
            data["reschedule_date"],
            msg,
            duration=total_duration,
            collection=collection_plural,
            booked_slots=booked_slots,
            active_employees=active_employees
        )

        # 3. Auto-Assign
        employee = auto_assign_employee(free_employees, msg)

        if not employee:
            return "⚠️ Sorry, all staff members have just been booked at this time. Please choose another slot."

        # Construct new booking with proper customer object
        new_booking = {
            "customer": {
                "name": booking["customerName"],
                "phone": booking["customerPhone"],
                "gender": booking.get("customer", {}).get("gender", ""),
                "age": booking.get("customer", {}).get("age", "")
            },
            "placeId": booking["salonId"],
            "salonName": booking.get("salonName"),
            "employeeId": employee["employeeId"],
            "employeeName": employee["name"],
            "services": services,
            "totalDuration": total_duration,
            "totalAmount": total_amount,
            "date": data["reschedule_date"],
            "startTime": msg,
            "status": "confirmed",
            "ownerUid": owner_uid
        }

        result = save_whatsapp_booking(
            booking["salonId"],
            new_booking,
            collection=booking.get("collection", "salon")
        )

        if isinstance(result, dict) and result.get("success") == False:
            return result["message"]

        SESSIONS.pop(user_id, None)
        return (
            "✅ *Appointment Rescheduled Successfully!*\n\n"
            f"📅 New Date: {data['reschedule_date']}\n"
            f"⏰ New Time: {msg}\n\n"
            "Your appointment has been successfully updated."
        )


# ==================================================
# MY BOOKINGS FLOW
# ==================================================

    if state == "MY_BOOKINGS_PHONE":
        bookings = get_customer_active_bookings(msg)

        if not bookings:
            SESSIONS.pop(user_id, None)
            return "❌ No appointments found for this phone number."

        response = "📋 *Your Appointments*\n\n"

        now = datetime.now()

        upcoming = []
        past = []
        cancelled = []

        for b in bookings:
            if b.get("status") == "cancelled":
                cancelled.append(b)
                continue

            try:
                dt = datetime.strptime(
                    f"{b['date']} {b['time']}",
                    "%d-%m-%Y %H:%M"
                )

                if dt >= now:
                    upcoming.append(b)
                else:
                    past.append(b)

            except:
                upcoming.append(b)

        # =========================
        # UPCOMING BOOKINGS
        # =========================

        if upcoming:

            response += "🟢 *Upcoming Appointments*\n\n"

            for b in upcoming:

                services_list = b.get("services", [])

                services_str = ", ".join(
                    [s.get("serviceName","Service") for s in services_list]
                )

                response += (
                    f"📅 {b['date']} ⏰ {b['time']}\n"
                    f"🏬 {b.get('salonName','Salon')}\n"
                    f"💆 {services_str}\n\n"
                )

        # =========================
        # PAST BOOKINGS
        # =========================

        if past:

            response += "⚪ *Past Appointments*\n\n"

            for b in past:

                services_list = b.get("services", [])

                services_str = ", ".join(
                    [s.get("serviceName","Service") for s in services_list]
                )

                response += (
                    f"📅 {b['date']} ⏰ {b['time']}\n"
                    f"🏬 {b.get('salonName','Salon')}\n"
                    f"💆 {services_str}\n\n"
                )

        # =========================
        # CANCELLED BOOKINGS
        # =========================

        if cancelled:

            response += "🔴 *Cancelled Appointments*\n\n"

            for b in cancelled:

                services_list = b.get("services", [])

                services_str = ", ".join(
                    [s.get("serviceName","Service") for s in services_list]
                )

                response += (
                    f"📅 {b['date']} ⏰ {b['time']}\n"
                    f"🏬 {b.get('salonName','Salon')}\n"
                    f"💆 {services_str}\n\n"
                )

        send_whatsapp_buttons(
            user_id,
            response,
            [
                {"id": "RESCHEDULE", "title": "Reschedule"},
                {"id": "CANCEL", "title": "Cancel Booking"}
            ]
        )

        SESSIONS.pop(user_id, None)

        return ""

    return "Type HI to start."