from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    credits = db.Column(db.Integer, default=100, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bets = db.relationship('Bet', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Draw(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server_seed = db.Column(db.String(64), nullable=False)
    hashed_server_seed = db.Column(db.String(64), nullable=False, index=True)
    nonce = db.Column(db.Integer, default=0, nullable=False)
    open_digit = db.Column(db.Integer, nullable=True)
    jodi = db.Column(db.String(10), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    bets = db.relationship('Bet', backref='draw', lazy=True, cascade='all, delete-orphan')


class Bet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    draw_id = db.Column(db.Integer, db.ForeignKey('draw.id'), nullable=False)
    bet_type = db.Column(db.String(20), nullable=False)
    pick = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    won = db.Column(db.Integer, default=0, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)