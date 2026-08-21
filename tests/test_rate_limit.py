import pytest
from starlette.requests import Request
from backend.core.rate_limit import InMemoryRateLimiter, get_client_identifier


def test_rate_limiter_basic():
    limiter = InMemoryRateLimiter()
    # 3 hits allowed
    for _ in range(3):
        limiter.hit(scope="test_scope", key="key1", max_attempts=3, window_seconds=10, block_seconds=60, detail="Rate limit exceeded")

    # 4th hit should trigger 429
    with pytest.raises(Exception) as exc_info:
        limiter.hit(scope="test_scope", key="key1", max_attempts=3, window_seconds=10, block_seconds=60, detail="Rate limit exceeded")
    assert exc_info.value.status_code == 429


def test_rate_limiter_reset():
    limiter = InMemoryRateLimiter()
    limiter.hit(scope="test_scope", key="key1", max_attempts=1, window_seconds=10, block_seconds=60, detail="Rate limit exceeded")
    limiter.reset("test_scope", "key1")
    # should succeed again
    limiter.hit(scope="test_scope", key="key1", max_attempts=1, window_seconds=10, block_seconds=60, detail="Rate limit exceeded")


def test_get_client_identifier_ip_sanitization():
    # Valid IP in X-Forwarded-For
    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 70.41.3.18")],
        "client": ("127.0.0.1", 12345),
    }
    req = Request(scope)
    assert get_client_identifier(req) == "203.0.113.195"

    # Malicious injection in X-Forwarded-For falls back to real-ip or client
    scope_spoofed = {
        "type": "http",
        "headers": [
            (b"x-forwarded-for", b"../../attacker' OR 1=1--"),
            (b"x-real-ip", b"198.51.100.4"),
        ],
        "client": ("127.0.0.1", 12345),
    }
    req_spoofed = Request(scope_spoofed)
    assert get_client_identifier(req_spoofed) == "198.51.100.4"
