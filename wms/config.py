"""Configuration helpers.

Goal: allow the app to run both locally and on Streamlit Cloud.

Priority order for config values:
1) Environment variables (best for local development)
2) Streamlit secrets (Streamlit Cloud or local `.streamlit/secrets.toml`)

Note: Streamlit prints an informational message if no secrets are configured.
We try env vars first to avoid that message during local runs.
"""

from __future__ import annotations

import os
from typing import Optional

import streamlit as st


def _get_from_secrets(key: str) -> Optional[str]:
    """Safely read a value from `st.secrets`.

    Streamlit prints an informational message when no secrets are configured.
    Using `.get()` avoids a KeyError and keeps the app behavior consistent.
    """

    try:
        # st.secrets behaves like a mapping and supports .get()
        return st.secrets.get(key)  # type: ignore[attr-defined]
    except Exception:
        # In extremely early import scenarios or edge environments, st.secrets
        # access can fail. Treat it as absent.
        return None


def get_setting(*, key: str, env: str | None = None, required: bool = False) -> Optional[str]:
    """Get a configuration value.

    Args:
        key: Name of the key in Streamlit secrets (e.g. "mongo_uri")
        env: Environment variable name (e.g. "MONGO_URI"). If not provided,
            defaults to uppercased `key`.
        required: If True, show a helpful Streamlit error and stop if missing.
    """

    env_name = env or key.upper()

    # Read env var *first* so local development doesn't depend on Streamlit
    # secrets and doesn't trigger the "No secrets found" message.
    value = os.getenv(env_name)
    if value:
        return value

    value = _get_from_secrets(key)
    if value:
        return value

    if required:
        st.error(
            "Missing configuration. Please set either "
            f"`{key}` in Streamlit secrets or the environment variable `{env_name}`."
        )
        st.stop()
    return None


def get_mongo_uri(*, required: bool = True) -> Optional[str]:
    """Convenience accessor for MongoDB connection string."""

    return get_setting(key="mongo_uri", env="MONGO_URI", required=required)
