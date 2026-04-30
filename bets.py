from flask import session
from models import db, User, Bet, Draw
from draws import finalize_draw

VALID_BET_TYPES = ['single', 'jodi', 'open', 'close']

PAYOUT = {
    'single': 9,    # matches open OR close digit
    'open':   9,    # matches open digit only
    'close':  9,    # matches close digit only
    'jodi':   90,   # exact 2-digit jodi match
}


def get_user_bets(user_id, limit=20):
    rows = (
        Bet.query
        .filter_by(user_id=user_id)
        .order_by(Bet.timestamp.desc())
        .limit(limit)
        .all()
    )
    results = []
    for b in rows:
        d = b.draw
        results.append({
            'id':          b.id,
            'type':        b.bet_type,
            'pick':        b.pick,
            'amount':      b.amount,
            'won':         b.won,
            'open_digit':  d.open_digit  if d and d.open_digit  is not None else '?',
            'close_digit': d.close_digit if d and d.close_digit is not None else '?',
            'jodi':        d.jodi        if d and d.jodi        is not None else '?',
            'open_patti':  d.open_patti  if d and d.open_patti  else '?',
            'close_patti': d.close_patti if d and d.close_patti else '?',
            'time':        b.timestamp.strftime('%H:%M'),
        })
    return results


def _validate_pick(bet_type, pick):
    if bet_type in ('single', 'open', 'close'):
        if not pick.isdigit() or not (0 <= int(pick) <= 9):
            return False, 'Pick must be a single digit 0–9'
    elif bet_type == 'jodi':
        if not pick.isdigit() or len(pick) != 2:
            return False, 'Jodi pick must be exactly 2 digits e.g. 37'
    return True, None


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

    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return {'error': 'Amount must be a number'}, 400

    if amount <= 0:
        return {'error': 'Amount must be greater than 0'}, 400

    if user.credits < amount:
        return {'error': 'Insufficient credits'}, 400

    bet_type = str(bet_type).strip().lower()
    pick     = str(pick).strip()

    if bet_type not in VALID_BET_TYPES:
        return {'error': f'Invalid bet type. Choose from: {", ".join(VALID_BET_TYPES)}'}, 400

    valid, err = _validate_pick(bet_type, pick)
    if not valid:
        return {'error': err}, 400

    bet = Bet(user_id=user_id, draw_id=draw_id,
              bet_type=bet_type, pick=pick, amount=amount)
    db.session.add(bet)
    db.session.flush()

    user.credits -= amount
    db.session.commit()

    return {'status': 'Bet placed', 'bet_id': bet.id, 'remaining': user.credits}


def reveal_draw(hashed_server, pin, nonce):
    draw = finalize_draw(hashed_server, pin, nonce)
    if not draw:
        return {'error': 'Invalid draw or hash mismatch'}, 400

    for bet in draw.bets:
        if bet.won > 0:
            continue

        if bet.bet_type == 'open' and bet.pick == str(draw.open_digit):
            bet.won = bet.amount * PAYOUT['open']
            bet.user.credits += bet.won

        elif bet.bet_type == 'close' and bet.pick == str(draw.close_digit):
            bet.won = bet.amount * PAYOUT['close']
            bet.user.credits += bet.won

        elif bet.bet_type == 'single' and bet.pick in (
                str(draw.open_digit), str(draw.close_digit)):
            bet.won = bet.amount * PAYOUT['single']
            bet.user.credits += bet.won

        elif bet.bet_type == 'jodi' and bet.pick == draw.jodi:
            bet.won = bet.amount * PAYOUT['jodi']
            bet.user.credits += bet.won

    db.session.commit()

    return {
        'open_patti':  draw.open_patti,
        'open_digit':  draw.open_digit,
        'close_patti': draw.close_patti,
        'close_digit': draw.close_digit,
        'jodi':        draw.jodi,
        'seed':        draw.server_seed,
    }


def check_win(bet_id):
    bet = Bet.query.get(bet_id)
    if not bet:
        return {'error': 'Bet not found'}
    if not bet.draw or bet.draw.open_digit is None:
        return {'status': 'pending'}
    return {
        'win':         bet.won > 0,
        'payout':      bet.won,
        'open_digit':  bet.draw.open_digit,
        'close_digit': bet.draw.close_digit,
        'jodi':        bet.draw.jodi,
    }
