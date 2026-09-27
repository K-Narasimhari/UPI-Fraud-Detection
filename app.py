from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
import os
import sys

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import threading
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# -------------------
# APP SETUP
# -------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'upi-fraud-detection-secret'

# Safe database path setup
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'database')
if not os.path.exists(db_path):
    os.makedirs(db_path)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(db_path, 'users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------------------
# EMAIL CONFIGURATION
# -------------------
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

mail = Mail(app)

# Check if simulation mode is active
SIMULATE_NOTIFICATIONS = os.getenv('SIMULATE_NOTIFICATIONS', 'True') == 'True'

# -------------------
# ML MODEL LOADING
# -------------------
MODEL_PATH = 'models/fraud_model.joblib'
FEATURES_PATH = 'models/features.joblib'

try:
    if os.path.exists(MODEL_PATH) and os.path.exists(FEATURES_PATH):
        fraud_model = joblib.load(MODEL_PATH)
        ml_features = joblib.load(FEATURES_PATH)
        ML_MODEL_LOADED = True
        print(f"✅ ML Model loaded successfully with features: {ml_features}")
    else:
        ML_MODEL_LOADED = False
        print("[ML] Model files not found. Using rule-based detection only.")
except Exception as e:
    ML_MODEL_LOADED = False
    print(f"❌ Failed to load ML model: {str(e)}")

print("\n" + "*"*50)
print("--- UPI FRAUD DETECTION SERVICE STARTED ---")
print(f"   Mode: {'SIMULATION' if SIMULATE_NOTIFICATIONS else 'REAL EMAIL'}")
print(f"   SMTP Server: {app.config['MAIL_SERVER']}")
print(f"   Sender: {app.config['MAIL_DEFAULT_SENDER']}")
print(f"   ML Model: {'ACTIVE' if ML_MODEL_LOADED else 'INACTIVE'}")
print("*"*50 + "\n")

# -------------------
# DATABASE MODELS
# -------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True) # Mobile number for SMS
    balance = db.Column(db.Float, default=50000.0)
    upi_id = db.Column(db.String(100), unique=True, nullable=False)
    pin = db.Column(db.String(4), nullable=False, default="1234")
    blocked_until = db.Column(db.DateTime, nullable=True) # Persistent security block
    reset_otp = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    @property
    def all_transactions(self):
        """Returns both sent and received transactions."""
        return Transaction.query.filter(
            (Transaction.sender_id == self.id) | 
            (Transaction.receiver_upi == self.upi_id)
        ).order_by(Transaction.timestamp.desc()).all()

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_transactions')
    receiver_upi = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(50))  # SUCCESS / SUSPICIOUS / BLOCKED
    risk_score = db.Column(db.Float, default=0.0)
    risk_reason = db.Column(db.String(500), nullable=True) # XAI: Explain why it was flagged

# -------------------
# UTILITIES
# -------------------
def send_sms_simulation(phone, message):
    """Simulates sending an SMS by printing to terminal."""
    print("\n" + "📱 " + "="*46)
    print(f"   [SIMULATED SMS SENT TO: {phone}]")
    print(f"   Message: {message}")
    print("   " + "="*46 + "\n")
def send_async_email(app, msg):
    """Sends email in a background thread."""
    with app.app_context():
        try:
            print(f"📤 [THREAD] Attempting to send REAL EMAIL to {msg.recipients}...")
            mail.send(msg)
            print(f"[THREAD] REAL EMAIL SENT SUCCESSFULLY to {msg.recipients}")
        except Exception as e:
            error_msg = f"[THREAD] Failed to send email: {str(e)}\n"
            print(error_msg)
            with open("notifications.log", "a", encoding="utf-8") as f:
                f.write(error_msg)

def send_transaction_notification(user, subject, body):
    """Sends email notification (asynchronously) and logs it."""
    log_msg = f"[{datetime.now()}] To: {user.email} | Subject: {subject}\n"
    with open("notifications.log", "a", encoding="utf-8") as f:
        f.write(log_msg)

    if SIMULATE_NOTIFICATIONS:
        print("\n" + "📧 " + "="*46)
        print(f"   [SIMULATED EMAIL SENT TO: {user.email}]")
        print(f"   Subject: {subject}")
        print(f"   Body: {body}")
        print("   " + "="*46 + "\n")
        return True
    
    # Create the message object
    msg = Message(subject, recipients=[user.email])
    msg.body = body
    
    # Start the background thread
    thread = threading.Thread(target=send_async_email, args=(app, msg))
    thread.start()
    return True

def generate_risk_explanation(amount, risk_score, velocity, is_night, recent_tx_count):
    """Generates a human-readable explanation for the transaction risk score."""
    reasons = []
    
    if amount > 20000:
        reasons.append(f"Transaction amount (₹{amount}) exceeds the safety threshold of ₹20,000.")
    elif amount > 10000:
        reasons.append(f"High-value transaction detected (₹{amount}).")

    if is_night:
        reasons.append("Transaction initiated during unusual late-night hours (11 PM - 5 AM).")
    
    if recent_tx_count >= 3:
        reasons.append(f"High transaction frequency detected ({recent_tx_count} attempts in 5 minutes).")
    elif velocity < 60:
        reasons.append(f"Very high velocity: Only {round(velocity, 1)} seconds since last transaction.")

    if risk_score > 0.7:
        reasons.append(f"AI Model identified behavioral patterns consistent with known fraud (Confidence: {round(risk_score*100, 1)}%).")
    elif risk_score > 0.4:
        reasons.append("AI Model detected moderate behavioral anomalies.")

    if not reasons:
        return "Transaction matches your typical spending patterns. Low risk detected."
    
    return " | ".join(reasons)

# -------------------
# ROUTES
# -------------------

@app.route("/")
def home():
    """Serves the modernized UPI Fraud Detection landing page."""
    return render_template("landing.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        name = request.form.get("name")
        password = request.form.get("password")
        phone = request.form.get("phone")
        pin = request.form.get("pin")

        # Basic Validation
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return "Email already registered. Please login.", 400

        # Generate a dummy UPI ID based on name
        upi_id = f"{name.lower().replace(' ', '')}@alertsystem"
        
        new_user = User(
            name=name,
            email=email,
            password=password,
            phone=phone,
            upi_id=upi_id,
            pin=pin
        )

        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        print(f"DEBUG LOGIN: Email=|{email}| Password=|{password}|")
        user = User.query.filter_by(email=email, password=password).first()
        if user:
            print(f"DEBUG LOGIN: Success for {email}")
            return redirect(url_for('dashboard', user_id=user.id))
        
        print(f"DEBUG LOGIN: Failed for {email}")
        return "Invalid Credentials", 401

    return render_template("login.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Option 1: Send current PIN (as requested by user)
            # Option 2: Generate OTP for password reset
            import random
            otp = str(random.randint(100000, 999999))
            user.reset_otp = otp
            user.otp_expiry = datetime.now() + timedelta(minutes=10)
            db.session.commit()
            
            subject = "🔒 Account Recovery - UPI Fraud Detection"
            body = f"Hello {user.name},\n\nYou requested to recover your account.\n\n"
            body += f"Your current PIN is: {user.pin}\n\n"
            body += f"To reset your password, use this OTP: {otp}\n"
            body += "This OTP will expire in 10 minutes.\n\n"
            body += "If you did not request this, please ignore this email.\n\n"
            body += "Thank you,\nUPI Fraud Detection and Real-time Alert System"
            
            send_transaction_notification(user, subject, body)
            flash("Recovery email sent! Please check your inbox for your PIN and reset OTP.", "success")
            return redirect(url_for('reset_password'))
        
        flash("Email not found in our records.", "danger")
    return render_template("forgot_password.html")

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        otp = request.form.get("otp")
        new_password = request.form.get("password")
        
        user = User.query.filter_by(reset_otp=otp).first()
        
        if user and user.otp_expiry > datetime.now():
            user.password = new_password
            user.reset_otp = None
            user.otp_expiry = None
            db.session.commit()
            flash("Password reset successful! You can now login with your new password.", "success")
            return redirect(url_for('login'))
        
        flash("Invalid or expired OTP.", "danger")
    return render_template("reset_password.html")

@app.route("/dashboard/<int:user_id>")
def dashboard(user_id):
    user = User.query.get_or_404(user_id)
    
    # Check if block has expired (User-specific)
    if user.blocked_until:
        if datetime.now() > user.blocked_until:
            user.blocked_until = None
            db.session.commit()
            flash("🛡️ Security Restriction Lifted: Your account is now fully active.", "success")
    
    # Generate QR Code URL using a public API
    # Format: upi://pay?pa=recipient@upi&pn=RecipientName
    upi_payload = f"upi://pay?pa={user.upi_id}&pn={user.name.replace(' ', '%20')}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={upi_payload}"
            
    return render_template("dashboard.html", user=user, qr_url=qr_url)

@app.route("/settings/<int:user_id>", methods=["GET", "POST"])
def settings(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        user.name = request.form.get("name")
        user.phone = request.form.get("phone")
        new_password = request.form.get("password")
        new_pin = request.form.get("pin")
        
        if new_password:
            user.password = new_password
        if new_pin:
            user.pin = new_pin
            
        db.session.commit()
        return redirect(url_for('dashboard', user_id=user.id))
    return render_template("settings.html", user=user)

@app.route("/transaction/<int:user_id>", methods=["GET", "POST"])
def transaction(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        amount = float(request.form.get("amount", 0))
        receiver = request.form.get("receiver_upi")
        provided_pin = request.form.get("pin")

        # PIN Verification
        if provided_pin != user.pin:
            flash("❌ Incorrect PIN. Please try again.", "danger")
            return redirect(url_for('transaction', user_id=user.id))

        # Receiver Validation
        receiver_user = User.query.filter_by(upi_id=receiver).first()
        if not receiver_user:
            flash("❌ Enter correct account UPID. Receiver does not exist.", "danger")
            return redirect(url_for('transaction', user_id=user.id))

        # --- ML RISK SCORING ---
        current_time = datetime.now()
        risk_score = 0.05 # Default low risk
        
        if ML_MODEL_LOADED:
            # Calculate features
            hour = current_time.hour
            day_of_week = current_time.weekday()
            is_night = 1 if (hour <= 5 or hour >= 23) else 0
            
            # Velocity calculation (time since last transaction in seconds)
            last_tx = Transaction.query.filter_by(sender_id=user.id).order_by(Transaction.timestamp.desc()).first()
            if last_tx:
                velocity = (current_time - last_tx.timestamp).total_seconds()
            else:
                velocity = 86400 # Default to 1 day if no previous tx
            
            # Prepare feature vector for model
            # ['amount', 'hour', 'day_of_week', 'velocity', 'is_night']
            feature_data = [amount, hour, day_of_week, velocity, is_night]
            features = pd.DataFrame([feature_data], columns=ml_features)
            
            # Save to session for visibility in Analysis/Dashboard
            session['last_features'] = {
                'amount': amount,
                'hour': hour,
                'day_of_week': day_of_week,
                'velocity': round(velocity, 2),
                'is_night': is_night
            }
            
            # Get probability of class 1 (fraud)
            risk_score = float(fraud_model.predict_proba(features)[0][1])
            print(f"DEBUG: ML Risk Score for Tx: {risk_score}")
        else:
            # Basic defaults for rule-based mode
            hour = current_time.hour
            is_night = 1 if (hour <= 5 or hour >= 23) else 0
            velocity = 86400

        # Calculate common metrics for XAI
        five_minutes_ago = datetime.now() - timedelta(minutes=5)
        recent_tx_count = Transaction.query.filter(
            Transaction.sender_id == user.id,
            Transaction.timestamp >= five_minutes_ago
        ).count()
        
        # Recalculate velocity if not already done in ML block
        if not ML_MODEL_LOADED:
            last_tx = Transaction.query.filter_by(sender_id=user.id).order_by(Transaction.timestamp.desc()).first()
            if last_tx:
                velocity = (current_time - last_tx.timestamp).total_seconds()
            else:
                velocity = 86400

        # --- ADVANCED FRAUD DETECTION RULES ---
        
        # Rule 1: Threshold Check
        if amount > 20000:
            txn = Transaction(
                sender_id=user.id,
                receiver_upi=receiver,
                amount=amount,
                status="BLOCKED",
                risk_score=0.95,
                risk_reason=generate_risk_explanation(amount, 0.95, velocity, is_night, recent_tx_count)
            )
            db.session.add(txn)
            db.session.commit()

            # Security Alert Email
            block_body = f"Hello {user.name},\n\nA transaction of ₹{amount} to {receiver} was BLOCKED because it exceeds your safety threshold of ₹20,000.\n\nIf you did not authorize this, please secure your account immediately.\n\nThank you,\nUPI Fraud Detection and Real-time Alert System"
            send_transaction_notification(user, "⚠️ Security Alert: Transaction Blocked", block_body)

            return render_template("blocked.html", amount=amount, receiver=receiver, user_id=user.id, risk_reason=txn.risk_reason)

        # Rule 2: Balance Check
        if amount > user.balance:
            flash("❌ Transaction Failed: Insufficient funds in your account.", "danger")
            return redirect(url_for('transaction', user_id=user.id))

        # Rule 3: Velocity Check (Multiple transactions in a short time)
        five_minutes_ago = datetime.now() - timedelta(minutes=5)
        recent_tx_count = Transaction.query.filter(
            Transaction.sender_id == user.id,
            Transaction.timestamp >= five_minutes_ago
        ).count()

        if recent_tx_count >= 3:
            txn = Transaction(
                sender_id=user.id,
                receiver_upi=receiver,
                amount=amount,
                status="SUSPICIOUS",
                risk_score=0.8,
                risk_reason=generate_risk_explanation(amount, 0.8, velocity, is_night, recent_tx_count)
            )
            db.session.add(txn)
            db.session.commit()
            
            # Set a 5-minute block persistently for this user
            user.blocked_until = datetime.now() + timedelta(minutes=5)
            db.session.commit()
            
            # Security Alert Email
            restrict_body = f"Hello {user.name},\n\nYour account has been TEMPORARILY RESTRICTED for 5 minutes due to multiple rapid transaction attempts. This is a proactive measure to protect your balance from potential velocity-based fraud.\n\nYou can try transacting again after 5 minutes.\n\nThank you,\nUPI Fraud Detection and Real-time Alert System"
            send_transaction_notification(user, "⚠️ Security Alert: Account Temporarily Restricted", restrict_body)

            flash("⚠️ Security Alert: Multiple rapid transactions detected. Account temporarily restricted.", "danger")
            return redirect(url_for('dashboard', user_id=user.id))

        # Rule 4: ML Risk Threshold
        if risk_score > 0.7:
            txn = Transaction(
                sender_id=user.id,
                receiver_upi=receiver,
                amount=amount,
                status="SUSPICIOUS",
                risk_score=risk_score,
                risk_reason=generate_risk_explanation(amount, risk_score, velocity, is_night, recent_tx_count)
            )
            db.session.add(txn)
            db.session.commit()
            
            # Security Alert Email
            ml_body = f"Hello {user.name},\n\nA transaction of ₹{amount} to {receiver} was flagged as SUSPICIOUS by our AI monitoring system (Risk Score: {round(risk_score*100, 1)}%).\n\nIf you did not authorize this, please contact support immediately.\n\nThank you,\nUPI Fraud Detection and Real-time Alert System"
            send_transaction_notification(user, "⚠️ Security Alert: Suspicious Activity Detected", ml_body)

            flash(f"⚠️ Security Alert: Transaction flagged as suspicious by AI monitoring (Risk: {round(risk_score*100, 1)}%).", "warning")
            # We don't block success here yet, but we log it as suspicious. 
            # Or should we block it? Let's treat > 0.85 as block.
            if risk_score > 0.9:
                return render_template("blocked.html", amount=amount, receiver=receiver, user_id=user.id, risk_reason=txn.risk_reason)

        # Process Success
        user.balance -= amount
        
        # Credit receiver (already validated above)
        receiver_user.balance += amount
        # SMS to Receiver
        if receiver_user.phone:
            msg = f"₹{amount} received from {user.name} ({user.upi_id}). New balance: ₹{receiver_user.balance}"
            send_sms_simulation(receiver_user.phone, msg)
        
        # Email to Receiver
        rec_body = f"Hello {receiver_user.name},\n\nYou have received ₹{amount} from {user.name} ({user.upi_id}).\nYour updated balance is ₹{receiver_user.balance}.\n\nThank you for using UPI Fraud Detection and Real-time Alert System!"
        send_transaction_notification(receiver_user, "Payment Received - UPI Fraud Detection", rec_body)

        txn = Transaction(
            sender_id=user.id,
            receiver_upi=receiver,
            amount=amount,
            status="SUCCESS",
            risk_score=risk_score,
            risk_reason=generate_risk_explanation(amount, risk_score, velocity, is_night, recent_tx_count)
        )
        db.session.add(txn)
        db.session.commit()
        
        # Notification to Sender
        sender_msg = f"₹{amount} sent to {receiver}. New balance: ₹{user.balance}"
        if user.phone:
            send_sms_simulation(user.phone, sender_msg)
        
        sender_body = f"Hello {user.name},\n\nYou have successfully sent ₹{amount} to {receiver}.\nYour updated balance is ₹{user.balance}.\n\nIf this wasn't you, please contact support immediately.\n\nThank you for using UPI Fraud Detection and Real-time Alert System!"
        send_transaction_notification(user, "Transaction Successful - UPI Fraud Detection", sender_body)

        flash(f"✅ Transaction Successful! (AI Risk Score: {round(risk_score * 100, 1)}%)", "success")
        return redirect(url_for('success', amount=amount, receiver=receiver, user_id=user.id))

    return render_template("transaction.html", user=user)

@app.route("/analysis/<int:user_id>")
def analysis(user_id):
    user = User.query.get_or_404(user_id)
    # Calculate metrics for AI dashboard
    all_txns = user.all_transactions
    total_count = len(all_txns)
    blocked_count = sum(1 for t in all_txns if t.status == 'BLOCKED')
    suspicious_count = sum(1 for t in all_txns if t.status == 'SUSPICIOUS')
    
    # Mock risk score (usually low for good users)
    avg_risk = sum(t.risk_score for t in all_txns) / total_count if total_count > 0 else 0.05
    security_score = max(0, 100 - (avg_risk * 100))
    
    # Get the last ingested features from the session
    last_features = session.get('last_features')
    
    # Get the last transaction for this specific user to show details
    last_txn = Transaction.query.filter_by(sender_id=user.id).order_by(Transaction.timestamp.desc()).first()
    risk_reason = last_txn.risk_reason if last_txn else None
    
    return render_template("analysis.html", 
                         user=user, 
                         total_count=total_count, 
                         blocked_count=blocked_count, 
                         suspicious_count=suspicious_count,
                         security_score=round(security_score, 1),
                         last_features=last_features,
                         risk_reason=risk_reason)

@app.route("/history/<int:user_id>")
def history(user_id):
    user = User.query.get_or_404(user_id)
    search_query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'All Status')

    # Base query: user's sent transactions or successful received transactions
    # Note: Suspicious/Blocked received transactions aren't shown to receiver for security
    query = Transaction.query.filter(
        (Transaction.sender_id == user.id) | 
        (Transaction.receiver_upi == user.upi_id)
    )

    if search_query:
        # Check if search query is numeric (for User ID search)
        is_numeric_id = search_query.isdigit()
        search_id = int(search_query) if is_numeric_id else None

        # 1. Match query directly against Transaction.receiver_upi
        # 2. Match query directly against Sender's properties (Name, Email, Phone, UPI, ID)
        # 3. If query matches a User in the DB, also get transactions where they are the receiver
        
        matching_users = User.query.filter(
            (User.name.ilike(f"%{search_query}%")) |
            (User.upi_id.ilike(f"%{search_query}%")) |
            (User.phone.ilike(f"%{search_query}%")) |
            (User.email.ilike(f"%{search_query}%")) |
            (User.id == search_id if is_numeric_id else False)
        ).all()
        
        matching_upi_ids = [u.upi_id for u in matching_users]

        query = query.filter(
            (Transaction.receiver_upi.ilike(f"%{search_query}%")) |
            (Transaction.receiver_upi.in_(matching_upi_ids)) |
            (Transaction.sender.has(User.name.ilike(f"%{search_query}%"))) |
            (Transaction.sender.has(User.email.ilike(f"%{search_query}%"))) |
            (Transaction.sender.has(User.phone.ilike(f"%{search_query}%"))) |
            (Transaction.sender.has(User.upi_id.ilike(f"%{search_query}%"))) |
            (Transaction.sender_id == search_id if is_numeric_id else False)
        )

    if status_filter != 'All Status':
        query = query.filter(Transaction.status == status_filter.upper())

    transactions = query.order_by(Transaction.timestamp.desc()).all()
    
    return render_template("history.html", user=user, transactions=transactions, q=search_query, status=status_filter)

@app.route("/success")
def success():
    amount = request.args.get('amount')
    receiver = request.args.get('receiver')
    user_id = request.args.get('user_id')
    last_features = session.get('last_features')
    
    # Get the last transaction for this specific user/session
    last_txn = Transaction.query.order_by(Transaction.timestamp.desc()).first()
    risk_reason = last_txn.risk_reason if last_txn else None

    return render_template("success.html", amount=amount, receiver=receiver, last_features=last_features, risk_reason=risk_reason, user_id=user_id)

@app.route("/api/transaction/<int:txn_id>")
def get_transaction_details(txn_id):
    txn = Transaction.query.get_or_404(txn_id)
    
    # Get receiver info
    receiver_user = User.query.filter_by(upi_id=txn.receiver_upi).first()
    
    data = {
        "id": txn.id,
        "amount": txn.amount,
        "timestamp": txn.timestamp.strftime('%d %b %Y, %H:%M:%S'),
        "status": txn.status,
        "risk_score": txn.risk_score,
        "sender_name": txn.sender.name,
        "sender_upi": txn.sender.upi_id,
        "receiver_name": receiver_user.name if receiver_user else "External Entity",
        "receiver_upi": txn.receiver_upi
    }
    return data

# -------------------
# INITIALIZATION
# -------------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)