from flask import render_template, request, redirect, url_for, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from models import db, User


def get_reset_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generate_reset_token(email):
    serializer = get_reset_serializer()
    return serializer.dumps(email, salt='password-reset-salt')


def verify_reset_token(token, max_age=3600):
    serializer = get_reset_serializer()
    try:
        email = serializer.loads(
            token,
            salt='password-reset-salt',
            max_age=max_age
        )
        return email
    except (SignatureExpired, BadSignature):
        return None


def register_password_reset_routes(app):
    @app.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        reset_link = None
        message = None
        error = None

        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()

            if not email:
                error = 'Please enter your registered email.'
                return render_template(
                    'forgot_password.html',
                    error=error,
                    message=message,
                    reset_link=reset_link
                )

            user = User.query.filter_by(email=email).first()

            if not user:
                error = 'No account found with this email.'
                return render_template(
                    'forgot_password.html',
                    error=error,
                    message=message,
                    reset_link=reset_link
                )

            token = generate_reset_token(user.email)
            reset_link = url_for('reset_password', token=token, _external=True)
            message = 'Reset link generated successfully. Use the link below for now.'

        return render_template(
            'forgot_password.html',
            error=error,
            message=message,
            reset_link=reset_link
        )

    @app.route('/reset-password/<token>', methods=['GET', 'POST'])
    def reset_password(token):
        email = verify_reset_token(token)

        if not email:
            return render_template(
                'reset_password.html',
                error='This reset link is invalid or has expired.',
                success=None,
                token_valid=False
            )

        user = User.query.filter_by(email=email).first()
        if not user:
            return render_template(
                'reset_password.html',
                error='User not found.',
                success=None,
                token_valid=False
            )

        if request.method == 'POST':
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()

            if not password or not confirm_password:
                return render_template(
                    'reset_password.html',
                    error='Please fill both password fields.',
                    success=None,
                    token_valid=True
                )

            if password != confirm_password:
                return render_template(
                    'reset_password.html',
                    error='Passwords do not match.',
                    success=None,
                    token_valid=True
                )

            if len(password) < 6:
                return render_template(
                    'reset_password.html',
                    error='Password must be at least 6 characters long.',
                    success=None,
                    token_valid=True
                )

            user.set_password(password)
            db.session.commit()

            return render_template(
                'reset_password.html',
                error=None,
                success='Password reset successful. You can now log in.',
                token_valid=False
            )

        return render_template(
            'reset_password.html',
            error=None,
            success=None,
            token_valid=True
        )