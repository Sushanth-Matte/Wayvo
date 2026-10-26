from __future__ import annotations

import os
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from mysql.connector import Error as MySQLError
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "change-this-development-key-before-deploying"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "carpool_db"),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "autocommit": False,
}


def connect_db():
    """Create a fresh connection; each request owns and closes its connection."""
    return mysql.connector.connect(**DB_CONFIG)


def delete_expired_unbooked_rides(cur):
    """Delete active rides whose departure has passed and that never received a booking."""
    cur.execute(
        """DELETE r FROM rides AS r
           WHERE r.status = 'active'
             AND (r.departure_date < CURDATE()
                  OR (r.departure_date = CURDATE() AND r.departure_time < CURTIME()))
             AND NOT EXISTS (
                 SELECT 1 FROM bookings AS b WHERE b.ride_id = r.id
             )"""
    )


def current_user_id():
    return session.get("user_id")


def login_required():
    if not current_user_id():
        return jsonify(error="Please log in first."), 401
    return None


def read_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def normalise_date(value: str):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def normalise_time(value: str):
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def serialize_date(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def serialize_time(value):
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    return str(value or "")[:5]


def ride_to_json(row, include_private=False):
    ride_id = int(row["id"])
    image = "images/city-car.jpg" if ride_id % 2 == 0 else "images/road-car.jpg"
    payload = {
        "id": ride_id,
        "from": row.get("from_location", ""),
        "to": row.get("to_location", ""),
        "date": serialize_date(row.get("departure_date")),
        "time": serialize_time(row.get("departure_time")),
        "seats": int(row.get("available_seats", 0)),
        "total_seats": int(row.get("total_seats", row.get("available_seats", 0))),
        "price": float(row.get("price_per_seat", 0) or 0),
        "driver": row.get("driver_name") or "Driver",
        "driver_id": row.get("driver_id"),
        "rating": "New driver",
        "img": "/static/" + image,
        "status": row.get("ride_status", row.get("status", "active")),
    }
    if include_private:
        payload["driver_phone"] = row.get("driver_phone", "")
        payload["car"] = row.get("car_model", "")
        payload["color"] = row.get("car_color") or "Not specified"
        payload["reg"] = row.get("registration_number") or "Not provided"
        payload["pickup"] = row.get("pickup_location") or "Confirm with driver"
        payload["drop"] = row.get("dropoff_location") or ""
        payload["notes"] = row.get("notes") or ""
    # Vehicle and exact pickup/drop-off information is only included for the driver or an accepted passenger.
    if "booking_status" in row:
        payload["booking_status"] = row.get("booking_status")
    return payload


def booking_to_json(row):
    status = row["status"]
    include_private = status == "accepted" and row.get("ride_status", "active") == "active"
    payload = {
        "id": int(row["booking_id"]),
        "booking_id": int(row["booking_id"]),
        "ride_id": int(row["ride_id"]),
        "status": status,
        "seats_requested": int(row.get("seats_requested", 1)),
        "from": row.get("from_location", ""),
        "to": row.get("to_location", ""),
        "date": serialize_date(row.get("departure_date")),
        "time": serialize_time(row.get("departure_time")),
        "seats": int(row.get("available_seats", 0)),
        "price": float(row.get("price_per_seat", 0) or 0),
        "driver": row.get("driver_name") or "Driver",
        "img": "/static/" + ("images/city-car.jpg" if int(row["ride_id"]) % 2 == 0 else "images/road-car.jpg"),
        "ride_status": row.get("ride_status", "active"),
    }
    if include_private:
        payload["car"] = row.get("car_model", "")
        payload["color"] = row.get("car_color") or "Not specified"
        payload["reg"] = row.get("registration_number") or "Not provided"
        payload["pickup"] = row.get("pickup_location") or "Confirm with driver"
        payload["drop"] = row.get("dropoff_location") or ""
        payload["notes"] = row.get("notes") or ""
    if "created_at" in row:
        payload["requested_at"] = serialize_date(row["created_at"])
    return payload


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    try:
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        return jsonify(ok=True, database="connected")
    except MySQLError:
        return jsonify(ok=False, database="unavailable", message="Start MySQL in XAMPP and import schema.sql."), 503


@app.get("/api/me")
def api_me():
    user_id = current_user_id()
    if not user_id:
        return jsonify(user=None)
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, name, email, created_at FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            session.clear()
            return jsonify(user=None)
        return jsonify(user={"id": int(user["id"]), "name": user["name"], "email": user["email"]})
    finally:
        cur.close()
        conn.close()


@app.post("/api/auth/signup")
def api_signup():
    data = read_json()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if len(name) < 2 or len(name) > 100:
        return jsonify(error="Enter a name between 2 and 100 characters."), 400
    if len(email) > 190 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify(error="Enter a valid email address."), 400
    if len(password) < 6:
        return jsonify(error="Password must contain at least 6 characters."), 400

    conn = connect_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        user_id = cur.lastrowid
        session.clear()
        session["user_id"] = user_id
        session["user_name"] = name
        session.permanent = bool(data.get("remember", True))
        return jsonify(user={"id": int(user_id), "name": name, "email": email}), 201
    except mysql.connector.IntegrityError:
        conn.rollback()
        return jsonify(error="An account with this email already exists. Log in instead."), 409
    finally:
        cur.close()
        conn.close()


@app.post("/api/auth/login")
def api_login():
    data = read_json()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, name, email, password_hash FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify(error="Email or password is incorrect."), 401
        session.clear()
        session["user_id"] = int(user["id"])
        session["user_name"] = user["name"]
        session.permanent = bool(data.get("remember", True))
        return jsonify(user={"id": int(user["id"]), "name": user["name"], "email": user["email"]})
    finally:
        cur.close()
        conn.close()


@app.post("/api/auth/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/rides")
def api_rides():
    user_id = current_user_id()
    from_text = request.args.get("from", "").strip()
    to_text = request.args.get("to", "").strip()
    date_text = request.args.get("date", "").strip()
    sort = request.args.get("sort", "soon")
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 100))
    except ValueError:
        limit = 50

    sql = """
        SELECT r.*, u.name AS driver_name,
          (SELECT b.status FROM bookings b
           WHERE b.ride_id = r.id AND b.passenger_id = %s
             AND b.status IN ('pending', 'accepted')
           ORDER BY b.created_at DESC LIMIT 1) AS booking_status
        FROM rides r JOIN users u ON u.id = r.driver_id
        WHERE r.status = 'active' AND r.available_seats > 0
          AND (r.departure_date > CURDATE() OR
               (r.departure_date = CURDATE() AND r.departure_time >= CURTIME()))
          AND r.driver_id <> COALESCE(%s, 0)
    """
    args = [user_id or 0, user_id or 0]
    if from_text:
        sql += " AND LOWER(r.from_location) LIKE %s"
        args.append("%" + from_text.lower() + "%")
    if to_text:
        sql += " AND LOWER(r.to_location) LIKE %s"
        args.append("%" + to_text.lower() + "%")
    if date_text:
        selected_date = normalise_date(date_text)
        if not selected_date:
            return jsonify(error="Choose a valid departure date."), 400
        sql += " AND r.departure_date = %s"
        args.append(selected_date)
    if sort == "price":
        sql += " ORDER BY r.price_per_seat ASC, r.departure_date ASC, r.departure_time ASC"
    elif sort == "seats":
        sql += " ORDER BY r.available_seats DESC, r.departure_date ASC, r.departure_time ASC"
    else:
        sql += " ORDER BY r.departure_date ASC, r.departure_time ASC"
    sql += " LIMIT %s"
    args.append(limit)

    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    try:
        delete_expired_unbooked_rides(cur)
        conn.commit()
        cur.execute(sql, tuple(args))
        rides = [ride_to_json(row) | {"booking_status": row.get("booking_status")} for row in cur.fetchall()]
        return jsonify(rides=rides)
    finally:
        cur.close()
        conn.close()


@app.post("/api/rides")
def api_create_ride():
    auth_error = login_required()
    if auth_error:
        return auth_error
    data = read_json()
    start = str(data.get("from", "")).strip()
    destination = str(data.get("to", "")).strip()
    pickup = str(data.get("pickup", "")).strip()
    dropoff = str(data.get("drop", "")).strip()
    departure_date = normalise_date(str(data.get("date", "")))
    departure_time = normalise_time(str(data.get("time", "")))
    car_model = str(data.get("car", "")).strip()
    car_color = str(data.get("color", "")).strip()
    registration_number = str(data.get("reg", "")).strip().upper()
    driver_phone = re.sub(r"[\s()-]", "", str(data.get("phone", "")).strip())
    if driver_phone.startswith("+91"):
        driver_phone = driver_phone[3:]
    elif driver_phone.startswith("91") and len(driver_phone) == 12:
        driver_phone = driver_phone[2:]
    notes = str(data.get("notes", "")).strip()
    try:
        seats = int(data.get("seats", 0))
        price = Decimal(str(data.get("price", "")))
    except (TypeError, ValueError, InvalidOperation):
        return jsonify(error="Enter a valid seat count and price."), 400

    if not all([start, destination, pickup, departure_date, departure_time, car_model, registration_number, driver_phone]):
        return jsonify(error="Please fill in all required route, time, vehicle and mobile number fields."), 400
    if not re.fullmatch(r"[6-9]\d{9}", driver_phone):
        return jsonify(error="Enter a valid 10-digit Indian mobile number."), 400
    if len(start) > 120 or len(destination) > 120 or len(pickup) > 255 or len(dropoff) > 255:
        return jsonify(error="One of the location fields is too long."), 400
    if start.casefold() == destination.casefold():
        return jsonify(error="Starting point and destination must be different."), 400
    now = datetime.now()
    if departure_date < date.today() or (departure_date == date.today() and departure_time <= now.time().replace(second=0, microsecond=0)):
        return jsonify(error="Choose a future departure date and time."), 400
    if seats not in (1, 2, 3, 4):
        return jsonify(error="Choose between 1 and 4 available seats."), 400
    if price < 0 or price > Decimal("50000"):
        return jsonify(error="The price per seat must be between ₹0 and ₹50,000."), 400
    if len(car_model) > 120 or len(car_color) > 60 or len(registration_number) > 30 or len(notes) > 1000:
        return jsonify(error="A vehicle or note field is too long."), 400

    conn = connect_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO rides
               (driver_id, from_location, to_location, pickup_location, dropoff_location,
                departure_date, departure_time, total_seats, available_seats, price_per_seat,
                car_model, car_color, registration_number, notes, driver_phone)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (current_user_id(), start, destination, pickup, dropoff or None,
             departure_date, departure_time, seats, seats, price, car_model,
             car_color or None, registration_number, notes or None, driver_phone),
        )
        conn.commit()
        return jsonify(ok=True, ride_id=int(cur.lastrowid)), 201
    finally:
        cur.close()
        conn.close()


@app.post("/api/rides/<int:ride_id>/bookings")
def api_request_seat(ride_id):
    auth_error = login_required()
    if auth_error:
        return auth_error
    passenger_id = current_user_id()
    data = read_json()
    try:
        seats_requested = int(data.get("seats", 1))
    except (TypeError, ValueError):
        return jsonify(error="Choose a valid number of seats."), 400
    if seats_requested < 1 or seats_requested > 4:
        return jsonify(error="You can request between 1 and 4 seats."), 400
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, driver_id, status, available_seats, departure_date, departure_time FROM rides WHERE id = %s", (ride_id,))
        ride = cur.fetchone()
        if not ride or ride["status"] != "active":
            return jsonify(error="This ride is no longer available."), 404
        if int(ride["driver_id"]) == int(passenger_id):
            return jsonify(error="You cannot book a seat on your own ride."), 400
        available_seats = int(ride["available_seats"])
        if available_seats < 1:
            return jsonify(error="There are no seats left on this ride."), 409
        if seats_requested > available_seats:
            return jsonify(error=f"Only {available_seats} seat(s) are currently available."), 409
        cur.execute(
            "SELECT id FROM bookings WHERE ride_id = %s AND passenger_id = %s AND status IN ('pending','accepted') LIMIT 1",
            (ride_id, passenger_id),
        )
        if cur.fetchone():
            return jsonify(error="You already have an active request for this ride."), 409
        cur.execute(
            "INSERT INTO bookings (ride_id, passenger_id, seats_requested, status) VALUES (%s, %s, %s, 'pending')",
            (ride_id, passenger_id, seats_requested),
        )
        conn.commit()
        return jsonify(ok=True, booking_id=int(cur.lastrowid), status="pending", seats_requested=seats_requested), 201
    finally:
        cur.close()
        conn.close()


@app.get("/api/activity")
def api_activity():
    auth_error = login_required()
    if auth_error:
        return auth_error
    user_id = current_user_id()
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    try:
        delete_expired_unbooked_rides(cur)
        conn.commit()
        cur.execute(
            """SELECT b.id AS booking_id, b.ride_id, b.status, b.seats_requested, b.created_at,
                      r.driver_id, r.from_location, r.to_location, r.pickup_location,
                      r.dropoff_location, r.departure_date, r.departure_time,
                      r.available_seats, r.total_seats, r.price_per_seat,
                      r.car_model, r.car_color, r.registration_number, r.notes, r.driver_phone, r.status AS ride_status,
                      u.name AS driver_name
               FROM bookings b
               JOIN rides r ON r.id = b.ride_id
               JOIN users u ON u.id = r.driver_id
               WHERE b.passenger_id = %s ORDER BY b.created_at DESC""",
            (user_id,),
        )
        requests_list = [booking_to_json(row) for row in cur.fetchall()]

        cur.execute(
            """SELECT r.*, u.name AS driver_name
               FROM rides r JOIN users u ON u.id = r.driver_id
               WHERE r.driver_id = %s ORDER BY r.created_at DESC""",
            (user_id,),
        )
        offered_rows = cur.fetchall()
        offered = []
        for row in offered_rows:
            ride_json = ride_to_json(row, include_private=True)
            cur.execute(
                """SELECT b.id, b.status, b.seats_requested, b.created_at, u.name AS passenger_name
                   FROM bookings b JOIN users u ON u.id = b.passenger_id
                   WHERE b.ride_id = %s ORDER BY b.created_at DESC""",
                (row["id"],),
            )
            ride_json["bookings"] = [
                {"id": int(b["id"]), "status": b["status"], "seats_requested": int(b["seats_requested"]),
                 "passenger_name": b["passenger_name"], "created_at": serialize_date(b["created_at"])}
                for b in cur.fetchall()
            ]
            offered.append(ride_json)
        return jsonify(requests=requests_list, offered=offered)
    finally:
        cur.close()
        conn.close()


def get_booking_and_ride_for_update(cur, booking_id):
    cur.execute("SELECT ride_id FROM bookings WHERE id = %s", (booking_id,))
    basic = cur.fetchone()
    if not basic:
        return None, None
    ride_id = int(basic["ride_id"])
    cur.execute("SELECT id, driver_id, available_seats, total_seats, status FROM rides WHERE id = %s FOR UPDATE", (ride_id,))
    ride = cur.fetchone()
    cur.execute("SELECT id, ride_id, passenger_id, seats_requested, status FROM bookings WHERE id = %s FOR UPDATE", (booking_id,))
    booking = cur.fetchone()
    return ride, booking


@app.post("/api/bookings/<int:booking_id>/accept")
def api_accept_booking(booking_id):
    auth_error = login_required()
    if auth_error:
        return auth_error
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        ride, booking = get_booking_and_ride_for_update(cur, booking_id)
        if not ride or not booking:
            conn.rollback()
            return jsonify(error="Booking not found."), 404
        if int(ride["driver_id"]) != int(current_user_id()):
            conn.rollback()
            return jsonify(error="Only the driver who posted this ride can accept requests."), 403
        if ride["status"] != "active":
            conn.rollback()
            return jsonify(error="This ride has been cancelled."), 409
        if booking["status"] != "pending":
            conn.rollback()
            return jsonify(error="This booking is no longer pending."), 409
        seats = int(booking["seats_requested"])
        if int(ride["available_seats"]) < seats:
            conn.rollback()
            return jsonify(error="There are not enough seats left to accept this request."), 409
        cur.execute("UPDATE bookings SET status = 'accepted', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (booking_id,))
        cur.execute("UPDATE rides SET available_seats = available_seats - %s WHERE id = %s", (seats, ride["id"]))
        conn.commit()
        return jsonify(ok=True, status="accepted")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@app.post("/api/bookings/<int:booking_id>/decline")
def api_decline_booking(booking_id):
    auth_error = login_required()
    if auth_error:
        return auth_error
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        ride, booking = get_booking_and_ride_for_update(cur, booking_id)
        if not ride or not booking:
            conn.rollback()
            return jsonify(error="Booking not found."), 404
        if int(ride["driver_id"]) != int(current_user_id()):
            conn.rollback()
            return jsonify(error="Only the ride's driver can decline this request."), 403
        if booking["status"] != "pending":
            conn.rollback()
            return jsonify(error="Only pending requests can be declined."), 409
        cur.execute("UPDATE bookings SET status = 'declined', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (booking_id,))
        conn.commit()
        return jsonify(ok=True, status="declined")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@app.post("/api/bookings/<int:booking_id>/cancel")
def api_cancel_booking(booking_id):
    auth_error = login_required()
    if auth_error:
        return auth_error
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        ride, booking = get_booking_and_ride_for_update(cur, booking_id)
        if not ride or not booking:
            conn.rollback()
            return jsonify(error="Booking not found."), 404
        if int(booking["passenger_id"]) != int(current_user_id()):
            conn.rollback()
            return jsonify(error="You can only cancel your own booking."), 403
        if booking["status"] not in ("pending", "accepted"):
            conn.rollback()
            return jsonify(error="This booking cannot be cancelled now."), 409
        seats = int(booking["seats_requested"])
        cur.execute("UPDATE bookings SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (booking_id,))
        if booking["status"] == "accepted" and ride["status"] == "active":
            cur.execute(
                "UPDATE rides SET available_seats = LEAST(total_seats, available_seats + %s) WHERE id = %s",
                (seats, ride["id"]),
            )
        conn.commit()
        return jsonify(ok=True, status="cancelled")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@app.post("/api/rides/<int:ride_id>/cancel")
def api_cancel_ride(ride_id):
    auth_error = login_required()
    if auth_error:
        return auth_error
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cur.execute("SELECT id, driver_id, status FROM rides WHERE id = %s FOR UPDATE", (ride_id,))
        ride = cur.fetchone()
        if not ride:
            conn.rollback()
            return jsonify(error="Ride not found."), 404
        if int(ride["driver_id"]) != int(current_user_id()):
            conn.rollback()
            return jsonify(error="You can only cancel a ride you posted."), 403
        if ride["status"] != "active":
            conn.rollback()
            return jsonify(error="This ride is already cancelled."), 409
        cur.execute("UPDATE rides SET status = 'cancelled', available_seats = 0 WHERE id = %s", (ride_id,))
        cur.execute(
            "UPDATE bookings SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE ride_id = %s AND status IN ('pending','accepted')",
            (ride_id,),
        )
        conn.commit()
        return jsonify(ok=True, status="cancelled")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@app.errorhandler(MySQLError)
def handle_database_error(error):
    app.logger.error("MySQL error: %s", error)
    return jsonify(error="Could not connect to MySQL. Start MySQL in XAMPP, create carpool_db, import schema.sql, and check your .env settings."), 503


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("FLASK_PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "1") == "1")
