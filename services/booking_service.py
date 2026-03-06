# services/booking_service.py

from services.firebase_service import (
    get_salons_by_city,
    get_services_by_salon,
    get_employees_by_salon
)


# =====================================================
# 🏬 FIND SALONS BY CITY
# =====================================================

def find_salons_by_city(city: str):
    """
    Fetch salons filtered by city.

    Used in conversation.py when user enters city.
    """

    if not city:
        return []

    salons = get_salons_by_city(city)

    if not salons:
        return []

    return salons


# =====================================================
# 💆 FIND SERVICES BY SALON
# =====================================================

def find_services_by_salon(salon_id: str):
    """
    Fetch all services for a specific salon.

    Used after user selects a salon.
    """

    if not salon_id:
        return []

    services = get_services_by_salon(salon_id)

    if not services:
        return []

    return services


# =====================================================
# 👨‍💼 FIND EMPLOYEES BY SALON
# =====================================================

def find_employees_by_salon(salon_id: str):
    """
    Fetch all active employees of a salon.

    Used during booking confirmation to assign employee.
    """

    if not salon_id:
        return []

    employees = get_employees_by_salon(salon_id)

    if not employees:
        return []

    return employees