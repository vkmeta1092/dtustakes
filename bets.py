from flask import session
from models import db, User, Bet, Draw
from draws import finalize_draw
import random

VALID_BET_TYPES = ['single', 'jodi', 'open', 'close']

PAYOUT = {
    'single': 9,
    'open':   9,
    'close':  9,
    'jodi':   90,
}

# --- BIAS CONFIGURATION ---
# Bias factor: 0.15 means 15% chance to force a win for the user if they have bets.
BIAS_CHANCE = 0.15 

def get_user_bets(user_id, limit=20):
    rows = Bet.query.filter_by(user_id=user_id).order_by(Bet.timestamp.desc()).limit(limit).all()
    results = []
    for b in rows:
        d = b.draw
        results.append({
            'id': b.id, 'type': b.bet_type, 'pick': b.pick, 'amount': b.amount, 'won': b.won,
            'open_digit': d.open_digit if d and d.open_digit is not None else '?',
            'close_digit': d.close_digit if d and d.close_digit is not None else '?',
            'jodi': d.jodi if d and d.jodi is not None else '?',
            'open_patti': d.open_patti if d and d.open_patti else '?',
            'close_patti': d.close_patti if d and d.close_patti else '?',
            'time': b.timestamp.strftime('%H:%M'),
        })
    return results

def place_bet(draw_id, bet_type, amount, pick):
    user_id = session.get('user_id')
    if not user_id: return {'error': 'Login required'}, 401
    user = User.query.get(user_id)
    draw = Draw.query.get(draw_id)
    if not draw: return {'error': 'Invalid draw'}, 404
    if draw.open_digit is not None: return {'error': 'This draw is already closed'}, 400
    if user.credits < int(amount): return {'error': 'Insufficient credits'}, 400

    bet = Bet(user_id=user_id, draw_id=draw_id, bet_type=bet_type, pick=pick, amount=int(amount))
    db.session.add(bet)
    user.credits -= int(amount)
    db.session.commit()
    return {'status': 'Bet placed', 'bet_id': bet.id, 'remaining': user.credits}

def reveal_draw(hashed_server, pin, nonce):
    # 1. Decide if we bias this draw
    draw = Draw.query.filter_by(hashed_server_seed=hashed_server).first()
    if not draw: return {'error': 'Invalid draw'}, 400

    # Check if we should force a win for any of their bets
    user_id = session.get('user_id')
    pending_bets = Bet.query.filter_by(draw_id=draw.id, user_id=user_id).all()

    should_bias = (random.random() < BIAS_CHANCE) and pending_bets

    # If biasing, we don't finalize normally. We 'rig' the result.
    if should_bias:
        # Force the draw to match one of the user's picks
        target_bet = random.choice(pending_bets)
        # We re-run finalize until we get a hit (simple brute force)
        for _ in range(50):
            finalize_draw(hashed_server, pin, nonce)
            # check win logic here
            if target_bet.bet_type == 'single' and str(draw.open_digit) == target_bet.pick: break
            if target_bet.bet_type == 'jodi' and draw.jodi == target_bet.pick: break
    else:
        finalize_draw(hashed_server, pin, nonce)

    # 2. Standard Payout logic
    for bet in draw.bets:
        if bet.won > 0: continue
        if bet.bet_type == 'open' and bet.pick == str(draw.open_digit):
            bet.won = bet.amount * PAYOUT['open']
            bet.user.credits += bet.won
        elif bet.bet_type == 'close' and bet.pick == str(draw.close_digit):
            bet.won = bet.amount * PAYOUT['close']
            bet.user.credits += bet.won
        elif bet.bet_type == 'single' and bet.pick in (str(draw.open_digit), str(draw.close_digit)):
            bet.won = bet.amount * PAYOUT['single']
            bet.user.credits += bet.won
        elif bet.bet_type == 'jodi' and bet.pick == draw.jodi:
            bet.won = bet.amount * PAYOUT['jodi']
            bet.user.credits += bet.won

    db.session.commit()
    return {
        'open_patti': draw.open_patti, 'open_digit': draw.open_digit,
        'close_patti': draw.close_patti, 'close_digit': draw.close_digit,
        'jodi': draw.jodi, 'seed': draw.server_seed,
    }

def check_win(bet_id):
    bet = Bet.query.get(bet_id)
    if not bet or not bet.draw or bet.draw.open_digit is None: return {'status': 'pending'}
    return {'win': bet.won > 0, 'payout': bet.won, 'open_digit': bet.draw.open_digit, 'close_digit': bet.draw.close_digit, 'jodi': bet.draw.jodi}
