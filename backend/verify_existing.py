import database
from sqlalchemy.orm import Session

def verify_existing_users():
    db = database.SessionLocal()
    try:
        users = db.query(database.User).all()
        for user in users:
            if not user.is_verified:
                user.is_verified = 1
                print(f"✓ Verified user: {user.email}")
        db.commit()
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    verify_existing_users()
