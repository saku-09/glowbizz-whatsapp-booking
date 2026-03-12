import os
import time
from datetime import datetime, timedelta

# global lock removed to support high concurrency

def normalize_phone(p):
    """Returns last 10 digits of a phone number for robust comparison."""
    if not p: return ""
    # Remove all non-numeric characters first
    p_str = "".join(c for c in str(p) if c.isdigit())
    return p_str[-10:] if len(p_str) >= 10 else p_str

from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, db

# ============================================
# LOAD ENV
# ============================================

load_dotenv()

# ============================================
# FIREBASE INIT
# ============================================

if not firebase_admin._apps:

    firebase_config = {
        "type": os.getenv("FIREBASE_TYPE"),
        "project_id": os.getenv("FIREBASE_PROJECT_ID"),
        "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
        "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
        "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
        "client_id": os.getenv("FIREBASE_CLIENT_ID"),
        "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
        "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_CERT_URL"),
        "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL"),
    }

    cred = credentials.Certificate(firebase_config)

    firebase_admin.initialize_app(cred, {
        "databaseURL": os.getenv("FIREBASE_DATABASE_URL")
    })

print("🔥 Firebase Connected")

# ============================================
# NORMALIZE DATE
# ============================================

def normalize_date(date):

    try:
        # Handle slashes if present
        date = date.replace("/", "-")
        
        if len(date.split("-")[0]) == 4:
            dt = datetime.strptime(date, "%Y-%m-%d")
        else:
            dt = datetime.strptime(date, "%d-%m-%Y")

        return dt.strftime("%d-%m-%Y")
    except:
        return None


# ============================================
# SALON TIMINGS
# ============================================

def get_salon_timings(salon_id, day, collection="salons"):

    ref = db.reference(f"salonandspa/{collection}/{salon_id}/timings/{day}")
    print("TIMINGS PATH:", f"salonandspa/{collection}/{salon_id}/timings/{day}")
    data = ref.get()
    print("TIMINGS DATA:", data)

    if not data:
        return None

    return {
        "isOpen": data.get("isOpen", True),
        "open": data.get("open"),
        "close": data.get("close")
    }


# ============================================
# BOOKED SLOTS
# ============================================

def get_booked_slots_from_salon_node(salon_id, date, collection="salons"):
    
    date = normalize_date(date)

    ref = db.reference(f"salonandspa/{collection}/{salon_id}/slots/{date}")

    slots_data = ref.get() or {}

    booked = []

    for slot in slots_data.values():

        if slot.get("status") in ["booked", "confirmed"]:

            start_time = slot.get("startTime")
            end_time = slot.get("endTime")
            emp_id = slot.get("employeeId")

            if start_time and end_time:
                booked.append({
                    "start": start_time,
                    "end": end_time,
                    "employeeId": emp_id
                })

    return booked

# ============================================
# CHECK SLOT AVAILABILITY (PREVENT DOUBLE BOOKING)
# ============================================

def get_available_employees_for_slot(salon_id, date, start_time, duration=30, collection="salons", booked_slots=None, active_employees=None):
    """
    Returns a list of employee objects who are FREE for the given time slot.
    """
    date = normalize_date(date)

    # 1. Past-time check
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    today_str = ist_now.strftime("%d-%m-%Y")

    if date == today_str:
        try:
            slot_time = datetime.strptime(start_time, "%H:%M").time()
            if slot_time <= ist_now.time():
                return []
        except:
            pass

    # 2. Get dependencies if not provided
    if active_employees is None:
        active_employees = get_employees_by_salon(salon_id, collection=collection)
    
    if not active_employees:
        return []

    if booked_slots is None:
        booked_slots = get_booked_slots_from_salon_node(salon_id, date, collection=collection)

    # 3. Calculate interval
    new_start = datetime.strptime(start_time, "%H:%M")
    slot_interval = 30 
    new_end = new_start + timedelta(minutes=max(duration, slot_interval))

    # 4. Identify busy employees
    busy_emp_ids = set()
    for slot in booked_slots:
        b_start = datetime.strptime(slot["start"], "%H:%M")
        b_end = datetime.strptime(slot["end"], "%H:%M")
        
        # Overlap check
        if new_start < b_end and b_start < new_end:
            if slot.get("employeeId"):
                busy_emp_ids.add(str(slot["employeeId"]))

    # 5. Return free employees
    free_employees = [
        emp for emp in active_employees 
        if str(emp["employeeId"]) not in busy_emp_ids
    ]

    return free_employees

def is_slot_available(salon_id, date, start_time, duration=30, collection="salons", booked_slots=None):
    """Legacy wrapper for backward compatibility or simple boolean checks."""
    free_emps = get_available_employees_for_slot(
        salon_id, date, start_time, duration, collection, booked_slots
    )
    return len(free_emps) > 0

def get_available_slots(salon_id, date, duration=30, collection="salons"):
    """
    Returns available HH:MM slots at 30-min intervals.
    Optimized: Fetches employees and booked slots ONCE and filters in-memory.
    """
    date = normalize_date(date)
    dt = datetime.strptime(date, "%d-%m-%Y")
    day_name = dt.strftime("%A").lower()

    # 1. Fetch all required data once
    timings = get_salon_timings(salon_id, day_name, collection=collection)
    if not timings or not timings.get("isOpen"):
        return []

    active_employees = get_employees_by_salon(salon_id, collection=collection)
    if not active_employees:
        return []

    booked = get_booked_slots_from_salon_node(salon_id, date, collection=collection)

    # 2. Potential slots at 30-minute intervals
    slot_interval = 30
    open_time = timings["open"]
    close_time = timings["close"]
    
    potential_slots_dt = []
    try:
        start_curr = datetime.strptime(open_time, "%H:%M")
        end_limit = datetime.strptime(close_time, "%H:%M")
        while start_curr + timedelta(minutes=slot_interval) <= end_limit:
            potential_slots_dt.append(start_curr)
            start_curr += timedelta(minutes=slot_interval)
    except:
        return []

    # Pre-parse booked slots for faster comparison
    booked_dt = []
    for b in booked:
        try:
            booked_dt.append({
                "start": datetime.strptime(b["start"], "%H:%M"),
                "end": datetime.strptime(b["end"], "%H:%M"),
                "employeeId": str(b["employeeId"]) if b.get("employeeId") else None
            })
        except: continue

    # 3. Filter slots
    free_slots = []
    
    # Pre-calculate active IDs
    active_emp_ids = [str(emp["employeeId"]) for emp in active_employees]

    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    today_str = ist_now.strftime("%d-%m-%Y")

    for slot_dt in potential_slots_dt:
        slot_start_str = slot_dt.strftime("%H:%M")
        
        # Past-time check
        if date == today_str and slot_dt.time() <= ist_now.time():
            continue

        # Check availability
        new_end = slot_dt + timedelta(minutes=max(duration, slot_interval))
        
        busy_emp_ids = set()
        for b in booked_dt:
            # Type safe overlap check for lints
            b_start = b.get("start")
            b_end = b.get("end")
            
            if not isinstance(b_start, datetime) or not isinstance(b_end, datetime):
                continue

            if slot_dt < b_end and b_start < new_end:
                if b.get("employeeId"):
                    busy_emp_ids.add(b["employeeId"])
        
        # If at least ONE active employee is not in busy_emp_ids
        if any(eid not in busy_emp_ids for eid in active_emp_ids):
            free_slots.append(slot_start_str)

    return free_slots

def find_customer_by_phone(phone):

    ref = db.reference("salonandspa/customer")
    customers_data = ref.get()

    if not isinstance(customers_data, dict):
        return None

    for cid, c in customers_data.items():
        if isinstance(c, dict) and normalize_phone(c.get("phone")) == normalize_phone(phone):
            return cid

    return None

def create_customer(customer):

    ref = db.reference("salonandspa/customer").push()

    customer_id = ref.key

    ref.set({
        "uid": customer_id,
        "name": customer.get("name"),
        "phone": customer.get("phone"),
        "gender": customer.get("gender"),
        "age": customer.get("age"),
        "role": "customer",   # ✅ added
        "createdAt": int(time.time()*1000)
    })

    return customer_id


# ============================================
# SAVE BOOKED SLOT
# ============================================

def save_booked_slot(salon_id, booking, appointment_id, collection="salons"):

    date = normalize_date(booking["date"])

    slot_ref = db.reference(
        f"salonandspa/{collection}/{salon_id}/slots/{date}"
    )

    start = datetime.strptime(
        f"{date} {booking['startTime']}",
        "%d-%m-%Y %H:%M"
    )

    end = start + timedelta(minutes=booking["totalDuration"])

    slots = slot_ref.get() or {}

    for s in slots.values():
        if s.get("employeeId") == booking["employeeId"] and s.get("startTime") == booking["startTime"]:
            raise Exception("Slot already booked")

    slot_ref.push({
        "appointmentId": appointment_id,
        "employeeId": booking["employeeId"],
        "serviceIds": [s["serviceId"] for s in booking["services"]],
        "startTime": booking["startTime"],
        "endTime": end.strftime("%H:%M"),
        "status": booking["status"],
        "customerName": booking["customer"]["name"]
    })


# ============================================
# SAVE WHATSAPP BOOKING
# ============================================

def save_whatsapp_booking(salon_id, booking_data, collection="salon"):
    
    # ── Removed lock to support high concurrency ──
    print("🔥 COLLECTION USED:", collection)
    print("🔥 APPOINTMENT PATH:", f"salonandspa/appointments/{collection}/{salon_id}")
    
    collection_plural = f"{collection}s"
    
    if not any(
        str(emp["employeeId"]) == str(booking_data.get("employeeId"))
        for emp in get_available_employees_for_slot(
            salon_id,
            booking_data["date"],
            booking_data["startTime"],
            duration=booking_data.get("totalDuration", 30),
            collection=collection_plural
        )
    ):
        return {
            "success": False,
            "message": "⚠️ This staff member was just booked. Please choose another slot."
        }

    ref = db.reference(
        f"salonandspa/appointments/{collection}/{salon_id}"
    )

    booking = {
        "appointmentId": "",
        "createdAt": int(time.time()*1000),
        "customer": booking_data["customer"],

        "salonId": salon_id,
        "salonName": booking_data.get("salonName"),

        "employeeId": booking_data["employeeId"],
        "services": booking_data["services"],

        "date": normalize_date(booking_data["date"]),
        "startTime": booking_data["startTime"],

        "totalAmount": booking_data.get("totalAmount", 0),
        "totalDuration": booking_data.get("totalDuration", 30),

        "status": "confirmed",
        "mode": "whatsapp",
        "ownerUid": booking_data.get("ownerUid")
    }

    new_ref = ref.push()
    booking["appointmentId"] = new_ref.key

    try:
        save_booked_slot(
            salon_id,
            booking,
            new_ref.key,
            collection=collection_plural
        )
    except Exception as e:
        return {
            "success": False,
            "message": "⚠️ This slot was just booked. Please choose another time."
        }

    new_ref.set(booking)

    return new_ref.key


# ============================================
# CANCEL APPOINTMENT
# ============================================

def cancel_appointment_and_cleanup(
        salon_id,
        appointment_id,
        date,
        collection="salon"
):
    # 1️⃣ Update appointment status only (SINGULAR)
    appt_ref = db.reference(
        f"salonandspa/appointments/{collection}/{salon_id}/{appointment_id}"
    )

    appt_ref.update({
        "status": "cancelled"
    })

    # 2️⃣ Delete slot from salon slots
    collection_plural = f"{collection}s"
    slots_ref = db.reference(
        f"salonandspa/{collection_plural}/{salon_id}/slots/{date}"
    )

    slots = slots_ref.get() or {}

    for slot_id, slot in slots.items():

        if slot.get("appointmentId") == appointment_id:

            slots_ref.child(slot_id).delete()

            print("✅ Slot removed:", slot_id)

            break


# ============================================
# FIND CUSTOMER BOOKING
# ============================================

def find_latest_active_booking_by_customer(
        phone,
        name=None
):

    search_phone = normalize_phone(phone)
    search_name = name.lower() if name else None

    latest = None
    latest_time = 0
    collections = ["salon", "spa"]

    for col in collections:
        
        ref = db.reference(f"salonandspa/appointments/{col}")
        all_bookings = ref.get() or {}

        # Handle both dict {salonId: {bookingId: data}} and list [{bookingId: data}]
        if isinstance(all_bookings, dict):
            salon_bookings_items = all_bookings.items()
        elif isinstance(all_bookings, list):
            salon_bookings_items = []
            for idx, val in enumerate(all_bookings):
                if val: salon_bookings_items.append((str(idx), val))
        else:
            continue

        for salon_id, bookings in salon_bookings_items:
            # Robust conversion of bookings node to dict
            if isinstance(bookings, list):
                temp = {}
                for idx, b in enumerate(bookings):
                    if b: temp[str(idx)] = b
                bookings = temp
                
            if not isinstance(bookings, dict):
                continue

            for appointment_id, booking in bookings.items():
                if not isinstance(booking, dict):
                    continue

                if booking.get("status") != "confirmed":
                    continue

                customer = booking.get("customer")
                if not isinstance(customer, dict): continue
                
                db_phone = normalize_phone(customer.get("phone"))
                customer_name = str(customer.get("name", "")).lower()

                # Match phone and (optionally) name
                phone_matches = (db_phone == search_phone)
                name_matches = True
                if search_name:
                    name_matches = (search_name in customer_name or customer_name in search_name)

                if phone_matches and name_matches:

                    created = booking.get("createdAt", 0)

                    if created > latest_time:

                        latest_time = created

                        latest = {
                            "appointmentId": appointment_id,
                            "salonId": salon_id,
                            "ownerUid": booking.get("ownerUid"),
                            "date": booking.get("date"),
                            "startTime": booking.get("startTime"),
                            "salonName": booking.get("salonName"),
                            "services": booking.get("services") or [],
                            "serviceName": (booking.get("services") or [{}])[0].get("serviceName", "Service"),
                            "customer": customer,
                            "customerName": customer.get("name"),
                            "customerPhone": customer.get("phone"),
                            "collection": col,
                            "totalDuration": booking.get("totalDuration", 30)
                        }

    return latest


def find_latest_past_booking_by_customer(
        phone,
        name=None
):
    search_phone = normalize_phone(phone)
    search_name = name.lower() if name else None

    latest = None
    latest_time = 0
    collections = ["salon", "spa"]
    
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    today = ist_now.date()

    for col in collections:
        
        ref = db.reference(f"salonandspa/appointments/{col}")
        all_bookings = ref.get() or {}

        # Handle both dict {salonId: {bookingId: data}} and list [{bookingId: data}]
        if isinstance(all_bookings, dict):
            salon_bookings_items = all_bookings.items()
        elif isinstance(all_bookings, list):
            salon_bookings_items = []
            for idx, val in enumerate(all_bookings):
                if val: salon_bookings_items.append((str(idx), val))
        else:
            continue

        for salon_id, bookings in salon_bookings_items:
            # Robust conversion of bookings node to dict
            if isinstance(bookings, list):
                temp = {}
                for idx, b in enumerate(bookings):
                    if b: temp[str(idx)] = b
                bookings = temp
                
            if not isinstance(bookings, dict):
                continue

            for appointment_id, booking in bookings.items():
                if not isinstance(booking, dict):
                    continue

                if booking.get("status") != "confirmed":
                    continue

                # ❌ Filter out today's and future bookings here
                b_date = booking.get("date")
                b_time = booking.get("startTime")
                if not b_date or not b_time:
                    continue
                
                try:
                    booking_dt = datetime.strptime(f"{b_date} {b_time}", "%d-%m-%Y %H:%M")
                    if booking_dt.date() >= today:
                        continue # Only keep past bookings
                except:
                    continue

                customer = booking.get("customer")
                if not isinstance(customer, dict): continue
                
                db_phone = normalize_phone(customer.get("phone"))
                customer_name = str(customer.get("name", "")).lower()

                # Match phone and (optionally) name
                phone_matches = (db_phone == search_phone)
                name_matches = True
                if search_name:
                    name_matches = (search_name in customer_name or customer_name in search_name)

                if phone_matches and name_matches:

                    created = booking.get("createdAt", 0)

                    if created > latest_time:

                        latest_time = created

                        latest = {
                            "appointmentId": appointment_id,
                            "salonId": salon_id,
                            "ownerUid": booking.get("ownerUid"),
                            "date": booking.get("date"),
                            "startTime": booking.get("startTime"),
                            "salonName": booking.get("salonName"),
                            "services": booking.get("services") or [],
                            "serviceName": (booking.get("services") or [{}])[0].get("serviceName", "Service"),
                            "customer": customer,
                            "customerName": customer.get("name"),
                            "customerPhone": customer.get("phone"),
                            "collection": col,
                            "totalDuration": booking.get("totalDuration", 30)
                        }

    return latest


# ============================================
# FIND OWNER UID
# ============================================

def find_owner_uid_by_salon(salon_id):

    ref = db.reference("salonandspa/admin")

    admins = ref.get() or {}

    for uid, admin in admins.items():

        for k,v in admin.items():

            if k.startswith("salonid") and v==salon_id:

                return uid

    return None


# ============================================
# GET OWNER PHONE
# ============================================

def get_owner_phone(owner_uid):

    if not owner_uid:
        return None

    ref = db.reference(f"salonandspa/admin/{owner_uid}")
    data = ref.get() or {}

    return data.get("phone")


# ============================================
# GET SALONS + SPAS BY CITY
# ============================================

def get_salons_by_city(city):

    city = city.lower().strip()

    salons_ref = db.reference("salonandspa/salons")
    spas_ref = db.reference("salonandspa/spas")

    salons = salons_ref.get() or {}
    spas = spas_ref.get() or {}

    # ── DIAGNOSTIC: print raw keys of first salon to identify field names ──
    if salons:
        first_key = next(iter(salons))
        print("🔍 RAW SALON KEYS:", list(salons[first_key].keys()))
        print("🔍 RAW SALON DATA:", salons[first_key])
    else:
        print("⚠️ No salons node found in Firebase at all!")
    # ─────────────────────────────────────────────────────────────────────────

    results = []

    # SALONS
    for salon_id, salon in salons.items():

    
        
        if not salon.get("activeSlot", False):  # Filter those without activeSlot: true
            continue

        address = str(salon.get("address", "")).lower()
        branch  = str(salon.get("branch",  "")).lower()
        city_field = str(salon.get("city", "")).lower()

        if city in address or city in branch or city in city_field:

            name    = salon.get("name") or salon.get("salonName") or "Salon"
            address_val = salon.get("address") or ""

            results.append({
                "id": salon_id,
                "name": name,
                "address": address_val,
                "ownerUid": salon.get("ownerUid"),
                "type": "salon"
            })

    # SPAS
    for spa_id, spa in spas.items():

       

        if not spa.get("activeSlot", False):  # Filter those without activeSlot: true
            continue

        address = str(spa.get("address", "")).lower()
        branch  = str(spa.get("branch",  "")).lower()
        city_field = str(spa.get("city", "")).lower()

        if city in address or city in branch or city in city_field:

            name    = spa.get("name") or spa.get("salonName") or "Spa"
            address_val = spa.get("address") or ""

            results.append({
                "id": spa_id,
                "name": name,
                "address": address_val,
                "ownerUid": spa.get("ownerUid"),
                "type": "spa"
            })

    print("SALONS/SPAS FOUND:", results)

    return results


# ============================================
# GET SERVICES
# ============================================

def get_services_by_salon(salon_id, collection="salons"):
    try:
        ref = db.reference(f"salonandspa/{collection}/{salon_id}/services")
        services_data = ref.get() or {}
        print("🔍 SERVICE FETCH PATH:", f"salonandspa/{collection}/{salon_id}/services")
        print("🔍 SERVICES RAW DATA:", services_data)

        results = []

        # Handle both dict {id: {data}} and list [{data}]
        if isinstance(services_data, dict):
            items = services_data.items()
        elif isinstance(services_data, list):
            items = []
            for idx, val in enumerate(services_data):
                if val: items.append((str(idx), val))
        else:
            return []

        for sid, s in items:
            if not isinstance(s, dict): continue
            if not s.get("isActive", True): continue

            results.append({
                "serviceId": sid,
                "serviceName": str(s.get("name") or s.get("serviceName") or "Service"),
                "price": int(s.get("price", 0)),
                "duration": int(s.get("duration", 30))
            })

        return results
    except Exception as e:
        print(f"❌ Error in get_services_by_salon: {e}")
    return []


# ============================================
# GET EMPLOYEES
# ============================================

def get_employees_by_salon(salon_id, collection="salons"):
    try:
        ref = db.reference(f"salonandspa/{collection}/{salon_id}/employees")
        emp_data = ref.get() or {}

        results = []
        
        if isinstance(emp_data, dict):
            items = emp_data.items()
        elif isinstance(emp_data, list):
            items = []
            for idx, val in enumerate(emp_data):
                if val: items.append((str(idx), val))
        else:
            return []

        for emp_id, emp in items:
            if not isinstance(emp, dict): continue
            if emp.get("isActive") is True:
                results.append({
                    "employeeId": emp_id,
                    "name": emp.get("name", "Staff"),
                    "phone": emp.get("phone", "")
                })

        return results
    except Exception as e:
        print(f"❌ Error in get_employees_by_salon: {e}")
        return []

# ============================================
# GET CUSTOMER ACTIVE BOOKINGS
# ============================================

def get_customer_active_bookings(phone):

    results = []

    collections = ["salon", "spa"]

    for col in collections:

        ref = db.reference(f"salonandspa/appointments/{col}")
        data = ref.get() or {}

        if isinstance(data, dict):
            salon_items = data.items()
        elif isinstance(data, list):
            salon_items = []
            for idx, val in enumerate(data):
                if val: salon_items.append((str(idx), val))
        else:
            continue

        for salon_id, bookings in salon_items:
            if not isinstance(bookings, dict):
                continue

            for appointment_id, booking in bookings.items():
                if not isinstance(booking, dict):
                    continue

                status = booking.get("status")
                if status not in ["confirmed", "completed", "cancelled"]:
                    continue

                customer = booking.get("customer", {})

                if normalize_phone(customer.get("phone")) != normalize_phone(phone):
                    continue

                results.append({
                    "appointmentId": appointment_id,
                    "salonId": salon_id,
                    "salonName": booking.get("salonName") or "Salon",
                    "date": booking.get("date"),
                    "time": booking.get("startTime"),
                    "services": booking.get("services") or [],
                    "service": (booking.get("services") or [{}])[0].get("serviceName", "Service"),
                    "collection": col,
                    "status": status,
                    "ownerUid": booking.get("ownerUid"),
                    "totalDuration": booking.get("totalDuration", 30)
                })
    return results            
# ============================================
# GET APPOINTMENTS NEEDING REMINDER
# ============================================
def get_appointments_for_reminder():

    utc_now = datetime.utcnow()
    now = utc_now + timedelta(hours=5, minutes=30)
    collections = ["salon", "spa"]
    results = []

    for col in collections:

        ref = db.reference(f"salonandspa/appointments/{col}")
        data = ref.get() or {}

        for salon_id, bookings in (data or {}).items():

            for appointment_id, booking in bookings.items():

                status = booking.get("status")

                if status not in ["confirmed", "booked"]: 
                    continue

                if booking.get("reminderSent"):
                    continue

                date = normalize_date(booking.get("date"))
                time_slot = booking.get("startTime")

                if not date or not time_slot:
                    continue
                
                # Check for today's date
                if date != now.strftime("%d-%m-%Y"):
                    continue

                try:
                    appointment_time = datetime.strptime(f"{date} {time_slot}", "%d-%m-%Y %H:%M")
                except ValueError:
                    print("Invalid date format:", date, time_slot)
                    continue

                diff_minutes = (appointment_time - now).total_seconds() / 60

                # send reminder 45 minutes before
                if 0 < diff_minutes <= 45:

                    # ==========================================
                    # FETCH MISSING DETAILS FOR NOTIFICATIONS
                    # ==========================================
                    business_col = f"{col}s"

                    # 1. Salon Name
                    s_name = booking.get("salonName")
                    if not s_name or s_name == "None":
                        s_node = db.reference(f"salonandspa/{business_col}/{salon_id}").get() or {}
                        booking["salonName"] = s_node.get("name") or s_node.get("salonName") or "Salon"

                    # 2. Staff Name
                    e_name = booking.get("employeeName")
                    emp_id = str(booking.get("employeeId", ""))
                    if (not e_name or e_name == "None") and emp_id and emp_id != "auto":
                        e_node = db.reference(f"salonandspa/employees/{emp_id}").get() or {}
                        if isinstance(e_node, dict) and e_node.get("name"):
                            booking["employeeName"] = e_node.get("name")
                            
                        if "employeeName" not in booking or not booking["employeeName"] or booking["employeeName"] == "None":
                             booking["employeeName"] = "Staff"

                    # 3. Service Name
                    services_list = booking.get("services") or []
                    if isinstance(services_list, list) and len(services_list) > 0:
                        serv_name = services_list[0].get("serviceName")
                        serv_id = str(services_list[0].get("serviceId", ""))
                        if (not serv_name or serv_name == "None") and serv_id:
                            all_servs = get_services_by_salon(salon_id, collection=business_col)
                            for srv in all_servs:
                                if str(srv.get("serviceId")) == serv_id:
                                    services_list[0]["serviceName"] = srv.get("serviceName")
                                    break
                            if "serviceName" not in services_list[0] or not services_list[0]["serviceName"] or services_list[0]["serviceName"] == "None":
                                services_list[0]["serviceName"] = "Service"
                        booking["services"] = services_list

                    results.append({
                        "appointmentId": appointment_id,
                        "salonId": salon_id,
                        "collection": col,
                        "booking": booking
                    })

    return results