"""Cross-origin access, configured the same way in every service.

Shared for the same reason as ``shared/errors.py``: it is a contract, not a
convenience. The browser applies one rule to every response it receives, so
seven services answering the same SPA have to agree on the answer, and the only
thing keeping them in agreement once they are separate deployments is that it is
generated from here.

Why every service and not just users
------------------------------------
The gateway is a *proxy*. nginx forwards whatever the upstream returned and adds
no headers of its own, so a response from the restaurants service arrives at the
browser exactly as that service wrote it. The browser then checks it against the
page's origin — and the SPA is served from the frontend's Cloud Run hostname,
while the API answers on the gateway's. Different origins, so the check applies.

That the browser never opens a connection to the restaurants service directly is
true and beside the point: CORS is a rule about the response, not about who was
on the other end of the socket. Before this existed only the users service sent
the header, so sign-in worked and every other call in the app failed the
preflight — with the gateway answering 405, since FastAPI has no OPTIONS route
and there was no middleware to intercept one.

Doing it here rather than in nginx is what keeps a service correct on its own,
and avoids the duplicate ``Access-Control-Allow-Origin`` that a gateway adding
its own header would produce on the one service that already sends one. Browsers
reject a duplicate outright.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def split_origins(value: str) -> list[str]:
    """Parse a comma-separated origin list from configuration.

    Comma-separated because Cloud Run serves each service on two hostnames — the
    project-hash one and the project-number one — and the browser sends whichever
    the visitor actually landed on. Origin matching is byte-exact, so listing one
    locks out everybody who arrived by the other.
    """
    return [o.strip() for o in value.split(",") if o.strip()]


def install_cors(app: FastAPI, origins: list[str]) -> None:
    """Allow the SPA's origin to make credentialed calls to this service."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Credentialed requests, which is why the origin list is explicit and
        # never "*" — the combination is what Starlette refuses and browsers
        # reject, and it is also what would let any site make authenticated
        # requests on a signed-in visitor's behalf.
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
