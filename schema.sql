-- Wayvo carpool database schema for XAMPP / MariaDB / MySQL.
-- In phpMyAdmin, open the SQL tab and run this whole file.

CREATE DATABASE IF NOT EXISTS carpool_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE carpool_db;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(190) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rides (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    driver_id BIGINT UNSIGNED NOT NULL,
    driver_phone VARCHAR(16) NOT NULL,
    from_location VARCHAR(120) NOT NULL,
    to_location VARCHAR(120) NOT NULL,
    pickup_location VARCHAR(255) NOT NULL,
    dropoff_location VARCHAR(255) NULL,
    departure_date DATE NOT NULL,
    departure_time TIME NOT NULL,
    total_seats TINYINT UNSIGNED NOT NULL,
    available_seats TINYINT UNSIGNED NOT NULL,
    price_per_seat DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    car_model VARCHAR(120) NOT NULL,
    car_color VARCHAR(60) NULL,
    registration_number VARCHAR(30) NOT NULL,
    notes VARCHAR(1000) NULL,
    status ENUM('active','cancelled','completed') NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_rides_driver (driver_id),
    KEY idx_rides_route_date (from_location, to_location, departure_date),
    KEY idx_rides_status_date (status, departure_date, departure_time),
    CONSTRAINT fk_rides_driver FOREIGN KEY (driver_id)
      REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_rides_total_seats CHECK (total_seats BETWEEN 1 AND 4),
    CONSTRAINT chk_rides_available_seats CHECK (available_seats <= total_seats),
    CONSTRAINT chk_rides_price CHECK (price_per_seat >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bookings (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ride_id BIGINT UNSIGNED NOT NULL,
    passenger_id BIGINT UNSIGNED NOT NULL,
    seats_requested TINYINT UNSIGNED NOT NULL DEFAULT 1,
    status ENUM('pending','accepted','declined','cancelled') NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_bookings_ride_status (ride_id, status),
    KEY idx_bookings_passenger_created (passenger_id, created_at),
    CONSTRAINT fk_bookings_ride FOREIGN KEY (ride_id)
      REFERENCES rides(id) ON DELETE CASCADE,
    CONSTRAINT fk_bookings_passenger FOREIGN KEY (passenger_id)
      REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_bookings_seats CHECK (seats_requested BETWEEN 1 AND 4)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
