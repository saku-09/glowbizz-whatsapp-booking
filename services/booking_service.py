# services/booking_service.py

from services.firebase_service import (
    get_salons_by_city,
    get_services_by_salon,
    get_employees_by_salon,
    is_slot_available,
    get_booked_slots_for_date
)

# =====================================================
# 🔁 WRAPPER FUNCTIONS USED BY CONVERSATION
# =====================================================

def find_salons_by_city(city: str):
    """
    Fetch salons filtered by city
    """
    return get_salons_by_city(city)


def find_services_by_salon(salon_id: str):
    """
    Fetch all services of a salon
    """
    return get_services_by_salon(salon_id)


def find_employees_by_salon(salon_id: str):
    """
    Fetch all active employees of a salon
    """
    return get_employees_by_salon(salon_id)


def check_slot_available(salon_id, employee_id, date, start_time, duration):
    """
    Check if a particular employee is free for given slot & duration
    """
    return is_slot_available(
        salon_id=salon_id,
        employee_id=employee_id,
        date=date,
        start_time=start_time,
        duration=duration
    )


def get_booked_slots(salon_id: str, date: str):
    """
    Fetch all booked start times for a salon on a given date
    (used only if needed, not mandatory in final flow)
    """
    return get_booked_slots_for_date(salon_id, date)
