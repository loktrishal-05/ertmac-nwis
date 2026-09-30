"""Real SMTP/OTP lifecycle in the isolated development Mailpit stack; no external mail."""
import json
from pathlib import Path
import re
from time import monotonic, sleep
from uuid import uuid4
import httpx
from app.core.config import settings


def main():
    assert settings.deployment_mode == 'development' and settings.smtp_host == 'localhost'
    assert settings.smtp_port == 1025 and settings.smtp_tls == 'none', 'Disposable Mailpit only'
    email = 'release-' + uuid4().hex + '@example.com'
    password, replacement = uuid4().hex + '!A', uuid4().hex + '!B'
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=30) as client:
        def post(path, body, status=200):
            response = client.post('/auth/'+path, json=body)
            assert response.status_code == status, (path, response.status_code)
            return response.json()

        def delivered_code(purpose):
            deadline = monotonic() + 15
            while monotonic() < deadline:
                messages = httpx.get('http://127.0.0.1:8025/api/v1/messages', trust_env=False).json()['messages']
                message = next((m for m in messages if purpose in m['Subject'] and any(to['Address'] == email for to in m['To'])), None)
                if message:
                    detail = httpx.get('http://127.0.0.1:8025/api/v1/message/'+message['ID'], trust_env=False).json()
                    return re.search(r'code is ([0-9]{6})', detail['Text'])[1]
                sleep(0.2)
            raise AssertionError('Local SMTP delivery did not arrive within 15 seconds')

        post('signup', dict(display_name='Release Tester', email=email, password=password), 202)
        post('email/request-verification', {'email': email}, 202)
        code = delivered_code('email verification')
        post('email/verify', {'email': email, 'code': 'bad'}, 422)
        post('email/verify', {'email': email, 'code': code})
        post('email/verify', {'email': email, 'code': code}, 400)
        post('login', {'username': email, 'password': password})
        old_cookie = client.cookies.get(settings.session_cookie_name)
        known = post('password/forgot', {'email': email}, 202)
        unknown = post('password/forgot', {'email': uuid4().hex+'@example.com'}, 202)
        assert known == unknown
        code = delivered_code('password recovery')
        grant = post('password/verify-otp', {'email': email, 'code': code})
        post('password/verify-otp', {'email': email, 'code': code}, 400)
        reset = {'reset_token': grant['reset_token'], 'new_password': replacement}
        post('password/reset', reset)
        post('password/reset', reset, 400)
        client.cookies.set(settings.session_cookie_name, old_cookie)
        assert client.get('/auth/me').status_code == 401
        post('login', {'username': email, 'password': password}, 401)
        post('login', {'username': email, 'password': replacement})
        post('logout', {})
        assert client.get('/auth/me').status_code == 401
    result = dict(real_smtp='disposable Mailpit', email_verification=True, malformed_rejected=True,
                  otp_replay_rejected=True, generic_recovery=True, reset_replay_rejected=True,
                  old_sessions_revoked=True, new_password_login=True, logout=True)
    Path('data/final_auth.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
