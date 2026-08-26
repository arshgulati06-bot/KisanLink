import os
import mysql.connector
from mysql.connector import Error

def get_db_connection():
    """
    Attempts to establish a connection to the MySQL database using environment variables.
    Returns:
        connection object if successful, None otherwise.
    """
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", 3306))
    db_user = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASSWORD", "root")
    db_name = os.getenv("DB_NAME", "kisanlink_db")

    try:
        connection = mysql.connector.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"[DB Warning] Graceful MySQL connection check failed: {e}")
        return None
    return None

def check_db_connection():
    """
    Checks MySQL database connectivity without throwing unhandled exceptions.
    Returns:
        tuple: (is_connected: bool, details_message: str)
    """
    connection = get_db_connection()
    if connection is not None and connection.is_connected():
        connection.close()
        return True, "Successfully connected to MySQL database."
    else:
        return False, "Could not connect to MySQL server. Ensure MySQL service is running and credentials/database exist."
