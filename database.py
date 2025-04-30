import sqlite3
import os
from flask import g, current_app

DATABASE = 'ads_project.db'

def get_db():
    """Connect to the database and return the connection"""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        # Enable row factory to access columns by name
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """Close the database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    """Initialize the database"""
    # Register close_db with teardown_appcontext
    app.teardown_appcontext(close_db)
    
    try:
        # Create database if it doesn't exist
        if not os.path.exists(DATABASE):
            with app.app_context():
                db = get_db()
                with app.open_resource('schema.sql', mode='r') as f:
                    db.executescript(f.read())
                
                # Insert sample ads
                cursor = db.cursor()
                cursor.execute(
                    "INSERT INTO ads (title, video_url, duration) VALUES (?, ?, ?)",
                    ('Ad 1', '/static/videos/static/videos/Atif aslam (AADAT UNPLUGGED).mp4', 30)
                )
                cursor.execute(
                    "INSERT INTO ads (title, video_url, duration) VALUES (?, ?, ?)",
                    ('Ad 2', '/static/videos/Atif aslam (AADAT UNPLUGGED).mp4', 15)
                )
                cursor.execute(
                    "INSERT INTO ads (title, video_url, duration) VALUES (?, ?, ?)",
                    ('Ad 3', '/static/videos/ad3.mp4', 45)
                )
                db.commit()
                print("Database initialized with sample data")
    except Exception as e:
        print(f"Error initializing database: {e}")
        # If there was an error, remove the potentially corrupted database file
        if os.path.exists(DATABASE):
            os.remove(DATABASE)
            print("Removed corrupted database file")

def add_user(name, email, password):
    """Helper function to add a user to the database"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if email already exists
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            return False, "Email already registered"
        
        # Insert new user
        cursor.execute(
            "INSERT INTO users (name, email, password, balance) VALUES (?, ?, ?, ?)",
            (name, email, password, 0)
        )
        db.commit()
        return True, "Registration successful! Please login."
    except sqlite3.Error as e:
        db.rollback()
        return False, f"Database error: {e}"
    except Exception as e:
        return False, f"An error occurred: {e}"
