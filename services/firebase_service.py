import time
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, db

from services.notification_service import build_appointment_message
from services.whatsapp_service import send_whatsapp_message


# =====================================================
# 🔥 Initialize Firebase (ONLY ONCE)
# =====================================================
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://salonandspa-7b832-default-rtdb.firebaseio.com/"
    })

print("🔥 Firebase initialized successfully")


# =====================================================
# 🧑‍💼 SAVE OWNER LEAD
# =====================================================
def save_owner_lead(lead_data: dict):
    ref = db.reference("salonandspa/leads")

    lead_data["createdAt"] = int(time.time() * 1000)
    lead_data["status"] = "new"
    lead_data["source"] = "whatsapp"

    new_ref = ref.push(lead_data)
    new_ref.update({"leadId": new_ref.key})

    return new_ref.key


# =====================================================
# 🏬 GET SALONS BY CITY
# =====================================================
def get_salons_by_city(city: str):
    ref = db.reference("salonandspa/salons")
    all_salons = ref.get() or {}

    results = []

    for salon_id, salon in all_salons.items():
        address_raw = salon.get("address", "")
        branch_raw = salon.get("branch", "")
        name_raw = salon.get("name") or salon.get("salonName") or ""

        address = address_raw.lower()
        branch = branch_raw.lower()

        if city.lower() in address or city.lower() in branch:
            display_name = name_raw or branch_raw or "Unknown Salon"
            short_address = branch_raw or address_raw

            results.append({
                "id": salon_id,
                "name": display_name.strip(),
                "address": short_address.strip(),
                "ownerUid": salon.get("ownerUid")  # 🔥 MUST exist in DB
            })

    return results


# =====================================================
# 💆 GET SERVICES OF ONE SALON
# =====================================================
def get_services_by_salon(salon_id: str):
    ref = db.reference(f"salonandspa/salons/{salon_id}/services")
    services = ref.get() or {}

    results = []

    for service_id, service in services.items():
        results.append({
            "serviceId": service_id,
            "serviceName": service.get("name"),
            "price": int(service.get("price") or 0),
            "duration": int(service.get("duration") or 0)
        })

    return results


# =====================================================
# 👨‍💼 GET EMPLOYEES OF SALON
# =====================================================
def get_employees_by_salon(salon_id: str):
    try:
        ref = db.reference(f"salonandspa/salons/{salon_id}/employees")
        data = ref.get() or {}

        employees = []
        for emp_id, emp in data.items():
            if emp.get("isActive", True):
                employees.append({
                    "employeeId": emp_id,
                    "name": emp.get("name", "Staff"),
                    "phone": emp.get("phone", "")
                })

        print(f"🔥 Employees fetched for salon {salon_id}: {employees}")
        return employees

    except Exception as e:
        print("❌ Error fetching employees:", e)
        return []


# =====================================================
# 🕒 GET SALON TIMINGS FOR A DAY
# =====================================================
def get_salon_timings(salon_id: str, day_name: str):
    try:
        ref = db.reference(f"salonandspa/salons/{salon_id}/timings/{day_name}")
        timings = ref.get()

        if not timings:
            return None

        return {
            "isOpen": timings.get("isOpen", True),
            "open": timings.get("open"),
            "close": timings.get("close")
        }

    except Exception as e:
        print("❌ Error fetching salon timings:", e)
        return None


# =====================================================
# 🔹 NORMALIZE DATE
# =====================================================
def normalize_date(raw_date: str):
    if not raw_date:
        return None

    raw_date = raw_date.strip()

    try:
        if len(raw_date.split("-")[0]) == 2:
            dt = datetime.strptime(raw_date, "%d-%m-%Y")
        else:
            dt = datetime.strptime(raw_date, "%Y-%m-%d")

        return dt.strftime("%d-%m-%Y")

    except Exception as e:
        print("⛔ Date normalization failed:", raw_date, e)
        return None


# =====================================================
# 🔎 GET BOOKED SLOTS FOR DATE
# =====================================================
def get_booked_slots_for_date(salon_id: str, date: str):
    try:
        normalized_date = normalize_date(date)
        if not normalized_date:
            return []

        ref = db.reference(f"salonandspa/appointments/salon/{salon_id}")
        all_appointments = ref.get() or {}

        booked_times = []

        for _, appt in all_appointments.items():
            appt_date_norm = normalize_date(appt.get("date", ""))
            if appt_date_norm != normalized_date:
                continue

            status = appt.get("status")
            if status not in ["confirmed", "booked", "paid"]:
                continue

            start_time = appt.get("startTime")
            if start_time:
                booked_times.append(start_time)

        return booked_times

    except Exception as e:
        print("❌ Error fetching booked slots:", e)
        return []


# =====================================================
# 🔥 CHECK SLOT AVAILABLE (PER EMPLOYEE)
# =====================================================
def is_slot_available(salon_id, employee_id, date, start_time, duration) -> bool:
    normalized_date = normalize_date(date)
    if not normalized_date:
        return False

    appt_ref = db.reference(f"salonandspa/appointments/salon/{salon_id}")
    all_appointments = appt_ref.get() or {}

    try:
        req_start = datetime.strptime(
            f"{normalized_date} {start_time}", "%d-%m-%Y %H:%M"
        )
    except:
        return False

    req_end = req_start + timedelta(minutes=int(duration))

    for _, appt in all_appointments.items():

        # 🔥 Only same employee matters
        if appt.get("employeeId") != employee_id:
            continue

        if appt.get("status") not in ["confirmed", "booked", "paid"]:
            continue

        if normalize_date(appt.get("date", "")) != normalized_date:
            continue

        appt_start_time = appt.get("startTime")
        appt_duration = appt.get("totalDuration") or 0

        try:
            appt_start = datetime.strptime(
                f"{normalized_date} {appt_start_time}", "%Y-%m-%d %H:%M"
            )
        except:
            continue

        appt_end = appt_start + timedelta(minutes=int(appt_duration))

        # Overlap check
        if req_start < appt_end and req_end > appt_start:
            return False

    return True


# =====================================================
# 📞 GET OWNER & EMPLOYEE PHONE (SAFE VERSION)
# =====================================================
def get_owner_and_employee_phone(salon_id: str, owner_uid: str, emp_id: str):
    try:
        owner_phone = None
        emp_phone = None

        # Owner phone
        if owner_uid:
            owner_ref = db.reference(f"salonandspa/admin/{owner_uid}/phone")
            owner_phone = owner_ref.get()

        # Employee phone
        emp_ref = db.reference(
            f"salonandspa/salons/{salon_id}/employees/{emp_id}/phone"
        )
        emp_phone = emp_ref.get()

        print("📞 Owner phone:", owner_phone)
        print("📞 Employee phone:", emp_phone)

        return owner_phone, emp_phone

    except Exception as e:
        print("❌ Error fetching phones:", e)
        return None, None


# =====================================================
# 📲 SAVE WHATSAPP BOOKING + NOTIFY
# =====================================================
def save_whatsapp_booking(salon_id: str, booking_data: dict):
    ref = db.reference(f"salonandspa/appointments/salon/{salon_id}")

    booking = {
        "appointmentId": "",
        "createdAt": int(time.time() * 1000),

        "customer": booking_data["customer"],

        "placeId": booking_data["placeId"],
        "employeeId": booking_data["employeeId"],
        "services": booking_data["services"],

        "date": booking_data["date"],
        "startTime": booking_data["startTime"],

        "totalAmount": booking_data["totalAmount"],
        "totalDuration": booking_data["totalDuration"],

        "paymentStatus": booking_data.get("paymentStatus", "pending"),
        "status": booking_data.get("status", "confirmed"),

        "mode": "whatsapp",
        "type": "salon"
    }

    new_ref = ref.push()
    booking["appointmentId"] = new_ref.key
    new_ref.set(booking)

    print("🔥 WhatsApp booking saved:", new_ref.key)

    # ===============================
    # 🔔 SEND WHATSAPP NOTIFICATION
    # ===============================
    try:
        owner_uid = booking_data.get("ownerUid")
        employee_id = booking_data.get("employeeId")

        owner_phone, emp_phone = get_owner_and_employee_phone(
            salon_id=salon_id,
            owner_uid=owner_uid,
            emp_id=employee_id
        )

        message = build_appointment_message({
            "customer_name": booking["customer"]["name"],
            "customer_phone": booking["customer"]["phone"],
            "email": booking["customer"].get("email", ""),
            "age": booking["customer"].get("age", ""),
            "gender": booking["customer"].get("gender", ""),

            "salon_name": booking_data.get("salonName"),
            "branch": booking_data.get("branch"),
            "employee_name": booking_data.get("employeeName"),
            "service_name": booking_data["services"][0].get("serviceName", ""),
            "slot_time": booking["startTime"],
            "date": booking["date"]
        })

        if owner_phone:
            send_whatsapp_message(owner_phone, message)
        else:
            print("⚠️ Owner phone missing, WhatsApp not sent to owner")

        if emp_phone:
            send_whatsapp_message(emp_phone, message)
        else:
            print("⚠️ Employee phone missing, WhatsApp not sent to employee")

        print("✅ WhatsApp notification process completed")

    except Exception as e:
        print("❌ Error sending WhatsApp notification:", e)

    return new_ref.key
