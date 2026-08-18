"""Refuse to start a production service that is still holding development defaults.

Every service's ``Settings`` carries working defaults so the compose stack comes
up with no configuration at all. That convenience is also the failure mode: a
deploy that forgets a secret does not crash, it starts perfectly and signs tokens
with ``dev-secret-change-me`` — a value published in this repository. Anyone who
can read the source can then mint a token for any user id and any role, in every
service at once, because they all verify against that one shared secret.

Nothing detects that from the outside. The service is healthy, the tokens are
valid, the logs are clean. So the check has to happen at startup, and it has to
stop the process: a service that refuses to boot is a failed deploy, which is
noticed in minutes, while a service that boots on a known secret is a silent
compromise that lasts until someone thinks to look.

Only ``environment == "production"`` is checked. Development and test are exactly
where these defaults are meant to be used.
"""

from typing import Iterable, Protocol


#: Values shipped in this repository. Anything here is public knowledge.
DEV_JWT_SECRETS = frozenset({"dev-secret-change-me", "", "changeme", "secret"})

#: The password in every compose file and every ``database_url`` default.
DEV_DB_PASSWORDS = ("foodpass",)


class _HasSecrets(Protocol):
    environment: str
    service_name: str
    jwt_secret_key: str
    database_url: str


def _problems(settings: _HasSecrets) -> Iterable[str]:
    if settings.jwt_secret_key in DEV_JWT_SECRETS:
        yield (
            "JWT_SECRET_KEY is still a development default. Tokens signed with it "
            "are forgeable by anyone who has read this repository, in every "
            "service that shares the secret."
        )

    if len(settings.jwt_secret_key) < 32:
        yield (
            f"JWT_SECRET_KEY is only {len(settings.jwt_secret_key)} characters. "
            "Use at least 32 bytes of randomness."
        )

    for weak in DEV_DB_PASSWORDS:
        # Matched against the credentials segment only. A database *name* or host
        # that happens to contain the word is not a finding, and a guard that
        # cries wolf gets an environment variable set to silence it.
        credentials = settings.database_url.partition("://")[2].partition("@")[0]
        if weak in credentials:
            yield (
                f"DATABASE_URL still uses the development password {weak!r}. "
                "Issue a strong per-database password."
            )
            break


def assert_production_secrets(settings: _HasSecrets) -> None:
    """Raise ``RuntimeError`` if a production service holds a known dev default.

    Called at import time from each service's ``config`` module, so the process
    dies before it has bound a port or served a request.
    """
    if settings.environment != "production":
        return

    found = list(_problems(settings))
    if not found:
        return

    detail = "\n  - ".join(found)
    raise RuntimeError(
        f"{settings.service_name} refused to start in production:\n  - {detail}\n"
        "Set these from Secret Manager. See infra/gcp/create-secrets.sh."
    )
