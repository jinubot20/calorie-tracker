#!/usr/bin/env python3
"""
Password Reset Script for Calorie Tracker
Usage: python3 reset_password.py
"""

import sys
import getpass
import database
import auth

def reset_password():
    """Reset password for a user"""
    print("=" * 50)
    print("Calorie Tracker - Password Reset")
    print("=" * 50)
    print()

    # Get user email
    email = input("Enter your email address: ").strip()

    if not email:
        print("❌ Email is required")
        return

    # Create database session
    db = database.SessionLocal()

    try:
        # Check if user exists
        user = db.query(database.User).filter(database.User.email == email).first()

        if not user:
            print(f"❌ No user found with email: {email}")
            print("\nExisting users:")
            for u in db.query(database.User).all():
                print(f"  - {u.email} ({u.name})")
            return

        print(f"\n✓ User found: {user.name} ({user.email})")

        # Get new password
        password = getpass.getpass("Enter new password: ")
        if not password:
            print("❌ Password is required")
            return

        confirm_password = getpass.getpass("Confirm new password: ")
        if password != confirm_password:
            print("❌ Passwords do not match")
            return

        # Update password
        user.hashed_password = auth.get_password_hash(password)
        db.commit()

        print("\n✓ Password updated successfully!")
        print(f"\nYou can now login at: https://georgine-glebal-nenita.ngrok-free.dev")
        print(f"Email: {email}")
        print(f"Password: (your new password)")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reset_password()
