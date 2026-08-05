"""The CORS allowlist must match what a browser actually sends."""
import pytest

from src.config import Settings

_BASE = dict(
    database_url="postgresql://u:p@localhost:5432/db",
    redis_url="redis://localhost:6379/0",
    jwt_secret_key="test-key",
)


def _origins(configured: str) -> list[str]:
    return Settings(_env_file=None, cors_origins=configured, **_BASE).cors_origin_list


def test_a_plain_origin_passes_through():
    assert _origins("https://app.run.app") == ["https://app.run.app"]


def test_a_trailing_slash_is_stripped():
    """The failure this guards: a browser sends `Origin: https://app.run.app` with
    no slash, and CORSMiddleware compares by exact string."""
    assert _origins("https://app.run.app/") == ["https://app.run.app"]


def test_several_trailing_slashes_are_stripped():
    assert _origins("https://app.run.app///") == ["https://app.run.app"]


def test_surrounding_whitespace_is_ignored():
    assert _origins("  https://app.run.app  ") == ["https://app.run.app"]


def test_a_comma_separated_list_is_split_and_cleaned():
    assert _origins(" https://app.run.app/ , https://custom.example.com ") == [
        "https://app.run.app",
        "https://custom.example.com",
    ]


def test_empty_entries_are_dropped():
    assert _origins("https://app.run.app,,") == ["https://app.run.app"]


def test_duplicates_collapse_but_order_is_kept():
    configured = "https://b.example.com,https://a.example.com/,https://b.example.com/"
    assert _origins(configured) == ["https://b.example.com", "https://a.example.com"]


def test_an_unset_allowlist_is_empty_rather_than_a_wildcard():
    """An empty list blocks everything, which is the safe direction. It must never
    silently become "*" — browsers reject a wildcard alongside credentials."""
    assert _origins("") == []
    assert _origins("   ") == []
    assert "*" not in _origins("")


def test_a_port_is_preserved():
    """Local development origins carry a port and must survive normalisation."""
    assert _origins("http://localhost:5173/") == ["http://localhost:5173"]


def test_the_default_covers_local_development():
    default = Settings(_env_file=None, **_BASE).cors_origin_list

    assert "http://localhost:5173" in default


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_scheme_is_not_rewritten(scheme):
    """An origin is scheme-specific; https://x and http://x are different origins."""
    assert _origins(f"{scheme}://app.example.com") == [f"{scheme}://app.example.com"]


# ---------- frontend_base_url shares the same deploy substitution ----------

def _base_url(configured: str) -> str:
    return Settings(_env_file=None, frontend_base_url=configured, **_BASE).frontend_base_url


def test_base_url_keeps_a_single_url_unchanged():
    assert _base_url("https://app.run.app") == "https://app.run.app"


def test_base_url_drops_a_trailing_slash():
    assert _base_url("https://app.run.app/") == "https://app.run.app"


def test_base_url_takes_only_the_first_of_several():
    """CORS may list several origins; an emailed link can only be one. Joining two
    with a comma would produce a dead reset link."""
    assert _base_url("https://app.run.app,https://custom.example.com") == "https://app.run.app"


def test_a_multi_origin_value_serves_both_settings_correctly():
    """One deploy substitution feeds CORS_ORIGINS and FRONTEND_BASE_URL. Both must
    end up correct from the same input."""
    configured = "https://app.run.app/,https://custom.example.com/"
    s = Settings(_env_file=None, cors_origins=configured,
                 frontend_base_url=configured, **_BASE)

    assert s.cors_origin_list == ["https://app.run.app", "https://custom.example.com"]
    assert s.frontend_base_url == "https://app.run.app"
