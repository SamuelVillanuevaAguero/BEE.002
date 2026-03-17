"""
Singleton session managers for Beecker, Slack, and FreshDesk.

All RPA monitors share the same credentials — there is no reason
to perform multiple logins for concurrent executions.

Each manager is a module-level singleton:
    - BeeckerSessionManager: JWT with auto-refresh (token lasts ~4h)
    - SlackSessionManager:   static bot token, no expiry
    - FreshDeskSessionManager: Basic Auth, no expiry
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── Margen de seguridad: refrescar si quedan menos de N minutos ───────────────
_REFRESH_MARGIN_MINUTES = 5


# ═══════════════════════════════════════════════════════════════════════════════
# Beecker
# ═══════════════════════════════════════════════════════════════════════════════

class BeeckerSessionManager:
    """
    Singleton that holds a single authenticated Beecker session.

    Usage:
        token = await beecker_session.get_token(email, password, http_client)

    The token is shared across all concurrent RPA monitors.
    Auto-refresh triggers when < 5 minutes remain before expiry.
    A Lock prevents duplicate logins on simultaneous first requests.
    """

    _instance: Optional[BeeckerSessionManager] = None

    def __new__(cls) -> BeeckerSessionManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _init_state(self) -> None:
        if self._initialized:
            return
        self._access_token:  Optional[str]      = None
        self._refresh_token: Optional[str]      = None
        self._expires_at:    Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._initialized = True

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_token(
        self,
        email: str,
        password: str,
        http_client,           # HttpClient instance from caller
        login_url:   str = "https://api.dashboard.beecker.ai/api/auth/login/",
        refresh_url: str = "https://api.beecker.ai/api/auth/token/refresh/",
    ) -> str:
        """
        Return a valid access token, refreshing or re-logging as needed.

        Args:
            email / password: Beecker credentials (same for all RPAs).
            http_client:      Caller's HttpClient (used for auth requests only).
            login_url:        Full login endpoint.
            refresh_url:      Full token-refresh endpoint.

        Returns:
            Bearer access token string.
        """
        self._init_state()

        async with self._lock:
            # ── Caso 1: sesión válida ─────────────────────────────────────────
            if self._is_valid():
                return self._access_token  # type: ignore[return-value]

            # ── Caso 2: tenemos refresh token y el acceso está por expirar ────
            if self._refresh_token:
                try:
                    await self._do_refresh(http_client, refresh_url)
                    logger.info("🔄 [BeeckerSession] Token refrescado correctamente.")
                    return self._access_token  # type: ignore[return-value]
                except Exception as e:
                    logger.warning(
                        f"⚠️ [BeeckerSession] Refresh falló ({e}), haciendo login completo."
                    )

            # ── Caso 3: primer login o refresh fallido ────────────────────────
            await self._do_login(email, password, http_client, login_url)
            logger.info("🔐 [BeeckerSession] Login exitoso. Sesión activa por ~4h.")
            return self._access_token  # type: ignore[return-value]

    def force_invalidate(self) -> None:
        """Force next get_token() call to refresh/re-login (e.g. after a 401)."""
        self._init_state()
        self._expires_at = None
        logger.warning("⚠️ [BeeckerSession] Sesión invalidada manualmente (probable 401).")

    def reset(self) -> None:
        """Full reset — use only in tests."""
        self._initialized = False
        self._init_state()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _is_valid(self) -> bool:
        if not self._access_token or not self._expires_at:
            return False
        margin = timedelta(minutes=_REFRESH_MARGIN_MINUTES)
        return datetime.now(tz=timezone.utc) < (self._expires_at - margin)

    async def _do_login(
        self, email: str, password: str, http_client, login_url: str
    ) -> None:
        result = await http_client.post(
            login_url,
            json={"email": email, "password": password},
            params={},
        )
        if not result["success"]:
            raise RuntimeError(
                f"[BeeckerSession] Login falló: status={result['status_code']}"
            )
        data = result["data"]
        self._store_tokens(
            access=data["access"],
            refresh=data.get("refresh"),
        )

    async def _do_refresh(self, http_client, refresh_url: str) -> None:
        result = await http_client.post(
            refresh_url,
            json={"refresh": self._refresh_token},
            params={},
        )
        if not result["success"]:
            raise RuntimeError(
                f"[BeeckerSession] Refresh falló: status={result['status_code']}"
            )
        data = result["data"]
        self._store_tokens(
            access=data["access"],
            refresh=self._refresh_token,   # el refresh token no cambia
        )

    def _store_tokens(self, access: str, refresh: Optional[str]) -> None:
        """Decode exp from JWT payload without external libraries."""
        import base64, json as _json
        payload_b64 = access.split(".")[1]
        padding     = 4 - len(payload_b64) % 4
        payload     = _json.loads(
            base64.urlsafe_b64decode(payload_b64 + "=" * padding)
        )
        exp = payload.get("exp")
        self._access_token  = access
        self._refresh_token = refresh or self._refresh_token
        self._expires_at    = (
            datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        )
        if self._expires_at:
            remaining = (self._expires_at - datetime.now(tz=timezone.utc)).seconds // 60
            logger.debug(f"[BeeckerSession] Token válido por ~{remaining} min.")


# ── Instancia global ──────────────────────────────────────────────────────────
beecker_session = BeeckerSessionManager()


# ═══════════════════════════════════════════════════════════════════════════════
# Slack
# ═══════════════════════════════════════════════════════════════════════════════

class SlackSessionManager:
    """
    Singleton that holds a single authenticated SlackAPI instance.
    The Slack bot token is static and does not expire.
    """

    _instance: Optional[SlackSessionManager] = None

    def __new__(cls) -> SlackSessionManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._api     = None
            cls._instance._token   = None
            cls._instance._lock    = asyncio.Lock()
        return cls._instance

    async def get_api(self, token: str):
        """Return the shared SlackAPI instance, authenticating once if needed."""
        async with self._lock:
            if self._api is not None and self._token == token:
                return self._api

            from app.services.slack.slack_api import SlackAPI
            api = SlackAPI()
            await api.login(token)
            self._api   = api
            self._token = token
            logger.info("🔐 [SlackSession] Autenticado correctamente (singleton).")
            return self._api

    def reset(self) -> None:
        self._api   = None
        self._token = None


slack_session = SlackSessionManager()


# ═══════════════════════════════════════════════════════════════════════════════
# FreshDesk
# ═══════════════════════════════════════════════════════════════════════════════

class FreshDeskSessionManager:
    """
    Singleton that holds a single authenticated FreshDeskAPI instance.
    FreshDesk uses Basic Auth — credentials don't expire.
    """

    _instance: Optional[FreshDeskSessionManager] = None

    def __new__(cls) -> FreshDeskSessionManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._api      = None
            cls._instance._username = None
            cls._instance._lock     = asyncio.Lock()
        return cls._instance

    async def get_api(self, username: str, password: str):
        """Return the shared FreshDeskAPI instance, authenticating once if needed."""
        async with self._lock:
            if self._api is not None and self._username == username:
                return self._api

            from app.services.freshdesk.freshdesk_api import FreshDeskAPI
            api = FreshDeskAPI()
            await api.login(username, password)
            self._api      = api
            self._username = username
            logger.info("🔐 [FreshDeskSession] Autenticado correctamente (singleton).")
            return self._api

    def reset(self) -> None:
        self._api      = None
        self._username = None


freshdesk_session = FreshDeskSessionManager()