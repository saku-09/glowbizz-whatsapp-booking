import os
import time
from datetime import datetime, timedelta

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

def get_salon_timings(salon_id, day):

    ref = db.reference(f"salonandspa/salons/{salon_id}/timings/{day}")

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

def get_booked_slots_from_salon_node(salon_id, date):

    date = normalize_date(date)

    ref = db.reference(f"salonandspa/salons/{salon_id}/slots/{date}")

    slots = ref.get() or {}

    booked = []

    for _, slot in slots.items():

        if slot.get("status") in ["booked", "confirmed"]:

            booked.append({
                "startTime": slot.get("startTime"),
                "endTime": slot.get("endTime")
            })

    return booked


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
        "createdAt": int(time.time()*1000)
    })

    return customer_id


# ============================================
# SAVE BOOKED SLOT
# ============================================

def save_booked_slot(salon_id, booking, appointment_id):

    date = normalize_date(booking["date"])

    slot_ref = db.reference(
        f"salonandspa/salons/{salon_id}/slots/{date}"
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

def save_whatsapp_booking(salon_id, booking_data):

    ref = db.reference(
        f"salonandspa/appointments/salon/{salon_id}"
    )

    customer_id = create_customer(booking_data["customer"])

    booking = {

        "appointmentId": "",

        "createdAt": int(time.time()*1000),

        "customerId": customer_id,

        "customer": booking_data["customer"],

        "placeId": booking_data["placeId"],

        "employeeId": booking_data["employeeId"],

        "services": booking_data["services"],

        "date": normalize_date(booking_data["date"]),

        "startTime": booking_data["startTime"],

        "totalAmount": booking_data.get("totalAmount",0),

        "totalDuration": booking_data.get("totalDuration",30),

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
        new_ref.key
    )

    return new_ref.key


# ============================================
# CANCEL APPOINTMENT
# ============================================

def cancel_appointment_and_cleanup(
        salon_id,
        appointment_id,
        date
):

    appt_ref = db.reference(
        f"salonandspa/appointments/salon/{salon_id}/{appointment_id}"
    )

    appt_ref.update({
        "status": "cancelled_by_customer"
    })

    slots_ref = db.reference(
        f"salonandspa/salons/{salon_id}/slots/{date}"
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

    ref = db.reference("salonandspa/appointments/salon")

    salons = ref.get() or {}

    latest = None
    latest_time = 0

    for salon_id, bookings in salons.items():

        for appointment_id, booking in bookings.items():

            if booking.get("status") != "confirmed":
                continue

            customer = booking.get("customer",{})

            if customer.get("phone")==phone and \
               customer.get("name","").lower()==name.lower():

                created = booking.get("createdAt",0)

                if created > latest_time:

                    latest_time = created

                    latest = {

                        "appointmentId": appointment_id,

                        "salonId": salon_id,

                        "ownerUid": booking.get("ownerUid"),

                        "date": booking.get("date"),

                        "startTime": booking.get("startTime"),

                        "salonName": booking.get("salonName"),

                        "serviceName": booking["services"][0]["serviceName"]
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

# =====================================================
# 🏬 GET SALONS BY CITY
# =====================================================

def get_salons_by_city(city):
    
    ref = db.reference("salonandspa/salons")

    salons = ref.get() or {}

    results = []

    city = city.strip().lower()

    for salon_id, salon in salons.items():

        address = str(salon.get("address", "")).lower()
        branch = str(salon.get("branch", "")).lower()
        name = salon.get("name") or salon.get("salonName") or branch

        if city in address or city in branch:

            results.append({
                "id": salon_id,
                "name": name,
                "address": salon.get("address") or salon.get("branch"),
                "ownerUid": salon.get("ownerUid")
            })

    print("CITY SEARCH:", city)
    print("SALONS FOUND:", results)

    return results


# =====================================================
# 💆 GET SERVICES BY SALON
# =====================================================

def get_services_by_salon(salon_id: str):

    ref = db.reference(
        f"salonandspa/salons/{salon_id}/services"
    )

    services = ref.get() or {}

    results = []

    for sid, s in services.items():

        results.append({
            "serviceId": sid,
            "serviceName": s.get("name"),
            "price": int(s.get("price", 0)),
            "duration": int(s.get("duration", 30))
        })

    return results


# =====================================================
# 👨‍💼 GET EMPLOYEES BY SALON
# =====================================================

def get_employees_by_salon(salon_id: str):

    ref = db.reference(
        f"salonandspa/salons/{salon_id}/employees"
    )

    employees = ref.get() or {}

    results = []

    for emp_id, emp in employees.items():

        if emp.get("isActive", True):

            results.append({
                "employeeId": emp_id,
                "name": emp.get("name", "Staff"),
                "phone": emp.get("phone", "")
            })

    return results