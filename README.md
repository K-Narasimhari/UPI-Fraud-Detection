# UPI Fraud Detection and Real-time Alert System

This is a simulated AI-powered web application designed to detect and prevent UPI fraud in real-time. It uses rule-based and behavioral analysis to identify suspicious transactions.

## Features
- **Real-time Monitoring**: Every transaction is analyzed for risk factors.
- **Safety Thresholds**: Transactions exceeding ₹20,000 are automatically blocked.
- **Modern Dashboard**: Track your balance and recent transaction history.
- **Secure Authentication**: User data is protected via centralized monitoring.

## Setup Instructions

### Prerequisites
- Python 3.8+
- SQLite (included)

### 1. Set Up Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate
```

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Run the Application
```powershell
python app.py
```
The app will be available at `http://127.0.0.1:5000/`.

## Academic Simulation
> [!NOTE]
> This project is for demo and academic purposes only. It does not connect to real bank accounts or UPI networks.
