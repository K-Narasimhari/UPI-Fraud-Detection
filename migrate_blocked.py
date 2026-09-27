import sqlite3
import os

# Set database path
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'database', 'users.db')

def migrate():
    print(f"Connecting to database at: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Add blocked_until column to user table
        print("Checking if 'blocked_until' column exists...")
        cursor.execute("PRAGMA table_info(user)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'blocked_until' not in columns:
            print("Adding 'blocked_until' column...")
            cursor.execute("ALTER TABLE user ADD COLUMN blocked_until DATETIME")
            print("Column added successfully!")
        else:
            print("'blocked_until' column already exists.")

        conn.commit()
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
