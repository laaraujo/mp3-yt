"""Tests for process-wide runtime configuration."""

from __future__ import annotations

import os

import certifi

from slicer.runtime import configure_tls_ca_bundle


def test_configure_tls_ca_bundle_sets_certifi_paths(monkeypatch) -> None:
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)

    configure_tls_ca_bundle()

    assert os.environ["SSL_CERT_FILE"] == certifi.where()
    assert os.environ["REQUESTS_CA_BUNDLE"] == certifi.where()


def test_configure_tls_ca_bundle_preserves_explicit_paths(monkeypatch) -> None:
    monkeypatch.setenv("SSL_CERT_FILE", "/custom/ssl.pem")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/custom/requests.pem")

    configure_tls_ca_bundle()

    assert os.environ["SSL_CERT_FILE"] == "/custom/ssl.pem"
    assert os.environ["REQUESTS_CA_BUNDLE"] == "/custom/requests.pem"
