import os

from flask import Flask, render_template, request, redirect, url_for, session, jsonify

from models import db, User, Draw
from draws import generate_draw
from bets import place_bet, reveal_draw, get_user_bets, check_win
from analytics import attach_analytics, register_admin_routes, log_event
from analytics_models import VisitorSession, AppEvent, DailyAnalytics
from password_reset import register_password_reset_routes

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dtu-stakes-secret-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'sqlite:///dtustakes.db'
).replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

attach_analytics(app)
register_admin_routes(app)
register_password_reset_routes(app)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/signup', methods=['POST'])
def signup():
    roll = request.form.get('roll_no', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()

    if not roll or not email or not password:
        return render_template('index.html', error='All signup fields are required.'), 400

    existing_user = User.query.filter(
        (User.roll_no == roll) | (User.email == email)
    ).first()

    if existing_user:
        return render_template('index.html', error='Roll number or email already exists.'), 400

    user = User(roll_no=roll, email=email)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id

    log_event(
        event_type='signup',
        page='/signup',
        event_value=1,
        meta={
            'roll_no': user.roll_no,
            'email': user.email
        }
    )

    return redirect(url_for('dashboard'))


@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()

    if not email or not password:
        return render_template('index.html', error='Email and password are required.'), 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return render_template('index.html', error='Invalid email or password.'), 401

    session['user_id'] = user.id

    log_event(
        event_type='login',
        page='/login',
        event_value=1,
        meta={
            'user_id': user.id,
            'email': user.email
        }
    )

    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user = User.query.get(session['user_id'])

    if not user:
        session.pop('user_id', None)
        return redirect(url_for('index'))

    server_seed, hashed, nonce = generate_draw()

    draw = Draw(
        hashed_server_seed=hashed,
        server_seed=server_seed,
        nonce=nonce
    )

    db.session.add(draw)
    db.session.commit()

    bets = get_user_bets(user.id)

    return render_template(
        'dashboard.html',
        user=user,
        hashed=hashed,
        nonce=nonce,
        draw=draw,
        bets=bets
    )


@app.route('/verify')
def verify():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    log_event(
        event_type='verify_page_visit',
        page='/verify',
        event_value=1
    )

    return render_template('verify.html')


@app.route('/api/bet', methods=['POST'])
def api_bet():
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401

    data = request.get_json()

    if not data:
        return jsonify({'error': 'Invalid JSON body'}), 400

    draw_id = data.get('draw_id')
    bet_type = data.get('bet_type')
    amount = data.get('amount')
    pick = str(data.get('pick', '')).strip()

    if not draw_id or not bet_type or amount is None or not pick:
        return jsonify({'error': 'draw_id, bet_type, amount and pick are required'}), 400

    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return jsonify({'error': 'Amount must be a number'}), 400

    result = place_bet(draw_id, bet_type, amount, pick)

    if isinstance(result, tuple):
        payload, status_code = result
        return jsonify(payload), status_code

    log_event(
        event_type='bet_placed',
        page='/api/bet',
        event_value=amount,
        meta={
            'draw_id': draw_id,
            'bet_type': bet_type,
            'pick': pick,
            'user_id': session.get('user_id')
        }
    )

    return jsonify(result)


@app.route('/api/reveal', methods=['POST'])
def api_reveal():
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401

    data = request.get_json()

    if not data:
        return jsonify({'error': 'Invalid JSON body'}), 400

    hashed = data.get('hashed')
    pin = str(data.get('pin', '')).strip()
    nonce = data.get('nonce')

    if not hashed or not pin or nonce is None:
        return jsonify({'error': 'hashed, pin and nonce are required'}), 400

    try:
        nonce = int(nonce)
    except (ValueError, TypeError):
        return jsonify({'error': 'Nonce must be a number'}), 400

    result = reveal_draw(hashed, pin, nonce)

    if isinstance(result, tuple):
        payload, status_code = result
        return jsonify(payload), status_code

    log_event(
        event_type='draw_revealed',
        page='/api/reveal',
        event_value=1,
        meta={
            'hashed_server_seed': hashed,
            'nonce': nonce,
            'user_id': session.get('user_id')
        }
    )

    user_bets = get_user_bets(session['user_id'])
    latest_paid = 0

    for bet in user_bets:
        won_value = int(bet.get('won', 0) or 0)
        if won_value > 0:
            latest_paid += won_value

    if latest_paid > 0:
        log_event(
            event_type='payout',
            page='/api/reveal',
            event_value=latest_paid,
            meta={
                'user_id': session.get('user_id')
            }
        )

    return jsonify(result)


@app.route('/api/history')
def api_history():
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401

    bets = get_user_bets(session['user_id'])
    return jsonify(bets)


@app.route('/api/checkwin/<int:bet_id>')
def api_checkwin(bet_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required'}), 401

    result = check_win(bet_id)
    return jsonify(result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)