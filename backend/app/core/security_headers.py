"""
Baseline security response headers, added to every response.

Deliberately does not set Content-Security-Policy: this API mostly
serves JSON, but also serves the interactive /docs and /redoc pages
(Swagger UI / ReDoc), which load their JS/CSS from a CDN - a CSP
tight enough to be meaningful would need to be tuned against those
pages specifically to avoid breaking them, and a CSP loose enough not
to isn't worth adding. CSP is more relevant at the frontend/nginx
layer, which actually serves the application's HTML - see
frontend/nginx.conf.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Stops the browser from guessing a response's content type
        # from its content, overriding the declared Content-Type -
        # relevant here since e.g. an uploaded transcript's extracted
        # text is echoed back in JSON responses.
        response.headers["X-Content-Type-Options"] = "nosniff"

        # No page this API ever returns should be framed by another
        # site (clickjacking protection). The frontend SPA is a
        # separate origin/deployment and sets its own policy.
        response.headers["X-Frame-Options"] = "DENY"

        # Send the full referrer only to same-origin requests; only
        # the origin (not the path/query) to cross-origin ones. Avoids
        # leaking e.g. a password-reset or OAuth callback URL's query
        # string to a third party via the Referer header.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Tells browsers to only ever connect to this host over HTTPS
        # for the next 2 years, including subdomains. Harmless to send
        # over a plain HTTP connection in local development - browsers
        # only start honoring it once they've received it over HTTPS
        # at least once, per the HSTS spec, so this has no effect
        # until the app is actually served over TLS (see the
        # deployment guide for where TLS termination happens).
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )

        # No feature this API needs the browser to gate (camera, mic,
        # geolocation, etc.) - explicitly deny all of them for any
        # response that somehow ends up rendered rather than consumed
        # as JSON.
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        return response
