import hashlib
import hmac
import secrets
from models import db, Draw


def generate_draw():
    server_seed = secrets.token_hex(32)
    hashed = hashlib.sha256(server_seed.encode()).hexdigest()
    nonce = secrets.randbelow(10000)
    return server_seed, hashed, nonce


def compute_digit(server_seed, pin, nonce):
    message = f"{pin}:{nonce}".encode()
    digest = hmac.new(server_seed.encode(), message, hashlib.sha256).hexdigest()
    return int(digest[:8], 16) % 10


def finalize_draw(hashed_server, pin, nonce):
    draw = Draw.query.filter_by(hashed_server_seed=hashed_server).first()

    if not draw:
        return None

    if draw.open_digit is not None and draw.jodi is not None:
        return draw

    digit1 = compute_digit(draw.server_seed, pin, nonce)
    digit2 = compute_digit(draw.server_seed, str(int(pin) + 1), nonce)

    draw.open_digit = digit1
    draw.jodi = f"{digit1}-{digit2}"
    draw.nonce = nonce

    db.session.commit()
    return draw