from flask import Blueprint, jsonify, request , current_app
from db import get_db
from flask_mail import Message
main_routes = Blueprint("main_routes", __name__)

# -----------------------------
# BOOK APPOINTMENT
# -----------------------------
@main_routes.route('/appointments/<int:patient_id>', methods=['GET'])
def get_appointments(patient_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT 
        a.appointment_id,
        d.name AS doctor_name,
        d.specialization,
        s.available_date,
        s.time_slot,
        a.status,
        a.booking_date
    FROM appointment a
    JOIN doctor_availability s ON a.availability_id = s.availability_id
    JOIN doctor d ON s.doctor_id = d.doctor_id
    WHERE a.patient_id = %s
    """

    cursor.execute(query, (patient_id,))
    result = cursor.fetchall()

    return jsonify(result)

# -----------------------------
# HOME
# -----------------------------
@main_routes.route("/")
def home():
    return jsonify({
        "message": "Healthcare backend is running",
        "status": "success"
    })


# -----------------------------
# HEALTH CHECK
# -----------------------------
@main_routes.route("/health")
def health_check():
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT 1")
        cursor.fetchone()   # important line

        cursor.close()
        conn.close()

        return jsonify({
            "database": "connected",
            "server": "ok"
        })

    except Exception as e:
        return jsonify({
            "database": "error",
            "error": str(e)
        })
@main_routes.route("/doctor", methods=["GET"])
def get_doctor():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT doctor_id, name, specialization, email, phone,
               consultation_fee, experience, rating, image, gender
        FROM doctor
    """)

    doctor = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(doctor)


# -----------------------------
# GET AVAILABLE DOCTORS
# -----------------------------
@main_routes.route("/available-doctor", methods=["GET"])
def available_doctor():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT d.doctor_id,
               d.name,
               d.specialization,
               a.availability_id,
               a.available_date,
               a.time_slot
        FROM doctor d
        JOIN doctor_availability a
        ON d.doctor_id = a.doctor_id
        WHERE a.is_booked = FALSE
        ORDER BY a.available_date, a.time_slot
    """)

    doctor = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(doctor)



# -----------------------------
# GET DOCTOR SLOTS
# -----------------------------
@main_routes.route("/doctor-slots/<int:doctor_id>", methods=["GET"])
def doctor_slots(doctor_id):

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT availability_id, available_date, time_slot
    FROM doctor_availability
    WHERE doctor_id = %s
    AND is_booked = 0
    AND available_date >= CURDATE()
    ORDER BY available_date, time_slot
""", (doctor_id,))

    slots = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(slots)

# -----------------------------
# CHATBOT
# -----------------------------
user_context = {}

@main_routes.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.json
    message = data.get("message", "").lower().strip()
    user_id = "default"

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # Initialize context
    if user_id not in user_context:
        user_context[user_id] = {}

    context = user_context[user_id]

    # -----------------------------
    # GREETING
    # -----------------------------
    if any(word in message for word in ["hi", "hello", "hey"]):
        return jsonify({
            "response": "Hi! I can help you book a doctor appointment. Say 'book appointment' to start."
        })

    # -----------------------------
    # START BOOKING
    # -----------------------------
    if any(word in message for word in ["doctor", "appointment", "book", "consult"]):
        context.clear()
        context["step"] = "choose_doctor"

        cursor.execute("""
            SELECT doctor_id, name, specialization FROM doctor
        """)
        doctors = cursor.fetchall()

        response = "Select a doctor:\n"
        for d in doctors:
            response += f"{d['doctor_id']}. {d['name']} ({d['specialization']})\n"

        return jsonify({"response": response})

    # -----------------------------
    # SELECT DOCTOR
    # -----------------------------
    elif context.get("step") == "choose_doctor" and message.isdigit():
        doctor_id = int(message)
        context["doctor_id"] = doctor_id
        context["step"] = "choose_slot"

        cursor.execute("""
            SELECT available_date, time_slot
            FROM doctor_availability
            WHERE doctor_id=%s AND is_booked=0
        """, (doctor_id,))

        slots = cursor.fetchall()

        if not slots:
            return jsonify({"response": "No slots available for this doctor."})

        context["slots"] = slots

        response = "Choose a slot:\n"
        for i, s in enumerate(slots, start=1):
            response += f"{i}. {s['available_date']} - {s['time_slot']}\n"

        return jsonify({"response": response})

    # -----------------------------
    # SELECT SLOT
    # -----------------------------
    elif context.get("step") == "choose_slot" and message.isdigit():
        slot_index = int(message) - 1
        slots = context.get("slots", [])

        if slot_index < 0 or slot_index >= len(slots):
            return jsonify({"response": "Invalid slot selection."})

        selected = slots[slot_index]

        cursor.execute("""
            SELECT availability_id FROM doctor_availability
            WHERE doctor_id=%s AND available_date=%s AND time_slot=%s AND is_booked=0
        """, (
            context["doctor_id"],
            selected["available_date"],
            selected["time_slot"]
        ))

        slot = cursor.fetchone()

        if not slot:
            return jsonify({"response": "Slot already booked."})

        cursor.execute("""
            INSERT INTO appointment (availability_id)
            VALUES (%s)
        """, (slot["availability_id"],))

        cursor.execute("""
            UPDATE doctor_availability
            SET is_booked = 1
            WHERE availability_id = %s
        """, (slot["availability_id"],))

        conn.commit()

        context.clear()

        return jsonify({"response": "✅ Appointment booked successfully!"})

    # -----------------------------
    # DEFAULT
    # -----------------------------
    return jsonify({
        "response": "Say 'book appointment' to get started."
    })

@main_routes.route("/register", methods=["POST"])
def register():

    data = request.json

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    phone = data.get("phone")
    

    # Validate input
    if not name or not email or not password or not phone:
        return jsonify({"message": "All fields are required"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # Check if email exists
        cursor.execute("SELECT * FROM patient WHERE email = %s", (email,))
        existing = cursor.fetchone()

        if existing:
            return jsonify({"message": "Email already registered"}), 400

        # Insert new patient
        cursor.execute("""
            INSERT INTO patient (name, email, phone, password)
           VALUES (%s, %s, %s, %s)
        """, (name, email, phone, password))

        conn.commit()

        return jsonify({"message": "Registered successfully"})

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)})

    finally:
        cursor.close()
        conn.close()

@main_routes.route("/login", methods=["POST"])
def login():

    data = request.json

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"message": "Email and password required"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT * FROM patient 
            WHERE email = %s AND password = %s
        """, (email, password))

        user = cursor.fetchone()

        if not user:
            return jsonify({"message": "Invalid credentials"}), 401

        return jsonify({
            "message": "Login successful",
            "patient_id": user["patient_id"],
            "name": user["name"]
        })

    finally:
        cursor.close()
        conn.close()

@main_routes.route("/login/doctor", methods=["POST"])
def doctor_login():

    data = request.json
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"message": "Email and password required"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT * FROM doctor 
            WHERE email = %s AND password = %s
        """, (email, password))

        doctor = cursor.fetchone()

        if not doctor:
            return jsonify({"message": "Invalid credentials"}), 401

        return jsonify({
            "message": "Doctor login successful",
            "doctor_id": doctor["doctor_id"],
            "name": doctor["name"]
        })

    finally:
        cursor.close()
        conn.close()

@main_routes.route("/login/admin", methods=["POST"])
def admin_login():

    data = request.json
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"message": "Email and password required"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT * FROM admin 
            WHERE email = %s AND password = %s
        """, (email, password))

        admin = cursor.fetchone()

        if not admin:
            return jsonify({"message": "Invalid credentials"}), 401

        return jsonify({
            "message": "Admin login successful",
            "admin_id": admin["admin_id"],
            "name": admin["name"]
        })

    finally:
        cursor.close()
        conn.close()

@main_routes.route("/cancel-appointment", methods=["POST"])
def cancel_appointment():

    data = request.get_json()
    appointment_id = data.get("appointment_id")

    if not appointment_id:
        return jsonify({"message": "Appointment ID required"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1️⃣ Get availability_id before deleting
        cursor.execute("""
            SELECT availability_id FROM appointment
            WHERE appointment_id = %s
        """, (appointment_id,))
        appointment = cursor.fetchone()

        if not appointment:
            return jsonify({"message": "Appointment not found"}), 404

        availability_id = appointment["availability_id"]

        # 2️⃣ Delete appointment
        cursor.execute("""
            DELETE FROM appointment
            WHERE appointment_id = %s
        """, (appointment_id,))

        # 3️⃣ Make slot available again
        cursor.execute("""
            UPDATE doctor_availability
            SET is_booked = 0
            WHERE availability_id = %s
        """, (availability_id,))

        conn.commit()

        return jsonify({"message": "Appointment cancelled successfully"})

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)})

    finally:
        cursor.close()
        conn.close()

@main_routes.route("/book-appointment", methods=["POST"])
def book_appointment():

    data = request.json
    availability_id = data.get("availability_id")
    patient_id = data.get("patient_id")

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # Insert appointment
        cursor.execute("""
            INSERT INTO appointment (patient_id, availability_id)
            VALUES (%s, %s)
        """, (patient_id, availability_id))

        # Mark slot as booked
        cursor.execute("""
            UPDATE doctor_availability
            SET is_booked = 1
            WHERE availability_id = %s
        """, (availability_id,))

        # Get patient email
        cursor.execute("""
            SELECT email FROM patient WHERE patient_id = %s
        """, (patient_id,))
        patient = cursor.fetchone()
        patient_email = patient["email"]

        # Get doctor name, date and time
        cursor.execute("""
            SELECT d.name AS doctor_name,
                   da.available_date,
                   da.time_slot
            FROM doctor_availability da
            JOIN doctor d ON da.doctor_id = d.doctor_id
            WHERE da.availability_id = %s
        """, (availability_id,))

        details = cursor.fetchone()

        doctor_name = details["doctor_name"]
        date = details["available_date"]
        time = details["time_slot"]

        conn.commit()

        # Send Email
        msg = Message(
            "Appointment Confirmation - CareConnect",
            sender="yourgmail@gmail.com",
            recipients=[patient_email]
        )

        msg.body = f"""
Hello,

Your appointment has been successfully booked.

Doctor: Dr. {doctor_name}
Date: {date}
Time: {time}

Thank you for using CareConnect.
"""

        current_app.extensions['mail'].send(msg)

        return jsonify({"message": "Appointment booked and email sent successfully"})

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)})

    finally:
        cursor.close()
        conn.close()
# -----------------------------
# GET DOCTOR APPOINTMENTS
# -----------------------------
@main_routes.route("/doctor-appointments/<int:doctor_id>", methods=["GET"])
def get_doctor_appointments(doctor_id):

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            a.appointment_id,
            p.name AS patient_name,
            da.available_date,
            da.time_slot,
            a.booking_date
        FROM appointment a
        JOIN doctor_availability da 
            ON a.availability_id = da.availability_id
        JOIN patient p
            ON a.patient_id = p.patient_id
        WHERE da.doctor_id = %s
        ORDER BY da.available_date
    """, (doctor_id,))

    appointments = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(appointments)

@main_routes.route("/delete-appointment/<int:appointment_id>", methods=["DELETE"])
def delete_appointment(appointment_id):

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "DELETE FROM appointment WHERE appointment_id = %s",
            (appointment_id,)
        )
        conn.commit()

        return jsonify({"message": "Appointment deleted successfully"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"message": str(e)}), 500

    finally:
        cursor.close()
        conn.close()
    