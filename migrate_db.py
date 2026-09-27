import sqlite3
import os

db_path = os.path.join('database', 'users.db')

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add phone column to user table
        cursor.execute("ALTER TABLE user ADD COLUMN phone VARCHAR(20)")
        conn.commit()
        conn.close()
        print("✅ Database migration successful: Added 'phone' column to User table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("ℹ️ Column 'phone' already exists.")
        else:
            print(f"❌ Migration failed: {e}")
else:
    print("ℹ️ No database found. It will be created fresh on next app start.")
