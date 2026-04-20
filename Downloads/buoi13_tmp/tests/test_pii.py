from app.pii import scrub_text, scrub_value


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_phone_and_id() -> None:
    out = scrub_text("Call 090 123 4567 or use CCCD 012345678901")
    assert "090" not in out
    assert "012345678901" not in out
    assert "REDACTED_PHONE_VN" in out
    assert "REDACTED_CCCD" in out


def test_scrub_nested_values() -> None:
    payload = {
        "email": "student@vinuni.edu.vn",
        "profile": {"token": "bearer abcdefghijklmnop"},
        "items": ["hotline 0901234567", {"cccd": "012345678901"}],
    }
    out = scrub_value(payload)
    assert out["email"] == "[REDACTED_EMAIL]"
    assert out["profile"]["token"] == "[REDACTED_TOKEN]"
    assert out["items"][0] == "hotline [REDACTED_PHONE_VN]"
    assert out["items"][1]["cccd"] == "[REDACTED_CCCD]"
