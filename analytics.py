from datetime import datetime, date, timedelta
import json
import secrets

from flask import request, session, render_template
from sqlalchemy import func

from models import db, User, Bet
from analytics_models import VisitorSession, AppEvent, DailyAnalytics


def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def get_or_create_session_key():
    if 'analytics_session_key' not in session:
        session['analytics_session_key'] = secrets.token_hex(16)
    return session['analytics_session_key']


def get_or_create_daily_row(day_value=None):
    if day_value is None:
        day_value = date.today()

    row = DailyAnalytics.query.filter_by(day=day_value).first()
    if not row:
        row = DailyAnalytics(day=day_value)
        db.session.add(row)
        db.session.flush()
    return row


def get_or_create_visitor_session():
    session_key = get_or_create_session_key()

    visitor = VisitorSession.query.filter_by(session_key=session_key).first()
    is_new = False

    if not visitor:
        visitor = VisitorSession(
            session_key=session_key,
            user_id=session.get('user_id'),
            ip_address=get_client_ip(),
            user_agent=request.headers.get('User-Agent', '')[:1000],
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            total_hits=0
        )
        db.session.add(visitor)
        db.session.flush()
        is_new = True
    else:
        visitor.last_seen = datetime.utcnow()
        if session.get('user_id') and not visitor.user_id:
            visitor.user_id = session.get('user_id')

    return visitor, is_new


def log_event(event_type, page=None, event_value=0, meta=None, commit=True):
    visitor, _ = get_or_create_visitor_session()

    event = AppEvent(
        visitor_session_id=visitor.id,
        user_id=session.get('user_id'),
        event_type=event_type,
        page=page,
        event_value=event_value,
        meta=json.dumps(meta) if meta else None,
        created_at=datetime.utcnow()
    )
    db.session.add(event)

    daily = get_or_create_daily_row()

    if event_type == 'signup':
        daily.signups += 1
    elif event_type == 'login':
        daily.logins += 1
    elif event_type == 'bet_placed':
        daily.bets_placed += 1
        daily.credits_wagered += int(event_value or 0)
    elif event_type == 'draw_revealed':
        daily.reveals += 1
    elif event_type == 'verify_page_visit':
        daily.verify_page_visits += 1
    elif event_type == 'payout':
        daily.credits_paid_out += int(event_value or 0)

    if commit:
        db.session.commit()

    return event


def track_page_visit():
    if request.method != 'GET':
        return

    path = request.path or '/'

    if path.startswith('/static'):
        return

    visitor, is_new = get_or_create_visitor_session()
    visitor.total_hits += 1
    visitor.last_seen = datetime.utcnow()

    daily = get_or_create_daily_row()
    daily.visitors += 1

    if is_new:
        daily.unique_visitors += 1

    event = AppEvent(
        visitor_session_id=visitor.id,
        user_id=session.get('user_id'),
        event_type='page_view',
        page=path,
        event_value=1,
        meta=None,
        created_at=datetime.utcnow()
    )
    db.session.add(event)
    db.session.commit()


def attach_analytics(app):
    @app.before_request
    def before_request_tracking():
        track_page_visit()


def get_kpis():
    total_visitors = db.session.query(func.count(VisitorSession.id)).scalar() or 0
    unique_signups = db.session.query(func.count(User.id)).scalar() or 0
    total_bets = db.session.query(func.count(Bet.id)).scalar() or 0
    credits_wagered = db.session.query(func.sum(Bet.amount)).scalar() or 0
    credits_paid_out = db.session.query(func.sum(Bet.won)).scalar() or 0
    net_platform = credits_wagered - credits_paid_out

    total_page_views = (
        db.session.query(func.count(AppEvent.id))
        .filter(AppEvent.event_type == 'page_view')
        .scalar() or 0
    )

    total_reveals = (
        db.session.query(func.count(AppEvent.id))
        .filter(AppEvent.event_type == 'draw_revealed')
        .scalar() or 0
    )

    return {
        'total_visitors': total_visitors,
        'unique_signups': unique_signups,
        'total_bets': total_bets,
        'credits_wagered': credits_wagered,
        'credits_paid_out': credits_paid_out,
        'net_platform': net_platform,
        'total_page_views': total_page_views,
        'total_reveals': total_reveals
    }


def get_daily_chart_data(days=7):
    labels = []
    visits = []
    bets = []
    credits_in = []
    credits_out = []

    start_day = date.today() - timedelta(days=days - 1)

    for i in range(days):
        current_day = start_day + timedelta(days=i)
        row = DailyAnalytics.query.filter_by(day=current_day).first()

        labels.append(current_day.strftime('%d %b'))
        visits.append(row.visitors if row else 0)
        bets.append(row.bets_placed if row else 0)
        credits_in.append(row.credits_wagered if row else 0)
        credits_out.append(row.credits_paid_out if row else 0)

    return {
        'labels': labels,
        'visits': visits,
        'bets': bets,
        'credits_in': credits_in,
        'credits_out': credits_out
    }


def get_top_pages(limit=10):
    rows = (
        db.session.query(
            AppEvent.page,
            func.count(AppEvent.id).label('hits')
        )
        .filter(AppEvent.event_type == 'page_view')
        .group_by(AppEvent.page)
        .order_by(func.count(AppEvent.id).desc())
        .limit(limit)
        .all()
    )

    return [{'page': r.page, 'hits': r.hits} for r in rows]


def get_top_players(limit=10):
    rows = (
        db.session.query(
            User.roll_no,
            User.email,
            User.credits,
            func.coalesce(func.sum(Bet.amount), 0).label('total_bet'),
            func.coalesce(func.sum(Bet.won), 0).label('total_won'),
            func.count(Bet.id).label('bets_count')
        )
        .outerjoin(Bet, Bet.user_id == User.id)
        .group_by(User.id)
        .order_by(func.coalesce(func.sum(Bet.won), 0).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            'roll_no': r.roll_no,
            'email': r.email,
            'credits': r.credits,
            'total_bet': int(r.total_bet or 0),
            'total_won': int(r.total_won or 0),
            'bets_count': int(r.bets_count or 0)
        }
        for r in rows
    ]


def register_admin_routes(app):
    @app.route('/admin')
    def admin_dashboard():
        kpis = get_kpis()
        chart_data = get_daily_chart_data(7)
        top_pages = get_top_pages(10)
        top_players = get_top_players(10)

        return render_template(
            'admin_dashboard.html',
            kpis=kpis,
            chart_data=chart_data,
            top_pages=top_pages,
            top_players=top_players
        )