import hashlib
import hmac
import secrets
from models import db, Draw


def generate_draw():
    server_seed = secrets.token_hex(32)
    hashed = hashlib.sha256(server_seed.encode()).hexdigest()
    nonce = secrets.randbelow(10000)
    return server_seed, hashed, nonce


def _compute_patti(server_seed, salt, nonce):
    digits = []
    for i in range(3):
        msg = f"{salt}:{nonce}:{i}".encode()
        digest = hmac.new(server_seed.encode(), msg, hashlib.sha256).hexdigest()
        digits.append(int(digest[:8], 16) % 10)
    return digits


def finalize_draw(hashed_server, pin, nonce):
    draw = Draw.query.filter_by(hashed_server_seed=hashed_server).first()
    if not draw:
        return None

    if draw.open_digit is not None and draw.close_digit is not None:
        return draw

    open_digits  = _compute_patti(draw.server_seed, pin, nonce)
    close_digits = _compute_patti(draw.server_seed, str(int(pin) + 1), nonce)

    draw.open_patti  = "-".join(map(str, open_digits))
    draw.close_patti = "-".join(map(str, close_digits))
    draw.open_digit  = sum(open_digits) % 10
    draw.close_digit = sum(close_digits) % 10
    draw.jodi        = f"{draw.open_digit}{draw.close_digit}"
    draw.nonce       = nonce

    db.session.commit()
    return draw
