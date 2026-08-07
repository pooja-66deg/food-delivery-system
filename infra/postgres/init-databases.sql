-- Initialize separate databases for each microservice
-- Run by the postgres service on startup via init-database script

-- Create databases for each service
CREATE DATABASE orders_db;
CREATE DATABASE payments_db;
CREATE DATABASE delivery_db;
CREATE DATABASE users_db;
CREATE DATABASE restaurants_db;
CREATE DATABASE notifications_db;

-- Create schemas within each database
\c orders_db
CREATE SCHEMA IF NOT EXISTS orders;

\c payments_db
CREATE SCHEMA IF NOT EXISTS payments;

\c delivery_db
CREATE SCHEMA IF NOT EXISTS delivery;

\c users_db
CREATE SCHEMA IF NOT EXISTS users;

\c restaurants_db
CREATE SCHEMA IF NOT EXISTS restaurants;

\c notifications_db
CREATE SCHEMA IF NOT EXISTS notifications;

-- Return to default database
\c postgres
