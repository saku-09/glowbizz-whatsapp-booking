# Glowbizz WhatsApp Booking Assistant

A WhatsApp-style AI Booking Assistant built using **Flask + Firebase Realtime Database**.

This bot allows:
- Salon Owners to register
- Customers to book appointments
- Real-time slot management
- WhatsApp booking notifications
- Appointment + Slot storage in Firebase

# Features

# Customer Flow
- Select City
- Choose Salon
- Select Service
- Pick Date & Available Time Slot
- Auto Employee Assignment
- Booking Confirmation
- Saves:
  - Appointment
  - Slot inside salon node

# Owner Flow
- Register salon
- Choose subscription plan
- Owner lead stored in Firebase

# Database Structure

Appointments are stored at:
# 💬 Glowbizz WhatsApp Booking Assistant

A WhatsApp-style AI Booking Assistant built using **Flask + Firebase Realtime Database**.

This bot allows:
- 🏢 Salon Owners to register
- 👩‍💼 Customers to book appointments
- 📅 Real-time slot management
- 🔔 WhatsApp booking notifications
- 🗂 Appointment + Slot storage in Firebase

---

## 🚀 Features

### 👩‍💼 Customer Flow
- Select City
- Choose Salon
- Select Service
- Pick Date & Available Time Slot
- Auto Employee Assignment
- Booking Confirmation
- Saves:
  - Appointment
  - Slot inside salon node

# Owner Flow
- Register salon
- Choose subscription plan
- Owner lead stored in Firebase

### 🔥 Database Structure

Appointments are stored at:
salonandspa/
appointments/
salon/
{salonId}/
{appointmentId}

Slots are stored at:
salonandspa/
salons/
{salonId}/
slots/
{date}/
{slotId}

# Tech Stack

- Python 3.10+
- Flask
- Firebase Admin SDK
- HTML + CSS (WhatsApp UI)
- JavaScript (Chat handling)
  
# Project Structure

whatsapp/
│
├── app.py
├── firebase_key.json
├── requirements.txt
│
├── services/
│ ├── conversation_service.py
│ ├── booking_service.py
│ ├── firebase_service.py
│ ├── whatsapp_service.py
│ └── notification_service.py
│
├── data/
│ └── store.py
│
├── templates/
│ └── index.html
│
└── static/
└── style.css


---

# Installation Guide

#  Clone the Repository

```bash
git clone https://github.com/saku-09/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME

# Create Virtual Environment
python -m venv venv


# Install Dependencies
pip install -r requirements.txt

# Add Firebase Key

Download your Firebase Admin SDK key
Rename to:
firebase_key.json

# Run Application

python app.py

## UI

WhatsApp-style interface

User messages → Right side

Bot messages → Left side

Responsive layout

Auto scroll

Clean chat experience





