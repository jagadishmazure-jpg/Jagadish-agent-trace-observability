"""PII redaction: phones and SSNs out, dates untouched."""
from tracing.redact import REDACTED, redact_text


def test_phone_with_parens():
    out = redact_text("call the customer at (555) 123-4567 today")
    assert REDACTED in out
    assert "555" not in out and "4567" not in out


def test_phone_with_country_code():
    out = redact_text("reach me at +1 (555) 123-4567 please")
    assert REDACTED in out
    assert "555" not in out


def test_phone_dotted():
    out = redact_text("number 555.123.4567 on file")
    assert REDACTED in out
    assert "555" not in out


def test_phone_dashed():
    out = redact_text("number 555-123-4567 on file")
    assert REDACTED in out
    assert "4567" not in out


def test_phone_bare_digits():
    out = redact_text("dial 5551234567 now")
    assert REDACTED in out
    assert "5551234567" not in out


def test_ssn_redacted():
    out = redact_text("ssn 123-45-6789 provided")
    assert REDACTED in out
    assert "123-45-6789" not in out
    assert "6789" not in out


def test_date_not_redacted():
    text = "order placed on 2026-10-22 ships by 2026-10-25"
    assert redact_text(text) == text


def test_phone_redacted_but_date_kept_in_same_string():
    out = redact_text("on 2026-10-22 call (555) 123-4567 about order CP-1042")
    assert "2026-10-22" in out
    assert "CP-1042" in out
    assert "555" not in out


def test_card_number_redacted():
    out = redact_text("card 4111 1111 1111 1111 charged")
    assert REDACTED in out
    assert "4111" not in out


def test_long_digit_run_redacted():
    out = redact_text("account 123456789012 needs review")
    assert REDACTED in out
    assert "123456789012" not in out


def test_plain_text_unchanged():
    text = "the order shipped from the west warehouse"
    assert redact_text(text) == text


def test_empty_string():
    assert redact_text("") == ""
