"""The browser's CORS check (preflight) before every authenticated call."""

import pytest


def preflight(client, origin, path="/auth/sync"):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        },
    )


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5199"],
)
def test_local_frontends_are_allowed_on_any_port(client, origin):
    for path in ("/auth/sync", "/auth/otp/send", "/autopilot/post", "/facebook/publish"):
        response = preflight(client, origin, path)

        assert response.status_code == 200, (origin, path)
        assert response.headers["access-control-allow-origin"] == origin
        assert "authorization" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost.evil.example", "http://192.168.1.5:5173"])
def test_other_sites_are_refused(client, origin):
    response = preflight(client, origin)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
