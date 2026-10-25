"""F3/F8: behaviour tests for the CORS_ORIGINS environment variable.

`create_app()` builds the `origins` list synchronously at construction time and hands
it to `CORSMiddleware`, without needing to start the ASGI lifespan (no database access).
So this file deliberately avoids the `client`/`session` fixtures, calls `create_app()`
directly and inspects the kwargs of `CORSMiddleware` in `app.user_middleware`.
"""

from main import create_app

_DEFAULT_ORIGINS = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
]


def _cors_allow_origins(app) -> list[str]:
    for m in app.user_middleware:
        if m.cls.__name__ == "CORSMiddleware":
            return m.kwargs["allow_origins"]
    raise AssertionError("CORSMiddleware 未掛載")


def test_cors_defaults_to_localhost_when_unset(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    app = create_app()
    assert _cors_allow_origins(app) == _DEFAULT_ORIGINS


def test_cors_splits_comma_separated_list_and_strips_whitespace(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com, https://b.example.com")
    app = create_app()
    assert _cors_allow_origins(app) == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_cors_falls_back_to_default_when_set_to_empty_string(monkeypatch, capsys):
    """F3: CORS_ORIGINS="" means "set but empty" and takes the `or default_origins`
    path (the variable itself is an empty string and is replaced by the default before
    parsing).

    The extra assertion "no warning printed" is where this test's real discriminating
    power lies: if someone removed `or default_origins` and relied only on the later
    `if not origins:` guard (origins would still fall back correctly, since parse("") is
    also empty), an extra warning would be printed here, blending with the "," case
    below and losing the signal that "the two paths are independent" -- the value of
    allow_origins alone cannot detect this difference."""
    monkeypatch.setenv("CORS_ORIGINS", "")
    app = create_app()
    assert _cors_allow_origins(app) == _DEFAULT_ORIGINS
    assert "CORS_ORIGINS" not in capsys.readouterr().out


def test_cors_falls_back_to_default_when_only_commas(monkeypatch):
    """F8: CORS_ORIGINS="," means "set, but every item is empty after split", unlike
    the "" case above -- this takes the second guard, `if not origins:`. Each path needs
    its own test, otherwise removing either one would go undetected."""
    monkeypatch.setenv("CORS_ORIGINS", ",")
    app = create_app()
    assert _cors_allow_origins(app) == _DEFAULT_ORIGINS


def test_cors_falls_back_to_default_when_whitespace_and_commas(monkeypatch):
    """F8: a comma-only variant with spaces such as " , " (e.g. a stray comma pasted in
    during deployment) must also fall back, not produce allow_origins=[]."""
    monkeypatch.setenv("CORS_ORIGINS", " , ")
    app = create_app()
    assert _cors_allow_origins(app) == _DEFAULT_ORIGINS


def test_cors_fallback_logs_warning_instead_of_staying_silent(monkeypatch, capsys):
    """F8: half of the original problem was that it was silent -- a fallback must leave a log,
    otherwise this problem shows up as "nothing works and there is no way to find out why"."""
    monkeypatch.setenv("CORS_ORIGINS", ",")
    create_app()
    captured = capsys.readouterr()
    assert "CORS_ORIGINS" in captured.out
