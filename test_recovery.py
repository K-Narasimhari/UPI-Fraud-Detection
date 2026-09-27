import os
import sys
from datetime import datetime, timedelta

# Mocking Flask app context for testing
from app import app, db, User

def test_recovery_flow():
    with app.app_context():
        print("Starting recovery flow test...")
        
        # 1. Create a test user
        test_email = "test_recovery@example.com"
        User.query.filter_by(email=test_email).delete()
        db.session.commit()
        
        test_user = User(
            name="Test User",
            email=test_email,
            password="oldpassword",
            upi_id="testuser@alertsystem",
            pin="9999"
        )
        db.session.add(test_user)
        db.session.commit()
        print(f"Created test user: {test_email}")
        
        # 2. Simulate forgot password request
        user = User.query.filter_by(email=test_email).first()
        import random
        otp = str(random.randint(100000, 999999))
        user.reset_otp = otp
        user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()
        print(f"Generated OTP: {otp} for user {user.email}")
        
        # 3. Verify OTP storage
        user_after = User.query.filter_by(reset_otp=otp).first()
        if not user_after or user_after.email != test_email:
            print("❌ OTP storage verification failed!")
            return
        print("✅ OTP storage verified.")
        
        # 4. Simulate password reset
        new_password = "newpassword123"
        if user_after.otp_expiry > datetime.utcnow():
            user_after.password = new_password
            user_after.reset_otp = None
            user_after.otp_expiry = None
            db.session.commit()
            print("✅ Password reset simulation successful.")
        else:
            print("❌ OTP expired during test!")
            return
            
        # 5. Verify password change
        final_user = User.query.filter_by(email=test_email).first()
        if final_user.password == new_password:
            print("✅ Final password verification successful.")
        else:
            print("❌ Password was not updated!")
            return
            
        # Cleanup
        # db.session.delete(final_user)
        # db.session.commit()
        print("All recovery tests passed!")

if __name__ == "__main__":
    test_recovery_flow()
