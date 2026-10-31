from types import SimpleNamespace

from app.answer_cache import normalize_question
from app.limits import client_ip, hash_ip


def fake_request(headers, host="1.2.3.4"):
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_questions_are_normalised():
    assert normalize_question("  How does   Key rotation work?? ") == "how does key rotation work"
    assert normalize_question("How does key rotation work") == "how does key rotation work"


def test_client_ip_uses_the_last_forwarded_entry():
    request = fake_request({"x-forwarded-for": "6.6.6.6, 9.9.9.9"})
    assert client_ip(request) == "9.9.9.9"


def test_client_ip_falls_back_to_the_socket_address():
    assert client_ip(fake_request({})) == "1.2.3.4"


def test_hashed_addresses_are_stable_and_hide_the_address():
    assert hash_ip("1.2.3.4") == hash_ip("1.2.3.4")
    assert "1.2.3.4" not in hash_ip("1.2.3.4")
    assert hash_ip("1.2.3.4") != hash_ip("1.2.3.5")