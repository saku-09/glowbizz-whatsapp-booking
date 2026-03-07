import os
import time
import threading
from datetime import datetime, timedelta

# One lock per (salon_id, date, start_time) would be ideal but a single
# global lock is simpler and safe — booking confirmations are rare events.
_booking_lock = threading.Lock()

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

    data = ref.get()

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

            if start_time and end_time:
                booked.append({
                    "start": start_time,
                    "end": end_time
                })

    return booked

# ============================================
# CHECK SLOT AVAILABILITY (PREVENT DOUBLE BOOKING)
# ============================================

def is_slot_available(salon_id, date, start_time, duration=30, collection="salons"):

    date = normalize_date(date)

    booked_slots = get_booked_slots_from_salon_node(salon_id, date, collection=collection)

    new_start = datetime.strptime(start_time, "%H:%M")
    new_end = new_start + timedelta(minutes=duration)

    for slot in booked_slots:
        
        b_start = datetime.strptime(slot["start"], "%H:%M")
        b_end = datetime.strptime(slot["end"], "%H:%M")

        # Overlap check: (start1 < end2) and (start2 < end1)
        if new_start < b_end and b_start < new_end:
            return False

    return True

# ============================================
# CREATE CUSTOMER
# ============================================

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

    slot_ref.push({

        "appointmentId": appointment_id,
        "employeeId": booking["employeeId"],
        "serviceId": booking["services"][0]["serviceId"],
        "startTime": booking["startTime"],
        "endTime": end.strftime("%H:%M"),
        "status": booking["status"],
        "customerId": booking["customerId"],
        "customerName": booking["customer"]["name"]
    })


# ============================================
# SAVE WHATSAPP BOOKING
# ============================================

def save_whatsapp_booking(salon_id, booking_data, collection="salons"):

    with _booking_lock:
        # ── ATOMIC: check + save under one lock so two users can't grab the same slot ──

        if not is_slot_available(
            salon_id,
            booking_data["date"],
            booking_data["startTime"],
            duration=booking_data.get("totalDuration", 30),
            collection=collection
        ):
            return {
                "success": False,
                "message": "⚠️ This slot was just booked. Please choose another time."
            }

        ref = db.reference(
            f"salonandspa/appointments/{collection}/{salon_id}"
        )

        customer_id = create_customer(booking_data["customer"])

        booking = {

            "appointmentId": "",
            "createdAt": int(time.time()*1000),
            "customerId": customer_id,
            "customer": booking_data["customer"],

            "placeId": salon_id,
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

        new_ref.set(booking)

        save_booked_slot(
            salon_id,
            booking,
            new_ref.key,
            collection=collection
        )

        return new_ref.key


# ============================================
# CANCEL APPOINTMENT
# ============================================

def cancel_appointment_and_cleanup(
        salon_id,
        appointment_id,
        date,
        collection="salons"
):

    appt_ref = db.reference(
        f"salonandspa/appointments/{collection}/{salon_id}/{appointment_id}"
    )

    appt_ref.update({
        "status": "cancelled_by_customer"
    })

    slots_ref = db.reference(
        f"salonandspa/{collection}/{salon_id}/slots/{date}"
    )

    slots = slots_ref.get() or {}

    for slot_id, slot in slots.items():

        if slot.get("appointmentId") == appointment_id:

            slots_ref.child(slot_id).delete()
            break


# ============================================
# FIND CUSTOMER BOOKING
# ============================================

def find_latest_active_booking_by_customer(
        phone,
        name
):

    latest = None
    latest_time = 0

    collections = ["salons", "spas"]

    for col in collections:
        
        ref = db.reference(f"salonandspa/appointments/{col}")
        all_bookings = ref.get() or {}

        for salon_id, bookings in all_bookings.items():

            for appointment_id, booking in bookings.items():

                if booking.get("status") != "confirmed":
                    continue

                customer = booking.get("customer", {})

                if customer.get("phone") == phone and \
                   customer.get("name", "").lower() == name.lower():

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
                            "serviceName": booking["services"][0]["serviceName"],
                            "collection": col
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

        if not salon.get("isActive", True):  # Filter inactive
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

        if not spa.get("isActive", True):  # Filter inactive
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

    ref = db.reference(
        f"salonandspa/{collection}/{salon_id}/services"
    )

    services = ref.get() or {}

    results = []

    for sid, s in services.items():

        if not s.get("isActive", True):  # Filter inactive
            continue

        results.append({
            "serviceId": sid,
            "serviceName": s.get("name"),
            "price": int(s.get("price",0)),
            "duration": int(s.get("duration",30))
        })

    return results


# ============================================
# GET EMPLOYEES
# ============================================

def get_employees_by_salon(salon_id, collection="salons"):

    ref = db.reference(
        f"salonandspa/{collection}/{salon_id}/employees"
    )

    employees = ref.get() or {}

    results = []

    for emp_id, emp in employees.items():

        if emp.get("isActive",True):

            results.append({
                "employeeId": emp_id,
                "name": emp.get("name","Staff"),
                "phone": emp.get("phone","")
            })

    return results