import pytest
from app import app, db, User, Transaction
from datetime import datetime, timedelta

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()

def test_user_registration(client):
    response = client.post('/register', data={
        'name': 'New Agent',
        'email': 'agent@sentinel.ai',
        'password': 'password123',
        'phone': '9876543210',
        'pin': '1234'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email='agent@sentinel.ai').first()
        assert user is not None
        assert user.upi_id == 'newagent@alertsystem'
        assert user.pin == '1234'

def test_user_login(client):
    # Setup user
    with app.app_context():
        user = User(name="Existing Agent", email="existing@sentinel.ai", password="password123", upi_id="existing@alertsystem", pin="1111")
        db.session.add(user)
        db.session.commit()
    
    response = client.post('/login', data={
        'email': 'existing@sentinel.ai',
        'password': 'password123'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b"Active Session: Existing Agent" in response.data

def test_transaction_pin_validation(client):
    with app.app_context():
        user = User(name="Sender", email="sender@sentinel.ai", password="password", upi_id="sender@alertsystem", balance=1000.0, pin="1234")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    # Wrong PIN
    response = client.post(f'/transaction/{user_id}', data={
        'amount': '100',
        'receiver_upi': 'somebody@upi',
        'pin': '0000'
    }, follow_redirects=True)
    
    assert b"Incorrect PIN" in response.data
    
    with app.app_context():
        user = User.query.get(user_id)
        assert user.balance == 1000.0

def test_fraud_threshold_blocking(client):
    with app.app_context():
        user = User(name="HighRoller", email="hr@sentinel.ai", password="password", upi_id="hr@alertsystem", balance=100000.0, pin="1234")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    response = client.post(f'/transaction/{user_id}', data={
        'amount': '25000',
        'receiver_upi': 'scammer@upi',
        'pin': '1234'
    }, follow_redirects=True)
    
    assert b"DELTA BLOCKED" in response.data
    assert b"Impact Magnitude" in response.data
    assert b"25,000.00" in response.data

def test_velocity_check_blocking(client):
    with app.app_context():
        user = User(name="FastMover", email="fast@sentinel.ai", password="password", upi_id="fast@alertsystem", balance=10000.0, pin="1234")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    # 3 quick transactions
    for i in range(3):
        client.post(f'/transaction/{user_id}', data={
            'amount': '10',
            'receiver_upi': f'rec{i}@upi',
            'pin': '1234'
        })
    
    # 4th transaction should trigger velocity block
    response = client.post(f'/transaction/{user_id}', data={
        'amount': '10',
        'receiver_upi': 'rec4@upi',
        'pin': '1234'
    }, follow_redirects=True)
    
    assert b"temporarily restricted" in response.data
    assert b"Behavioral anomalies detected" in response.data

def test_successful_transfer_and_balance(client):
    with app.app_context():
        sender = User(name="Sender", email="s@s.ai", password="p", upi_id="s@upi", balance=1000.0, pin="1234")
        receiver = User(name="Receiver", email="r@r.ai", password="p", upi_id="r@upi", balance=500.0, pin="1234")
        db.session.add(sender)
        db.session.add(receiver)
        db.session.commit()
        sender_id = sender.id
        receiver_id = receiver.id

    response = client.post(f'/transaction/{sender_id}', data={
        'amount': '200',
        'receiver_upi': 'r@upi',
        'pin': '1234'
    }, follow_redirects=True)
    
    assert b"Transaction Verified" in response.data
    assert b"200" in response.data
    
    with app.app_context():
        s = User.query.get(sender_id)
        r = User.query.get(receiver_id)
        assert s.balance == 800.0
        assert r.balance == 700.0
