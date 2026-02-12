from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class UserIdentity:
    provider: str
    is_authenticated: bool
    name: str | None
    email: str | None
    subject: str | None


def _get_user_value(user: object, keys: tuple[str, ...]) -> str | None:
    if isinstance(user, Mapping):
        for key in keys:
            value = user.get(key)
            if value:
                return str(value)
        return None

    for key in keys:
        value = getattr(user, key, None)
        if value:
            return str(value)
    return None


def _get_user_flag(user: object, key: str) -> bool | None:
    if isinstance(user, Mapping):
        value = user.get(key)
    else:
        value = getattr(user, key, None)
    if isinstance(value, bool):
        return value
    return None


def _is_authenticated(user: object | None) -> bool:
    if user is None:
        return False
    for key in ("is_logged_in", "is_authenticated"):
        flag = _get_user_flag(user, key)
        if flag is not None:
            return flag
    return bool(_get_user_value(user, ("email", "name", "sub", "id", "user_id")))


def _normalize_identity(user: object | None, provider: str) -> UserIdentity:
    return UserIdentity(
        provider=provider,
        is_authenticated=_is_authenticated(user),
        name=_get_user_value(user, ("name", "full_name", "preferred_name")),
        email=_get_user_value(user, ("email", "email_address")),
        subject=_get_user_value(user, ("sub", "user_id", "id")),
    )


def _render_login_prompt(provider: str) -> None:
    st.title("Sign in required")
    st.info("Please sign in to continue.")
    st.login(provider)


def _render_sidebar(identity: UserIdentity) -> None:
    with st.sidebar:
        st.markdown("### Account")
        st.caption(identity.email or "Signed in")
        if st.button("Log out"):
            st.logout()
            st.stop()


def require_login(provider: str = "auth0") -> UserIdentity:
    user = getattr(st, "user", None)
    if not _is_authenticated(user):
        _render_login_prompt(provider)
        st.stop()

    identity = _normalize_identity(user, provider)
    _render_sidebar(identity)
    return identity
