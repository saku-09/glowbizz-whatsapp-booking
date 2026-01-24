import time
from datetime import datetime, timedelta

import firebase_admin
from firebase_admin import credentials, db


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
# 🔹 NORMALIZE DATE → ALWAYS DD-MM-YYYY
# =====================================================
def normalize_date(raw_date: str):
    try:
        # If starts with year → YYYY-MM-DD
        if len(raw_date.split("-")[0]) == 4:
            dt = datetime.strptime(raw_date, "%Y-%m-%d")
        else:
            dt = datetime.strptime(raw_date, "%d-%m-%Y")

        return dt.strftime("%d-%m-%Y")   # 🔥 FINAL FORMAT

    except Exception as e:
        print("⛔ Date normalize failed:", raw_date, e)
        return None


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

        if city.lower() in address_raw.lower() or city.lower() in branch_raw.lower():
            results.append({
                "id": salon_id,
                "name": name_raw or branch_raw or "Unknown Salon",
                "address": branch_raw or address_raw,
                "ownerUid": salon.get("ownerUid")
            })

    return results


# =====================================================
# 💆 GET SERVICES BY SALON
# =====================================================
def get_services_by_salon(salon_id: str):
    ref = db.reference(f"salonandspa/salons/{salon_id}/services")
    services = ref.get() or {}

    results = []

    for sid, s in services.items():
        results.append({
            "serviceId": sid,
            "serviceName": s.get("name"),
            "price": int(s.get("price") or 0),
            "duration": int(s.get("duration") or 0)   # minutes
        })

    return results


# =====================================================
# 👨‍💼 GET EMPLOYEES BY SALON
# =====================================================
def get_employees_by_salon(salon_id: str):
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

    return employees


# =====================================================
# 🕒 GET SALON TIMINGS
# =====================================================
def get_salon_timings(salon_id: str, day_name: str):
    try:
        ref = db.reference(f"salonandspa/salons/{salon_id}/timings/{day_name}")
        timings = ref.get()

        if not timings:
            return None

        return {
            "isOpen": timings.get("isOpen", True),
            "open": timings.get("open"),    # "10:00"
            "close": timings.get("close")  # "18:00"
        }

    except Exception as e:
        print("❌ Error fetching salon timings:", e)
        return None


# =====================================================
# 🔎 READ BOOKED SLOTS FROM SALON SLOTS NODE
# =====================================================
def get_booked_slots_from_salon_node(salon_id: str, date: str):
    try:
        normalized_date = normalize_date(date)
        if not normalized_date:
            return []

        ref = db.reference(f"salonandspa/salons/{salon_id}/slots/{normalized_date}")
        data = ref.get() or {}

        booked = []

        for _, slot in data.items():
            if slot.get("status") not in ["booked", "confirmed"]:
                continue

            start = slot.get("startTime")
            end = slot.get("endTime")

            if start and end:
                booked.append({
                    "startTime": start,
                    "endTime": end
                })

        return booked

    except Exception as e:
        print("❌ Error reading salon slots:", e)
        return []


# =====================================================
# 🔥 CHECK SLOT AVAILABLE
# =====================================================
def is_slot_available(salon_id, employee_id, date, start_time, duration) -> bool:
    normalized_date = normalize_date(date)
    if not normalized_date:
        return False

    booked_slots = get_booked_slots_from_salon_node(salon_id, normalized_date)

    try:
        req_start = datetime.strptime(
            f"{normalized_date} {start_time}", "%d-%m-%Y %H:%M"
        )
    except:
        print("⛔ Invalid requested time:", normalized_date, start_time)
        return False

    req_end = req_start + timedelta(minutes=int(duration))

    for b in booked_slots:
        try:
            booked_start = datetime.strptime(
                f"{normalized_date} {b['startTime']}", "%d-%m-%Y %H:%M"
            )
            booked_end = datetime.strptime(
                f"{normalized_date} {b['endTime']}", "%d-%m-%Y %H:%M"
            )
        except:
            continue

        if req_start < booked_end and req_end > booked_start:
            return False

    return True


# =====================================================
# 👤 CREATE CUSTOMER (FIREBASE-STYLE ID)
# =====================================================
def create_customer(customer_data: dict):
    try:
        ref = db.reference("salonandspa/customer").push()
        customer_id = ref.key

        base_data = {
            "uid": customer_id,
            "name": customer_data.get("name"),
            "phone": customer_data.get("phone"),
            "email": customer_data.get("email", ""),
            "role": "customer",
            "createdAt": int(time.time() * 1000)
        }

        ref.set(base_data)
        print("🆕 New customer created:", customer_id)
        return customer_id

    except Exception as e:
        print("❌ Error creating customer:", e)
        return None


# =====================================================
# 🧾 SAVE BOOKING HISTORY UNDER CUSTOMER NODE
# =====================================================
def save_booking_under_customer(customer_id: str, appointment_id: str, booking: dict):
    try:
        ref = db.reference(f"salonandspa/customer/{customer_id}/bookings/{appointment_id}")

        history_data = {
            "appointmentId": appointment_id,
            "salonId": booking["placeId"],
            "employeeId": booking["employeeId"],

            "serviceId": booking["services"][0]["serviceId"],
            "serviceName": booking["services"][0]["serviceName"],

            "date": booking["date"],
            "startTime": booking["startTime"],
            "duration": booking["totalDuration"],

            "amount": booking["totalAmount"],
            "status": booking["status"],
            "paymentStatus": booking["paymentStatus"],

            "createdAt": int(time.time() * 1000)
        }

        ref.set(history_data)
        print("📚 Booking history saved for customer:", customer_id)

    except Exception as e:
        print("❌ Error saving booking history:", e)


# =====================================================
# 📅 SAVE WHATSAPP BOOKING (MAIN ENTRY POINT)
# =====================================================
def save_whatsapp_booking(salon_id: str, booking_data: dict):
    ref = db.reference(f"salonandspa/appointments/salon/{salon_id}")

    # 🔥 Create customer
    customer_id = create_customer(
        customer_data=booking_data["customer"]
    )

    # 🔥 Build booking object
    booking = {
        "appointmentId": "",
        "createdAt": int(time.time() * 1000),

        "customerId": customer_id,
        "customer": booking_data["customer"],

        "placeId": booking_data["placeId"],
        "employeeId": booking_data["employeeId"],

        "services": booking_data["services"],

        "date": normalize_date(booking_data["date"]),
        "startTime": booking_data["startTime"],

        "totalAmount": booking_data["totalAmount"],
        "totalDuration": booking_data["totalDuration"],

        "paymentMode": booking_data.get("paymentMode", "offline"),
        "paymentStatus": booking_data.get("paymentStatus", "pending"),

        "status": booking_data.get("status", "confirmed"),

        "mode": "whatsapp",
        "type": "salon",

        "salonName": booking_data.get("salonName", ""),
        "branch": booking_data.get("branch", ""),
        "employeeName": booking_data.get("employeeName", "")
    }

    # 1️⃣ Save appointment
    new_ref = ref.push()
    booking["appointmentId"] = new_ref.key
    new_ref.set(booking)

    print("🔥 WhatsApp booking saved:", new_ref.key)
    print("👤 Customer ID (Firebase style):", customer_id)

    # 2️⃣ Save under customer history
    save_booking_under_customer(
        customer_id=customer_id,
        appointment_id=new_ref.key,
        booking=booking
    )

    # 3️⃣ Save slot
    save_booked_slot(
        salon_id=salon_id,
        booking=booking,
        appointment_id=new_ref.key
    )

    return new_ref.key


# =====================================================
# 🧩 SAVE BOOKED SLOT
# =====================================================
def save_booked_slot(salon_id: str, booking: dict, appointment_id: str):
    try:
        date = normalize_date(booking["date"])
        start_time = booking["startTime"]
        duration = int(booking["totalDuration"])

        slot_ref = db.reference(
            f"salonandspa/salons/{salon_id}/slots/{date}"
        )

        start_dt = datetime.strptime(f"{date} {start_time}", "%d-%m-%Y %H:%M")
        end_dt = start_dt + timedelta(minutes=duration)

        slot_data = {
            "appointmentId": appointment_id,
            "serviceId": booking["services"][0]["serviceId"],
            "employeeId": booking["employeeId"],

            "startTime": start_time,
            "endTime": end_dt.strftime("%H:%M"),

            "duration": duration,
            "status": booking["status"],

            "customerId": booking["customerId"],
            "customerName": booking["customer"]["name"],
            "serviceName": booking["services"][0]["serviceName"],

            "createdAt": int(time.time() * 1000)
        }

        new_slot_ref = slot_ref.push(slot_data)

        print("🧩 Slot saved:", new_slot_ref.key)
        return new_slot_ref.key

    except Exception as e:
        print("❌ Error saving slot:", e)
        return None


# =====================================================
# 📞 GET OWNER PHONE BY OWNER UID
# salonandspa/admin/{ownerUid}/phone
# =====================================================
def get_owner_phone(owner_uid: str):
    try:
        ref = db.reference(f"salonandspa/admin/{owner_uid}")
        data = ref.get() or {}

        phone = data.get("phone")
        print("📞 Fetched owner phone from admin node:", phone)
        return phone

    except Exception as e:
        print("❌ Error fetching owner phone:", e)
        return None
