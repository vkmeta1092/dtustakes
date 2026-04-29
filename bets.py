from flask import session
from models import db, User, Bet, Draw
from draws import finalize_draw


def get_user_bets(user_id, limit=10):
    bets = (
        Bet.query
        .filter_by(user_id=user_id)
        .order_by(Bet.timestamp.desc())
        .limit(limit)
        .all()
    )

    results = []
    for b in bets:
        results.append({
            'id': b.id,
            'type': b.bet_type,
            'pick': b.pick,
            'amount': b.amount,
            'won': b.won,
            'result': b.draw.open_digit if b.draw and b.draw.open_digit is not None else '?',
            'jodi': b.draw.jodi if b.draw and b.draw.jodi is not None else '?',
            'time': b.timestamp.strftime('%H:%M')
        })
    return results


def save_bet(user_id, draw_id, bet_type, pick, amount):
    bet = Bet(
        user_id=user_id,
        draw_id=draw_id,
        bet_type=bet_type,
        pick=pick,
        amount=amount
    )
    db.session.add(bet)
    db.session.flush()
    return bet.id


def place_bet(draw_id, bet_type, amount, pick):
    user_id = session.get('user_id')
    if not user_id:
        return {'error': 'Login required'}, 401

    user = User.query.get(user_id)
    if not user:
        return {'error': 'User not found'}, 404

    draw = Draw.query.get(draw_id)
    if not draw:
        return {'error': 'Invalid draw'}, 404

    if draw.open_digit is not None:
        return {'error': 'This draw is already closed'}, 400

    if amount <= 0:
        return {'error': 'Amount must be greater than 0'}, 400

    bet_type = str(bet_type).strip().lower()
    pick = str(pick).strip()

    if bet_type not in ['single', 'jodi']:
        return {'error': 'Invalid bet type'}, 400

    if bet_type == 'single':
        if not pick.isdigit() or not (0 <= int(pick) <= 9):
            return {'error': 'Single pick must be a digit from 0 to 9'}, 400

    if bet_type == 'jodi':
        parts = pick.split('-')
        if len(parts) != 2 or not all(p.isdigit() and 0 <= int(p) <= 9 for p in parts):
            return {'error': 'Jodi pick must be in format x-y, example 5-7'}, 400

    if user.credits < amount:
        return {'error': 'Low credits'}, 400

    bet_id = save_bet(user_id, draw_id, bet_type, pick, amount)
    user.credits -= amount
    db.session.commit()

    return {
        'status': 'Bet placed',
        'bet_id': bet_id,
        'remaining': user.credits
    }


def reveal_draw(hashed_server, pin, nonce):
    draw = finalize_draw(hashed_server, pin, nonce)

    if not draw:
        return {'error': 'Invalid draw'}, 400

    for bet in draw.bets:
        if bet.won > 0:
            continue

        if bet.bet_type == 'single' and bet.pick == str(draw.open_digit):
            payout = bet.amount * 9
            bet.won = payout
            bet.user.credits += payout

        elif bet.bet_type == 'jodi' and bet.pick == draw.jodi:
            payout = bet.amount * 90
            bet.won = payout
            bet.user.credits += payout

    db.session.commit()

    return {
        'open': draw.open_digit,
        'jodi': draw.jodi,
        'seed': draw.server_seed
    }


def check_win(bet_id):
    bet = Bet.query.get(bet_id)

    if not bet:
        return {'error': 'Bet not found'}

    if not bet.draw or bet.draw.open_digit is None:
        return {'status': 'Pending'}

    return {
        'win': bet.won > 0,
        'payout': bet.won,
        'result': bet.draw.open_digit,
        'jodi': bet.draw.jodi
    }