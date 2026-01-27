# services/booking_service.py

from services.firebase_service import (
    get_salons_by_city,
    get_services_by_salon,
    get_employees_by_salon,
    is_slot_available,
    get_salon_timings,
    save_owner_lead,
    save_whatsapp_booking
)

# =====================================================
# 🏬 FIND SALONS BY CITY
# =====================================================

def find_salons_by_city(city: str):
    """
    Fetch salons filtered by city.
    Used in CUSTOMER_CITY step.
    """
    if not city:
        return []
    return get_salons_by_city(city)


# =====================================================
# 💆 FIND SERVICES BY SALON
# =====================================================

def find_services_by_salon(salon_id: str):
    """
    Fetch all services of a salon.
    Used in CUSTOMER_SELECT_SERVICE step.
    """
    if not salon_id:
        return []
    return get_services_by_salon(salon_id)


# =====================================================
# 👨‍💼 FIND EMPLOYEES BY SALON
# =====================================================

def find_employees_by_salon(salon_id: str):
    """
    Fetch all active employees of a salon.
    Used in final slot assignment.
    """
    if not salon_id:
        return []
    return get_employees_by_salon(salon_id)


# =====================================================
# 🔥 CHECK SLOT AVAILABLE (PASS THROUGH)
# =====================================================

def check_slot_available(salon_id, employee_id, date, start_time, duration):
    """
    Check if a particular employee is free for given slot & duration.

    date format MUST be: DD-MM-YYYY
    """
    return is_slot_available(
        salon_id=salon_id,
        employee_id=employee_id,
        date=date,
        start_time=start_time,
        duration=duration
    )


# =====================================================
# 🕒 FIND SALON TIMINGS
# =====================================================

def find_salon_timings(salon_id: str, day_name: str):
    """
    Fetch open/close timings for a salon on a given day.

    day_name example: "monday", "tuesday"
    """
    if not salon_id or not day_name:
        return None
    return get_salon_timings(salon_id, day_name)


# =====================================================
# 🔔 SAVE BOOKING (HIGH LEVEL WRAPPER)
# =====================================================

def save_whatsapp_booking_and_notify(salon_id: str, booking_data: dict):
    """
    Save booking under:
    salonandspa/appointments/salon/{salonId}

    Internally this also:
    - Creates customer
    - Saves booking history
    - Saves slot under salons/{salonId}/slots/{DD-MM-YYYY}

    This is just a clean wrapper over firebase_service.
    """

    if not salon_id or not booking_data:
        return None

    return save_whatsapp_booking(salon_id, booking_data)


# =====================================================
# 🧑‍💼 SAVE OWNER LEAD (PASS THROUGH)
# =====================================================

def save_owner_lead_and_notify(lead_data: dict):
    """
    Save owner lead during owner registration flow.
    """
    if not lead_data:
        return None
    return save_owner_lead(lead_data)
