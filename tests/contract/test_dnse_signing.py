import hashlib
import hmac

from opentrading_mcp.providers.dnse import build_signature, build_ws_auth, build_ws_subscribe


def test_build_signature_vector():
    headers, sig = build_signature(
        "secret", "get", "/price/ohlc", "Wed, 23 Sep 2026 00:00:00 +0000", "abc"
    )
    assert headers == "(request-target) date"
    assert len(sig) > 20
    assert "%" in sig or sig.isalnum() or "=" in sig


def test_ws_auth_signature_matches_hmac():
    msg = build_ws_auth("key1", "s3cr3t", 123, "n1")
    expected = hmac.new(b"s3cr3t", b"key1:123:n1", hashlib.sha256).hexdigest()
    assert msg == {
        "action": "auth",
        "api_key": "key1",
        "signature": expected,
        "timestamp": 123,
        "nonce": "n1",
    }


def test_ws_subscribe_shape():
    msg = build_ws_subscribe("ohlc.1.json", ["VN30F1M"])
    assert msg["action"] == "subscribe"
    assert msg["channels"] == [{"name": "ohlc.1.json", "symbols": ["VN30F1M"]}]
