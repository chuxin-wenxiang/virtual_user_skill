#!/usr/bin/env python3
"""Official SIWC Responses transport: OAuth only, no API-key or paid fallback."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import secrets
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.error
import urllib.parse
import urllib.request

import authentic_user as au

API = "https://api.openai.com/v1"
ISSUER = "https://auth.openai.com"
SCOPES = {"chatgpt.tokens.use.direct", "resource.invoke"}
# Bounded tolerance for ordinary issuer/host clock skew; verification remains enabled.
JWT_CLOCK_LEEWAY_SECONDS = 30


class PlanStop(au.InputError):
    """A terminal quota, eligibility or transport condition; never change billing paths."""

    def __init__(self, message, diagnostic=None):
        super().__init__(message)
        self.diagnostic = diagnostic


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def atomic_private(path, obj):
    path = Path(path)
    if path.is_symlink():
        raise PlanStop("Symlink credential target rejected")
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(obj, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_identity(id_token, client_id, nonce, jwks_uri):
    try:
        import jwt
        parsed = urllib.parse.urlsplit(jwks_uri)
        if parsed.scheme != "https" or parsed.hostname != "auth.openai.com":
            raise PlanStop("Unexpected identity signing-key endpoint")
        signing = jwt.PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token)
        identity = jwt.decode(id_token, signing.key, algorithms=["RS256"], audience=client_id, issuer=ISSUER, leeway=JWT_CLOCK_LEEWAY_SECONDS,
                              options={"require": ["exp", "iss", "aud", "sub", "nonce"]})
        actual_nonce = identity.get("nonce")
        if not isinstance(actual_nonce, str) or not hmac.compare_digest(actual_nonce, nonce):
            raise PlanStop("Identity nonce mismatch")
        return identity
    except PlanStop:
        raise
    except ImportError:
        raise PlanStop("Install the optional PyJWT[crypto] dependency for authorization") from None
    except Exception as exc:
        raise PlanStop(f"Identity signature/claims rejected ({type(exc).__name__})") from None


def authorize(credential_dir, timeout=900):
    root = Path(credential_dir).expanduser()
    if root.is_symlink():
        raise PlanStop("Symlink credential directory rejected")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    if (root / "credentials.json").exists():
        PlanClient(root)
        return {"status": "existing_plan_credentials_present", "new_login_started": False}
    host_path = root / "host.json"
    if host_path.exists():
        host = au.read_object(host_path)["ext_agent_host_id"]
        uuid.UUID(host.removeprefix("urn:uuid:"))
    else:
        host = "urn:uuid:" + str(uuid.uuid4())
        atomic_private(host_path, {"ext_agent_host_id": host})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(ISSUER + "/.well-known/openid-configuration", timeout=25) as response:
        discovery = json.load(response)
    if discovery.get("issuer") != ISSUER:
        raise PlanStop("Unexpected identity issuer")
    state, nonce, verifier = (secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Callback URLs contain one-time codes and must not enter logs.

        def reply(self, status, message):
            content = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path != "/auth/callback":
                self.reply(404, "Not found")
                return
            query = urllib.parse.parse_qs(parsed.query)
            if not hmac.compare_digest(query.get("state", [""])[0], state):
                self.reply(400, "Authorization state mismatch. Return to your client.")
                return
            if "error" in query:
                result.update(status="authorization_denied", error_code=query["error"][0])
                self.reply(400, "Authorization was not completed. No inference was performed.")
                return
            code, client = query.get("code", [""])[0], query.get("client_id", [""])[0]
            if not code or not client or client == "dynamic_agent_client":
                result["status"] = "registration_incomplete"
                self.reply(400, "Registration did not return an issued client ID.")
                return
            try:
                form = {"grant_type": "authorization_code", "client_id": client, "code": code,
                        "code_verifier": verifier, "redirect_uri": redirect, "resource": API}
                request = urllib.request.Request(ISSUER + "/api/accounts/oauth/token",
                                                 data=urllib.parse.urlencode(form).encode(),
                                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
                with opener.open(request, timeout=30) as response:
                    tokens = json.load(response)
                identity = verify_identity(tokens["id_token"], client, nonce, discovery["jwks_uri"])
                scopes = set(tokens.get("scope", "").split())
                if not SCOPES.issubset(scopes):
                    result["status"] = "plan_usage_not_authorized"
                    self.reply(400, "Identity sign-in succeeded but plan usage was not authorized. No inference was performed.")
                    return
                if tokens.get("token_type", "").lower() != "bearer":
                    raise PlanStop("Unexpected token type")
                profile = {"issuer": ISSUER, "subject": identity["sub"], "client_id": client,
                           "ext_agent_host_id": host, "id_token": tokens["id_token"],
                           "access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token"),
                           "token_type": tokens["token_type"], "expires_in": tokens.get("expires_in"),
                           "scopes": sorted(scopes), "saved_at_unix": int(time.time()),
                           "cost_policy": "existing_subscription_only_no_paid_fallback"}
                atomic_private(root / "credentials.json", profile)
                result.update(status="authorized", id_token_signature_verified=True,
                              plan_usage_scope_granted=True, paid_api_key_created=False, model_calls_performed=0)
                self.reply(200, "ChatGPT plan authorization completed. No API key was created and no payment was made. Return to your client.")
            except Exception as exc:
                result.update(status="authorization_validation_failed", error_type=type(exc).__name__)
                self.reply(400, "Authorization verification failed. No inference was performed.")

    server = HTTPServer(("127.0.0.1", 0), Callback)
    server.timeout = 1
    redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
    query = {"client_id": "dynamic_agent_client", "agent_name_hint": "Authentic User v2027",
             "ext_agent_host_id": host, "response_type": "code", "redirect_uri": redirect,
             "scope": "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct",
             "resource": API, "state": state, "nonce": nonce, "code_challenge_method": "S256", "code_challenge": challenge}
    print(json.dumps({"status": "awaiting_browser_authorization", "expires_in_seconds": timeout}), flush=True)
    webbrowser.open(ISSUER + "/api/accounts/authorize?" + urllib.parse.urlencode(query), new=2)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline and not result:
            server.handle_request()
    finally:
        server.server_close()
    if not result:
        result["status"] = "authorization_timeout"
    atomic_private(root / "authorization-status.json", result)
    return result


def http_error(exc):
    try:
        obj = json.loads(exc.read())
        error = obj.get("error")
        code = error.get("code") if isinstance(error, dict) else None
    except (ValueError, TypeError):
        code = None
    return PlanStop(f"Official plan endpoint stopped: HTTP {exc.code}, code={code or 'unclassified'}")


class PlanClient:
    def __init__(self, credential_dir):
        self.root = Path(credential_dir).expanduser()
        if self.root.is_symlink() or (self.root / "credentials.json").is_symlink():
            raise PlanStop("Symlink credential storage rejected")
        self.path = self.root / "credentials.json"
        self.lock = threading.Lock()
        self.opener = urllib.request.build_opener(NoRedirect())
        self.profile = au.read_object(self.path)
        self._validate_profile()

    def _validate_profile(self):
        profile = self.profile
        if not isinstance(profile.get("scopes"), list) or not all(isinstance(s, str) for s in profile["scopes"]):
            raise PlanStop("Invalid plan scope record")
        if (profile.get("issuer") != ISSUER or not isinstance(profile.get("token_type"), str) or profile["token_type"].lower() != "bearer" or
                not SCOPES.issubset(set(profile.get("scopes", []))) or
                profile.get("cost_policy") != "existing_subscription_only_no_paid_fallback"):
            raise PlanStop("Verified plan authorization and subscription-only policy are required")
        if not all(isinstance(profile.get(k), str) and profile[k] for k in ("client_id", "subject", "access_token")):
            raise PlanStop("Incomplete plan credential record")
        if type(profile.get("saved_at_unix")) is not int or type(profile.get("expires_in")) is not int or profile["expires_in"] <= 0:
            raise PlanStop("Invalid plan session expiry record")

    def access_token(self):
        with self.lock:
            expiry = self.profile.get("saved_at_unix", 0) + self.profile.get("expires_in", 0)
            if expiry > time.time() + 90:
                return self.profile["access_token"]
            refresh = self.profile.get("refresh_token")
            if not refresh:
                raise PlanStop("Plan session expired; sign in again")
            form = {"grant_type": "refresh_token", "client_id": self.profile["client_id"],
                    "refresh_token": refresh, "resource": API}
            request = urllib.request.Request(ISSUER + "/api/accounts/oauth/token",
                                             data=urllib.parse.urlencode(form).encode(),
                                             headers={"Content-Type": "application/x-www-form-urlencoded"})
            try:
                with self.opener.open(request, timeout=30) as response:
                    tokens = json.load(response)
            except urllib.error.HTTPError as exc:
                raise http_error(exc) from None
            scopes = set(tokens.get("scope", " ".join(self.profile["scopes"])).split())
            if not SCOPES.issubset(scopes):
                raise PlanStop("Refreshed session lost plan-use permission")
            if not all(isinstance(tokens.get(k), str) and tokens[k] for k in ("access_token", "refresh_token")):
                raise PlanStop("Refresh did not return a complete rotating credential set")
            updated = dict(self.profile)
            if tokens.get("id_token"):
                try:
                    import jwt
                    discovery = self._public_json(ISSUER + "/.well-known/openid-configuration")
                    jwks = discovery["jwks_uri"]
                    if urllib.parse.urlsplit(jwks).scheme != "https" or urllib.parse.urlsplit(jwks).hostname != "auth.openai.com":
                        raise PlanStop("Unexpected ID-token key host")
                    signing = jwt.PyJWKClient(jwks).get_signing_key_from_jwt(tokens["id_token"])
                    identity = jwt.decode(tokens["id_token"], signing.key, algorithms=["RS256"],
                                          audience=self.profile["client_id"], issuer=ISSUER, leeway=JWT_CLOCK_LEEWAY_SECONDS,
                                          options={"require": ["exp", "iss", "aud", "sub"]})
                    if identity["sub"] != self.profile["subject"]:
                        raise PlanStop("Refreshed account identity changed")
                    updated["id_token"] = tokens["id_token"]
                except PlanStop:
                    raise
                except Exception as exc:
                    raise PlanStop(f"Refreshed identity validation failed ({type(exc).__name__})") from None
            for name in ("access_token", "refresh_token", "expires_in", "token_type"):
                if name in tokens:
                    updated[name] = tokens[name]
            updated.update(scopes=sorted(scopes), saved_at_unix=int(time.time()))
            self.profile = updated
            self._validate_profile()
            atomic_private(self.path, updated)
            return updated["access_token"]

    def _public_json(self, url):
        with self.opener.open(url, timeout=25) as response:
            return json.load(response)

    def models(self):
        request = urllib.request.Request(API + "/models", headers={"Authorization": "Bearer " + self.access_token()})
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise http_error(exc) from None

    def respond(self, model, prompt, instructions, *, schema=None, max_input_chars=40000,
                max_output_chars=16000, timeout=90):
        if not isinstance(prompt, str) or len(prompt) > max_input_chars:
            raise PlanStop("Input exceeds the frozen character guard")
        body = {"model": model, "instructions": instructions,
                "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
                "reasoning": {"effort": "low"}, "store": False, "stream": True}
        if schema:
            body["text"] = {"format": {"type": "json_schema", "name": "authentic_user_trial", "strict": True, "schema": schema}}
        encoded = json.dumps(body, ensure_ascii=False).encode()
        request = urllib.request.Request(API + "/responses", data=encoded,
                                         headers={"Authorization": "Bearer " + self.access_token(),
                                                  "Content-Type": "application/json", "Accept": "text/event-stream"})
        events, output, count, terminal = [], [], 0, None
        start = time.monotonic()
        try:
            with self.opener.open(request, timeout=timeout) as response:
                request_id = response.headers.get("x-request-id")
                for raw in response:
                    if time.monotonic() - start > timeout:
                        raise PlanStop("Plan response exceeded local time guard")
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    events.append(event)
                    if event.get("type") == "response.output_text.delta":
                        text = event.get("delta", "")
                        count += len(text)
                        if count > max_output_chars:
                            raise PlanStop("Output exceeded local stream guard; no automatic retry")
                        output.append(text)
                    if event.get("type") in ("response.completed", "response.failed", "response.incomplete"):
                        terminal = event.get("response", {})
                        break
        except urllib.error.HTTPError as exc:
            raise http_error(exc) from None
        if not terminal or terminal.get("status") != "completed":
            code = (terminal or {}).get("error") or {}
            raise PlanStop("Plan stream stopped: " + str(code.get("code", "missing_completed_event")),
                           {"events": events, "response": terminal, "request_id": request_id})
        if terminal.get("model") != model:
            raise PlanStop("Serving model changed from the frozen model alias")
        return {"text": "".join(output), "response": terminal, "request_id": request_id,
                "events": events, "request_body_sha256": hashlib.sha256(encoded).hexdigest(),
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "paid_fallback_used": False}


def answer_schema():
    return {"type": "object", "additionalProperties": False,
            "properties": {
                "answer": {"type": "string"},
                "direction": {"type": "string", "enum": ["promoter", "passive", "detractor", "unknown"]},
                "claims": {"type": "array", "maxItems": 6, "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"text": {"type": "string"}, "kind": {"type": "string", "enum": ["fact", "inference"]},
                                   "evidence_ids": {"type": "array", "items": {"type": "string"}},
                                   "confidence": {"type": "string", "enum": ["low", "medium", "high"]}},
                    "required": ["text", "kind", "evidence_ids", "confidence"]}},
                "unknowns": {"type": "array", "items": {"type": "string"}}},
            "required": ["answer", "direction", "claims", "unknowns"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("authorize", "models", "probe"))
    parser.add_argument("--credential-dir", required=True)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        if args.command == "authorize":
            result = authorize(args.credential_dir)
            if args.output:
                au.write_new(args.output, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(result))
            return 0 if result["status"] in ("authorized", "existing_plan_credentials_present") else 2
        if not args.output:
            raise PlanStop("--output is required for model catalog and probe results")
        client = PlanClient(args.credential_dir)
        if args.command == "models":
            result = {"models": [{k: row.get(k) for k in ("slug", "display_name", "visibility")}
                                  for row in client.models().get("models", [])]}
        else:
            result = client.respond(args.model, "只根据空资料回答：是否有过投诉获赔？资料不足请说明。", "输出 JSON。不得编造事实。",
                                    schema=answer_schema())
        au.write_new(args.output, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"ok": True, "command": args.command, "model": args.model,
                          "paid_fallback_used": False, "output_saved": True}))
        return 0
    except (au.InputError, OSError, ValueError) as exc:
        message = str(exc) if isinstance(exc, au.InputError) else type(exc).__name__
        print(json.dumps({"ok": False, "error": message, "paid_fallback_used": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
