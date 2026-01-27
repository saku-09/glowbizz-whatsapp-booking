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
        if len(raw_date.split("-")[0]) == 4:
            dt = datetime.strptime(raw_date, "%Y-%m-%d")
        else:
            dt = datetime.strptime(raw_date, "%d-%m-%Y")

        return dt.strftime("%d-%m-%Y")
    except:
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
        name_raw = (
            salon.get("branch") or
            salon.get("name") or
            salon.get("salonName") or
            ""
        )

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
            "duration": int(s.get("duration") or 0)
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
            "open": timings.get("open"),
            "close": timings.get("close")
        }

    except:
        return None


# =====================================================
# 🔎 READ BOOKED SLOTS
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

    except:
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
# 👤 CREATE CUSTOMER
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
# 🧾 SAVE BOOKING UNDER CUSTOMER
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
# 📅 SAVE WHATSAPP BOOKING
# =====================================================
def save_whatsapp_booking(salon_id: str, booking_data: dict):
    ref = db.reference(f"salonandspa/appointments/salon/{salon_id}")

    customer_id = create_customer(
        customer_data=booking_data["customer"]
    )

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

        "ownerUid": booking_data.get("ownerUid"),
        "salonName": booking_data.get("salonName", ""),
        "branch": booking_data.get("branch", ""),
        "employeeName": booking_data.get("employeeName", "")
    }

    new_ref = ref.push()
    booking["appointmentId"] = new_ref.key
    new_ref.set(booking)

    print("🔥 WhatsApp booking saved:", new_ref.key)

    save_booking_under_customer(
        customer_id=customer_id,
        appointment_id=new_ref.key,
        booking=booking
    )

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
# 📞 GET OWNER PHONE
# =====================================================
def get_owner_phone(owner_uid: str):
    try:
        if not owner_uid:
            print("⚠️ ownerUid is empty")
            return None

        ref = db.reference(f"salonandspa/admin/{owner_uid}")
        data = ref.get() or {}

        phone = data.get("phone")
        print("📞 Fetched owner phone from admin node:", phone)
        return phone

    except Exception as e:
        print("❌ Error fetching owner phone:", e)
        return None


# =====================================================
# ❌ CANCEL APPOINTMENT + CLEANUP
# =====================================================
def cancel_appointment_and_cleanup(salon_id: str, appointment_id: str, date: str):
    try:
        appt_ref = db.reference(f"salonandspa/appointments/salon/{salon_id}/{appointment_id}")
        appt_data = appt_ref.get()

        if not appt_data:
            print("⚠️ Appointment not found:", appointment_id)
            return

        customer_id = appt_data.get("customerId")

        # Update appointment status
        appt_ref.update({
            "status": "cancelled_by_customer",
            "cancelledAt": int(time.time() * 1000)
        })
        print("❌ Appointment status updated:", appointment_id)

        # Delete slot
        slots_ref = db.reference(f"salonandspa/salons/{salon_id}/slots/{date}")
        slots = slots_ref.get() or {}

        for slot_id, slot in slots.items():
            if slot.get("appointmentId") == appointment_id:
                slots_ref.child(slot_id).delete()
                print("🧩 Slot deleted:", slot_id)
                break

        # Delete customer booking + auto delete customer if empty
        if customer_id:
            bookings_ref = db.reference(f"salonandspa/customer/{customer_id}/bookings")
            bookings_ref.child(appointment_id).delete()
            print("👤 Customer booking deleted:", appointment_id)

            remaining = bookings_ref.get()

            if not remaining:
                cust_root_ref = db.reference(f"salonandspa/customer/{customer_id}")
                cust_root_ref.delete()
                print("🗑️ Customer profile deleted (no bookings left):", customer_id)
            else:
                print("ℹ️ Customer still has other bookings, profile kept:", customer_id)
        else:
            print("⚠️ customerId missing in appointment")

    except Exception as e:
        print("❌ Error during cancel cleanup:", e)


# =====================================================
# 🔎 FIND LATEST ACTIVE BOOKING BY CUSTOMER
# =====================================================
def find_latest_active_booking_by_customer(phone: str, name: str):
    try:
        ref = db.reference("salonandspa/appointments/salon")
        all_salons = ref.get() or {}

        latest_booking = None
        latest_time = 0

        for salon_id, salon_bookings in all_salons.items():
            for appointment_id, booking in (salon_bookings or {}).items():

                if booking.get("status") != "confirmed":
                    continue

                customer = booking.get("customer", {})
                customer_phone = customer.get("phone", "")
                customer_name = customer.get("name", "")

                if customer_phone == phone and customer_name.lower() == name.lower():

                    created_at = booking.get("createdAt", 0)

                    if created_at > latest_time:
                        latest_time = created_at

                        latest_booking = {
                            "appointmentId": appointment_id,
                            "salonId": salon_id,
                            "ownerUid": booking.get("ownerUid"),
                            "employeeId": booking.get("employeeId"),

                            "customerName": customer_name,
                            "customerPhone": customer_phone,

                            "salonName": booking.get("salonName"),
                            "serviceName": booking["services"][0]["serviceName"],

                            "date": booking.get("date"),
                            "startTime": booking.get("startTime"),

                            "employeePhone": None
                        }

                        emp_ref = db.reference(
                            f"salonandspa/salons/{salon_id}/employees/{booking.get('employeeId')}"
                        )
                        emp_data = emp_ref.get() or {}
                        latest_booking["employeePhone"] = emp_data.get("phone")

        return latest_booking

    except Exception as e:
        print("❌ Error finding booking for cancel:", e)
        return None

# =====================================================
# 🔎 FIND OWNER UID BY SALON ID
# =====================================================
def find_owner_uid_by_salon(salon_id: str):
    try:
        ref = db.reference("salonandspa/admin")
        admins = ref.get() or {}

        for admin_uid, admin in admins.items():
            for key, value in admin.items():
                if key.startswith("salonid") and value == salon_id:
                    print("👑 Found ownerUid for salon:", admin_uid)
                    return admin_uid

        print("⚠️ No owner found for salon:", salon_id)
        return None

    except Exception as e:
        print("❌ Error finding owner by salon:", e)
        return None
# =====================================================
# 👨‍💼 GET EMPLOYEE BY ID (GLOBAL EMPLOYEES NODE)
# =====================================================
def get_employee_by_id(employee_id: str):
    try:
        ref = db.reference(f"salonandspa/employees/{employee_id}")
        data = ref.get()

        if not data:
            print("⚠️ Employee not found in GLOBAL employees node:", employee_id)
            return None

        print("👨‍💼 Employee fetched from GLOBAL node:", data)
        return data

    except Exception as e:
        print("❌ Error fetching employee by id:", e)
        return None


