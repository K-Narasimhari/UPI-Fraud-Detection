import pytest
from app import app, db, User, Transaction

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()

def test_fraud_detection_threshold(client):
    # Setup test user
    with app.app_context():
        user = User(name="Test User", email="test@example.com", password="password", upi_id="test@guardupi", balance=50000.0, phone="1234567890")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    # Simulate transaction > 20,000
    response = client.post(f'/transaction/{user_id}', data={
        'amount': '25000',
        'receiver_upi': 'hacker@upi'
    }, follow_redirects=True)

    assert response.status_code == 403
    assert b"Security Alert" in response.data

    # Check Transaction record
    with app.app_context():
        txn = Transaction.query.filter_by(sender_id=user_id).first()
        assert txn.status == "BLOCKED"
        assert txn.amount == 25000.0

def test_insufficient_funds(client):
    with app.app_context():
        user = User(name="PoorUser", email="poor@example.com", password="password", upi_id="poor@guardupi", balance=10.0, phone="1234567890")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    response = client.post(f'/transaction/{user_id}', data={'amount': '50', 'receiver_upi': 'rich@upi'}, follow_redirects=True)
    assert response.status_code == 400
    assert b"Insufficient funds" in response.data

def test_successful_transaction(client):
    with app.app_context():
        user = User(name="RichUser", email="rich@example.com", password="password", upi_id="rich@guardupi", balance=5000.0, phone="1234567890")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    response = client.post(f'/transaction/{user_id}', data={'amount': '100', 'receiver_upi': 'someone@upi'}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome back, RichUser" in response.data
    assert b"someone@upi" in response.data

    with app.app_context():
        updated_user = User.query.get(user_id)
        assert updated_user.balance == 4900.0
        txn = Transaction.query.filter_by(sender_id=user_id).first()
        assert txn.status == "SUCCESS"

def test_transfer_between_users(client):
    with app.app_context():
        # Create Sender
        sender = User(name="Sender", email="sender@example.com", password="password", upi_id="sender@guardupi", balance=1000.0, phone="12345sender")
        # Create Receiver
        receiver = User(name="Receiver", email="receiver@example.com", password="password", upi_id="receiver@guardupi", balance=1000.0, phone="12345receiver")
        db.session.add(sender)
        db.session.add(receiver)
        db.session.commit()
        sender_id = sender.id
        receiver_id = receiver.id

    # Transfer 300
    response = client.post(f'/transaction/{sender_id}', data={
        'amount': '300',
        'receiver_upi': 'receiver@guardupi'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Welcome back, Sender" in response.data
    
    with app.app_context():
        s = User.query.get(sender_id)
        r = User.query.get(receiver_id)
        assert s.balance == 700.0
        assert r.balance == 1300.0

def test_velocity_check_blocks_multiple_txns(client):
    with app.app_context():
        user = User(name="SpeedUser", email="speed@example.com", password="password", upi_id="speed@guardupi", balance=10000.0, phone="12345speed")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    # 1st Transaction
    client.post(f'/transaction/{user_id}', data={'amount': '10', 'receiver_upi': 'r1@upi'}, follow_redirects=True)
    # 2nd Transaction
    client.post(f'/transaction/{user_id}', data={'amount': '10', 'receiver_upi': 'r2@upi'}, follow_redirects=True)
    # 3rd Transaction
    client.post(f'/transaction/{user_id}', data={'amount': '10', 'receiver_upi': 'r3@upi'}, follow_redirects=True)
    
    # 4th Transaction should be blocked by velocity check and redirect
    response = client.post(f'/transaction/{user_id}', data={'amount': '10', 'receiver_upi': 'r4@upi'}, follow_redirects=True)
    
    assert response.status_code == 200
    assert b"Account Temporarily Restricted" in response.data
    assert b"Unblocks In" in response.data

    with app.app_context():
        tx_count = Transaction.query.filter_by(sender_id=user_id).count()
        # 3 Success + 1 Suspicious/Blocked
        assert tx_count == 4
        last_tx = Transaction.query.filter_by(sender_id=user_id).order_by(Transaction.id.desc()).first()
        assert last_tx.status == "SUSPICIOUS"
