from starlette.requests import Request

from app.core.security import _same_origin_request, hash_password, verify_password


def _request(headers: dict[str, str], method: str = "POST") -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": method,
        "headers": raw_headers,
        "path": "/api/v1/library/import",
        "query_string": b"",
    }
    return Request(scope)


def test_same_origin_request_trusts_sec_fetch_site_same_origin():
    req = _request({"sec-fetch-site": "same-origin", "host": "veriref.pro"})
    assert _same_origin_request(req) is True


def test_same_origin_request_rejects_sec_fetch_site_cross_site():
    req = _request({"sec-fetch-site": "cross-site", "host": "veriref.pro"})
    assert _same_origin_request(req) is False


def test_same_origin_request_falls_back_to_origin_host_match():
    req = _request({"origin": "https://veriref.pro", "host": "veriref.pro"})
    assert _same_origin_request(req) is True


def test_same_origin_request_rejects_mismatched_origin_host():
    req = _request({"origin": "https://evil.example", "host": "veriref.pro"})
    assert _same_origin_request(req) is False


def test_same_origin_request_allows_when_neither_header_present():
    """No Sec-Fetch-Site and no Origin: ambiguous (old browser / non-fetch
    client), not the shape of a real CSRF attempt -- SameSite=Lax is
    already the primary defence for that case.
    """
    req = _request({"host": "veriref.pro"})
    assert _same_origin_request(req) is True


def test_password_hash_round_trip():
    stored = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", stored) is True
    assert verify_password("wrong", stored) is False


def test_password_hashes_are_salted():
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_password_fails_closed_on_malformed_stored_hash():
    for bad in ("", "not-a-hash", "pbkdf2_sha256$abc", "argon2$1$2$3$4"):
        assert verify_password("anything", bad) is False
