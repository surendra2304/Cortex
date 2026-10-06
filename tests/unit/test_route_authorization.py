"""Authorization inventory: every API route must be guarded.

This test would have caught audit defect C4 (36 of 75 routes unauthenticated).
A route is considered guarded when its dependency graph contains one of the
known authentication dependencies. Routes that authenticate by another
documented mechanism (public API key header, Stripe signature, metrics token,
WebSocket token) must be listed in ``CREDENTIAL_IN_HANDLER`` explicitly, so
adding a new public route requires a deliberate, reviewable change here.
"""

from __future__ import annotations

from cortex_api.main import app
from fastapi.routing import APIRoute

AUTH_DEPENDENCIES = {
    "verify_jwt_token",
    "role_checker",
    "verify_friday_token",
    "service_or_operator_auth",
}

# Routes that authenticate inside the handler or by design carry no principal.
CREDENTIAL_IN_HANDLER = {
    ("GET", "/"),  # serves dashboard / JSON liveness
    ("HEAD", "/"),
    ("GET", "/dashboard"),
    ("GET", "/dashboard/"),
    ("GET", "/v1/health"),
    ("GET", "/health"),
    ("HEAD", "/health"),
    ("GET", "/health/ready"),
    ("GET", "/metrics"),  # optional METRICS_TOKEN enforced in-handler
    ("POST", "/v1/events"),  # X-Cortex-Public-Key
    ("POST", "/v1/events/batch"),  # X-Cortex-Public-Key
    ("POST", "/v1/webhooks/{provider}"),  # X-Cortex-Public-Key + HMAC signature
    ("POST", "/v1/webhooks/stripe"),  # Stripe-Signature
    ("GET", "/{file_name:path}"),  # static dashboard export / SPA fallback
}

IGNORED_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _flatten_dependency_names(dependant, acc: list[str]) -> list[str]:
    for dependency in dependant.dependencies:
        call = dependency.call
        acc.append(getattr(call, "__name__", str(call)))
        _flatten_dependency_names(dependency, acc)
    return acc


def _all_api_routes() -> list[APIRoute]:
    routes: list[APIRoute] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append(route)
        else:
            original = getattr(route, "original_router", None)
            if original is not None:
                routes.extend(item for item in original.routes if isinstance(item, APIRoute))
    return routes


def test_every_api_route_is_authenticated():
    unguarded = []
    for route in _all_api_routes():
        if route.path in IGNORED_PATHS:
            continue
        names = set(_flatten_dependency_names(route.dependant, []))
        if names & AUTH_DEPENDENCIES:
            continue
        methods = {method.upper() for method in route.methods} - {"HEAD", "OPTIONS"}
        for method in sorted(methods):
            if (method, route.path) in CREDENTIAL_IN_HANDLER:
                continue
            unguarded.append(f"{method} {route.path}")

    assert not unguarded, (
        "These routes have no authentication dependency and are not declared as "
        "credential-in-handler routes:\n  " + "\n  ".join(sorted(unguarded))
    )


def test_high_risk_routes_are_absent_from_the_public_allowlist():
    """Guard-rails: privileged paths must never be added to the public allowlist silently."""
    privileged_prefixes = (
        "/v1/tenants",
        "/v1/privacy",
        "/v1/approvals",
        "/v1/actions",
        "/v1/memory",
        "/v1/strategies",
        "/v1/workflows",
        "/v1/security",
        "/v1/predictive",
        "/v1/sentinel",
        "/v1/task",
        "/v1/api-keys",
    )
    leaked = [f"{method} {path}" for method, path in CREDENTIAL_IN_HANDLER if path.startswith(privileged_prefixes)]
    assert leaked == [], f"Privileged routes must not sit in the public allowlist: {leaked}"
