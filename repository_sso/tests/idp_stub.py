"""Local OIDC integration fixture. Synthetic identities only; never use in deployment."""

import base64
import hashlib
import json
import time
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import rsa

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISSUER = "http://127.0.0.1:18990/realms/repository"
SESSIONS = set()
CODES = {}
REFRESH = {}
BACKCHANNELS = {
    "repository": "http://127.0.0.1:18991/sso/backchannel-logout/",
    "upload": "http://127.0.0.1:18992/sso/backchannel-logout/",
}


def tokens(client, sid):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": client,
        "sub": "synthetic-existing-user",
        "sid": sid,
        "iat": now,
        "exp": now + 300,
        "preferred_username": "synthetic-user",
        "email": "synthetic@example.test",
        "email_verified": True,
    }
    raw = jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "fixture"})
    refresh = uuid.uuid4().hex
    REFRESH[refresh] = (client, sid)
    return {
        "access_token": raw,
        "id_token": raw,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": 300,
    }


def backchannel(sid):
    for client, target in BACKCHANNELS.items():
        raw = jwt.encode(
            {
                "iss": ISSUER,
                "aud": client,
                "iat": int(time.time()),
                "jti": uuid.uuid4().hex,
                "sid": sid,
                "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
            },
            KEY,
            algorithm="RS256",
            headers={"kid": "fixture"},
        )
        response = requests.post(target, data={"logout_token": raw}, timeout=5)
        if response.status_code != 200:
            raise RuntimeError("Backchannel fixture rejected")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never record tokens, codes, or complete authentication URLs.

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def redirect(self, url, cookie=None):
        self.send_response(302)
        self.send_header("Location", url)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        args = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        endpoint = ISSUER + "/protocol/openid-connect/"
        if path.endswith("/.well-known/openid-configuration"):
            return self.send_json(
                {
                    "issuer": ISSUER,
                    "authorization_endpoint": endpoint + "auth",
                    "token_endpoint": endpoint + "token",
                    "userinfo_endpoint": endpoint + "userinfo",
                    "jwks_uri": endpoint + "certs",
                    "end_session_endpoint": endpoint + "logout",
                    "token_endpoint_auth_methods_supported": ["client_secret_post"],
                }
            )
        if path.endswith("/certs"):
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
            return self.send_json({"keys": [{**jwk, "kid": "fixture", "use": "sig", "alg": "RS256"}]})
        if path.endswith("/userinfo"):
            raw = self.headers["Authorization"].removeprefix("Bearer ")
            claims = jwt.decode(
                raw,
                KEY.public_key(),
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            return self.send_json(claims)
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        sid = cookies["fixture_sso"].value if "fixture_sso" in cookies else None
        if path.endswith("/auth"):
            if args.get("prompt") == "none" and sid not in SESSIONS:
                return self.redirect(
                    args["redirect_uri"] + "?" + urlencode({"error": "login_required", "state": args["state"]})
                )
            if sid not in SESSIONS:
                sid = uuid.uuid4().hex
                SESSIONS.add(sid)
            code = uuid.uuid4().hex
            CODES[code] = (
                args["client_id"],
                sid,
                args["redirect_uri"],
                args.get("code_challenge"),
            )
            return self.redirect(
                args["redirect_uri"] + "?" + urlencode({"code": code, "state": args["state"]}),
                "fixture_sso=" + sid + "; Path=/; HttpOnly; SameSite=Lax",
            )
        if path.endswith("/logout"):
            hint = args.get("id_token_hint")
            if hint:
                sid = jwt.decode(
                    hint,
                    KEY.public_key(),
                    algorithms=["RS256"],
                    options={"verify_aud": False},
                )["sid"]
            SESSIONS.discard(sid)
            backchannel(sid)
            return self.redirect(args["post_logout_redirect_uri"], "fixture_sso=; Max-Age=0; Path=/")
        self.send_json({"error": "not_found"}, 404)

    def do_POST(self):
        args = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
        if urlparse(self.path).path == "/fixture/revoke/":
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            sid = cookies["fixture_sso"].value if "fixture_sso" in cookies else None
            SESSIONS.discard(sid)
            backchannel(sid)
            return self.send_json({"revoked": True})
        if args.get("grant_type") == "refresh_token":
            client, sid = REFRESH.get(args.get("refresh_token"), (None, None))
            if client != args.get("client_id") or sid not in SESSIONS:
                return self.send_json({"error": "invalid_grant"}, 400)
            return self.send_json(tokens(client, sid))
        client, sid, callback, challenge = CODES.pop(args.get("code"), (None, None, None, None))
        actual = (
            base64.urlsafe_b64encode(hashlib.sha256(args.get("code_verifier", "").encode()).digest())
            .decode()
            .rstrip("=")
        )
        if not client or callback != args.get("redirect_uri") or (challenge and challenge != actual):
            return self.send_json({"error": "invalid_grant"}, 400)
        self.send_json(tokens(client, sid))


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18990), Handler).serve_forever()
