"""Offline plan-route checks; no OAuth or inference network requests."""

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import chatgpt_plan as cp
import validation_workflow as vw


class Stream:
    def __init__(self, events):
        self.events = events
        self.headers = {"x-request-id": "synthetic-request-id"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def __iter__(self):
        return iter(("data: " + json.dumps(e) + "\n").encode() for e in self.events)


class PlanRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = {"issuer": cp.ISSUER, "subject": "synthetic-user", "client_id": "synthetic-client",
                        "access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
                        "token_type": "Bearer", "scopes": sorted(cp.SCOPES),
                        "expires_in": 3600, "saved_at_unix": int(time.time()),
                        "cost_policy": "existing_subscription_only_no_paid_fallback"}
        cp.atomic_private(self.root / "credentials.json", self.profile)

    def tearDown(self):
        self.temp.cleanup()

    def events(self, *, status="completed", model="gpt-6-luna", text="OK", error=None):
        return [{"type": "response.output_text.delta", "delta": text},
                {"type": "response.completed" if status == "completed" else "response.failed",
                 "response": {"status": status, "model": model, "id": "synthetic-response", "usage": {}, "error": error}}]

    def test_plan_route_ignores_api_key_environment_and_omits_unsupported_fields(self):
        client = cp.PlanClient(self.root)
        captured = []
        client.opener = SimpleNamespace(open=lambda req, **kw: captured.append(req) or Stream(self.events()))
        with patch.dict("os.environ", {"OPENAI_API_KEY": "synthetic-unused-api-credential"}):
            result = client.respond("gpt-6-luna", "synthetic input", "synthetic instruction", schema=cp.answer_schema())
        request = captured[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, cp.API + "/responses")
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-access")
        self.assertFalse(body["store"])
        self.assertTrue(body["stream"])
        for field in ("temperature", "top_p", "max_output_tokens", "previous_response_id", "tools"):
            self.assertNotIn(field, body)
        self.assertFalse(result["paid_fallback_used"])

    def test_missing_scope_and_wrong_policy_fail_closed(self):
        for field, value in (("scopes", []), ("cost_policy", "paid-fallback"), ("issuer", "https://example.invalid"),
                             ("token_type", None), ("scopes", [{}])):
            obj = dict(self.profile)
            obj[field] = value
            cp.atomic_private(self.root / "credentials.json", obj)
            with self.subTest(field=field), self.assertRaises(cp.PlanStop):
                cp.PlanClient(self.root)

    def test_expired_profile_without_refresh_does_not_try_api_key(self):
        self.profile.update(saved_at_unix=0, refresh_token=None)
        cp.atomic_private(self.root / "credentials.json", self.profile)
        client = cp.PlanClient(self.root)
        with self.assertRaises(cp.PlanStop):
            client.access_token()

    def test_stream_quota_failure_stops_without_retry(self):
        client = cp.PlanClient(self.root)
        calls = []
        events = self.events(status="failed", error={"code": "subscription_sharing_usage_limit_exceeded"})
        client.opener = SimpleNamespace(open=lambda req, **kw: calls.append(req) or Stream(events))
        with self.assertRaises(cp.PlanStop) as caught:
            client.respond("gpt-6-luna", "synthetic", "synthetic")
        self.assertIn("usage_limit_exceeded", str(caught.exception))
        self.assertEqual(len(calls), 1)
        self.assertTrue(caught.exception.diagnostic)

    def test_http_429_stops_without_retry_or_credentials_in_error(self):
        client = cp.PlanClient(self.root)
        calls = []

        def fail(req, **kwargs):
            calls.append(req)
            raise urllib.error.HTTPError(req.full_url, 429, "limited", {},
                                         io.BytesIO(b'{"error":{"code":"subscription_sharing_usage_limit_exceeded"}}'))
        client.opener = SimpleNamespace(open=fail)
        with self.assertRaises(cp.PlanStop) as caught:
            client.respond("gpt-6-luna", "synthetic", "synthetic")
        self.assertEqual(len(calls), 1)
        self.assertNotIn(self.profile["access_token"], str(caught.exception))

    def test_model_drift_missing_terminal_and_character_guard_stop(self):
        for events, limit in ((self.events(model="different-model"), 100), (self.events()[:1], 100),
                              (self.events(text="too-long"), 2)):
            client = cp.PlanClient(self.root)
            client.opener = SimpleNamespace(open=lambda req, **kw: Stream(events))
            with self.assertRaises(cp.PlanStop):
                client.respond("gpt-6-luna", "synthetic", "synthetic", max_output_chars=limit)

    def test_no_redirect_can_forward_bearer_credentials(self):
        self.assertIsNone(cp.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid"))

    def test_private_store_permissions_and_symlink_rejection(self):
        self.assertEqual((self.root / "credentials.json").stat().st_mode & 0o777, 0o600)
        alias = self.root / "alias.json"
        alias.symlink_to(self.root / "credentials.json")
        with self.assertRaises(cp.PlanStop):
            cp.atomic_private(alias, {})

    def test_schema_is_fixed_for_both_input_conditions(self):
        schema = cp.answer_schema()
        self.assertEqual(schema, cp.answer_schema())
        self.assertEqual(set(schema["required"]), {"answer", "direction", "claims", "unknowns"})

    @unittest.skipUnless(importlib.util.find_spec("jwt") and importlib.util.find_spec("cryptography"), "Optional OAuth crypto dependency unavailable")
    def test_id_token_signature_audience_and_nonce_are_checked(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {"iss": cp.ISSUER, "sub": "synthetic-subject", "aud": "synthetic-client",
                  "exp": int(time.time()) + 300, "nonce": "synthetic-nonce"}
        token = jwt.encode(claims, key, algorithm="RS256")
        fake = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))
        with patch.object(jwt, "PyJWKClient", return_value=fake):
            identity = cp.verify_identity(token, "synthetic-client", "synthetic-nonce", cp.ISSUER + "/jwks")
            self.assertEqual(identity["sub"], "synthetic-subject")
            for audience, nonce in (("wrong-client", "synthetic-nonce"), ("synthetic-client", "wrong-nonce")):
                with self.assertRaises(cp.PlanStop):
                    cp.verify_identity(token, audience, nonce, cp.ISSUER + "/jwks")
        with self.assertRaises(cp.PlanStop):
            cp.verify_identity(token, "synthetic-client", "synthetic-nonce", "https://example.invalid/jwks")

    def test_plan_config_records_unsupported_parameters_honestly(self):
        config = {"provider": "openai-chatgpt-plan", "model": "gpt-6-luna", "revision": "provider-alias:gpt-6-luna",
                  "parameters": {"temperature": None, "top_p": None, "max_output_tokens": None},
                  "seed_policy": "unsupported", "repeat_seeds": None, "input_token_limit": 16000, "synthetic": True,
                  "transport": {"route": cp.API + "/responses", "store": False, "stream": True,
                                "billing_policy": "subscription_only_no_paid_fallback", "reasoning_effort": "low",
                                "revision_policy": "provider_alias_exploratory", "max_input_characters": 40000,
                                "max_output_characters": 16000, "reported_output_token_guard": 4000}}
        self.assertEqual(vw.model_config(config), config)
        config["parameters"]["temperature"] = 0
        with self.assertRaises(Exception):
            vw.model_config(config)


if __name__ == "__main__":
    unittest.main()


class ClockSkewTests(unittest.TestCase):
    setUp = PlanRouteTests.setUp
    tearDown = PlanRouteTests.tearDown
    @unittest.skipUnless(importlib.util.find_spec("jwt") and importlib.util.find_spec("cryptography"), "Optional OAuth crypto dependency unavailable")
    def test_small_clock_skew_allowed_but_large_future_token_rejected_on_refresh(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        fake = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))
        for seconds in (10, 300):
            self.profile['saved_at_unix'] = 0
            cp.atomic_private(self.root / 'credentials.json', self.profile)
            client = cp.PlanClient(self.root)
            now = int(time.time())
            claims = {'iss':cp.ISSUER,'aud':'synthetic-client','sub':'synthetic-user','iat':now+seconds,'nbf':now+seconds,'exp':now+3600,'nonce':'synthetic-nonce'}
            token = jwt.encode(claims,key,algorithm='RS256')
            result = {'access_token':'synthetic-new-access','refresh_token':'synthetic-new-refresh','expires_in':3600,'token_type':'Bearer','id_token':token}
            client.opener = SimpleNamespace(open=lambda *a, **kw: io.StringIO(json.dumps(result)))
            client._public_json = lambda url: {'jwks_uri':cp.ISSUER+'/jwks'}
            with patch.object(jwt,'PyJWKClient',return_value=fake):
                if seconds == 10:
                    self.assertEqual(client.access_token(),'synthetic-new-access')
                    self.assertEqual(cp.verify_identity(token,'synthetic-client','synthetic-nonce',cp.ISSUER+'/jwks')['sub'],'synthetic-user')
                else:
                    with self.assertRaises(cp.PlanStop): client.access_token()
                    with self.assertRaises(cp.PlanStop): cp.verify_identity(token,'synthetic-client','synthetic-nonce',cp.ISSUER+'/jwks')
                    self.assertEqual(json.loads(client.path.read_text())['access_token'],'synthetic-access')
