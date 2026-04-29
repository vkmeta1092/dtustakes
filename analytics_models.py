from datetime import datetime, date
from models import db


class VisitorSession(db.Model):
    __tablename__ = "visitor_sessions"

    id = db.Column(db.Integer, primary_key=True)
    session_key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    ip_address = db.Column(db.String(100), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    total_hits = db.Column(db.Integer, default=0)

    events = db.relationship('AppEvent', backref='visitor_session', lazy=True, cascade='all, delete-orphan')


class AppEvent(db.Model):
    __tablename__ = "app_events"

    id = db.Column(db.Integer, primary_key=True)
    visitor_session_id = db.Column(db.Integer, db.ForeignKey('visitor_sessions.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    event_type = db.Column(db.String(50), nullable=False, index=True)
    page = db.Column(db.String(120), nullable=True)
    event_value = db.Column(db.Integer, default=0)

    meta = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class DailyAnalytics(db.Model):
    __tablename__ = "daily_analytics"

    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, unique=True, nullable=False, index=True)

    visitors = db.Column(db.Integer, default=0)
    unique_visitors = db.Column(db.Integer, default=0)
    signups = db.Column(db.Integer, default=0)
    logins = db.Column(db.Integer, default=0)

    bets_placed = db.Column(db.Integer, default=0)
    reveals = db.Column(db.Integer, default=0)
    verify_page_visits = db.Column(db.Integer, default=0)

    credits_wagered = db.Column(db.Integer, default=0)
    credits_paid_out = db.Column(db.Integer, default=0)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)