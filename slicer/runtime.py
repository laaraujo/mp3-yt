"""Process-wide runtime setup for packaged app builds."""

from __future__ import annotations

import os


def configure_tls_ca_bundle() -> None:
    """Point Python HTTPS clients at certifi's CA bundle when none is configured.

    Frozen macOS apps cannot rely on a user's shell or Python.org certificate
    installer having configured OpenSSL paths. Setting these environment
    variables before importing network clients keeps yt-dlp certificate
    validation enabled while making the bundle self-contained.
    """
    try:
        import certifi
    except ImportError:
        return

    cafile = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", cafile)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", cafile)
