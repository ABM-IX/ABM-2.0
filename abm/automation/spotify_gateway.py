"""
abm/automation/spotify_gateway.py
====================================
Spotify Web API Gateway — Phase 7 Tier 1 Automation

Provides search and play control for Spotify using the Web API.
Credentials are read from environment variables — no credentials are
ever hardcoded.

Required environment variables:
    SPOTIFY_CLIENT_ID      : Your Spotify Developer App Client ID.
    SPOTIFY_CLIENT_SECRET  : Your Spotify Developer App Client Secret.
    SPOTIFY_REDIRECT_URI   : OAuth redirect URI (e.g. http://localhost:8888/callback).

Usage:
    from abm.automation.spotify_gateway import SpotifyGateway
    gw = SpotifyGateway()
    if gw.is_configured:
        tracks = gw.search("Kendrick Lamar")
        gw.play(tracks[0].uri)

Design contract:
  - All methods degrade gracefully and return empty lists / False on failure.
  - Credentials are read at instantiation from env vars. Never stored in config files.
  - Token refresh happens automatically before each API call.
  - play() uses the Spotify Player API (requires a Premium account and an active device).
  - search() returns up to ``limit`` Track results.
  - Never raises to the caller.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment variable names
# ---------------------------------------------------------------------------

SPOTIFY_CLIENT_ID_ENV = "SPOTIFY_CLIENT_ID"
SPOTIFY_CLIENT_SECRET_ENV = "SPOTIFY_CLIENT_SECRET"
SPOTIFY_REDIRECT_URI_ENV = "SPOTIFY_REDIRECT_URI"

# Spotify API endpoints
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SEARCH_URL = "https://api.spotify.com/v1/search"
_PLAY_URL = "https://api.spotify.com/v1/me/player/play"
_DEVICES_URL = "https://api.spotify.com/v1/me/player/devices"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Track:
    """
    A Spotify track result from ``SpotifyGateway.search()``.

    Attributes
    ----------
    name : str
        Track title.
    artist : str
        Primary artist name.
    album : str
        Album name.
    uri : str
        Spotify URI in the form ``spotify:track:<id>``. Pass to ``play()``.
    duration_ms : int
        Track duration in milliseconds.
    """

    name: str
    artist: str
    album: str
    uri: str
    duration_ms: int = 0

    def __str__(self) -> str:
        return f"{self.artist} — {self.name} ({self.album})"


# ---------------------------------------------------------------------------
# SpotifyGateway
# ---------------------------------------------------------------------------


class SpotifyGateway:
    """
    Spotify Web API client for search and playback control.

    Credentials are read from environment variables:
      ``SPOTIFY_CLIENT_ID``, ``SPOTIFY_CLIENT_SECRET``, ``SPOTIFY_REDIRECT_URI``.

    Uses the Client Credentials flow for search (no user login required).
    Uses the Authorization Code flow token (if SPOTIFY_ACCESS_TOKEN is set)
    for playback control.

    Parameters
    ----------
    timeout_seconds : int
        HTTP timeout for Spotify API requests. Default 10.
    """

    def __init__(self, timeout_seconds: int = 10) -> None:
        self._client_id = os.environ.get(SPOTIFY_CLIENT_ID_ENV, "")
        self._client_secret = os.environ.get(SPOTIFY_CLIENT_SECRET_ENV, "")
        self._redirect_uri = os.environ.get(SPOTIFY_REDIRECT_URI_ENV, "http://localhost:8888/callback")
        self._timeout = timeout_seconds

        # Token cache
        self._access_token: str = ""
        self._token_expiry: float = 0.0

        if not self.is_configured:
            logger.warning(
                "SpotifyGateway: %s and/or %s not set — all calls will return empty results.",
                SPOTIFY_CLIENT_ID_ENV, SPOTIFY_CLIENT_SECRET_ENV,
            )

    @property
    def is_configured(self) -> bool:
        """True if both Client ID and Client Secret are set."""
        return bool(self._client_id and self._client_secret)

    def search(self, query: str, limit: int = 10) -> list[Track]:
        """
        Search Spotify for tracks matching ``query``.

        Uses the Client Credentials OAuth flow — no user login needed for search.

        Parameters
        ----------
        query : str
            Search query (artist name, song title, etc.).
        limit : int
            Maximum number of results to return (1–50). Default 10.

        Returns
        -------
        list[Track]
            Matched tracks in order of relevance. Empty list on error.
        """
        if not self.is_configured:
            logger.debug("SpotifyGateway.search: not configured.")
            return []

        if not query or not query.strip():
            return []

        token = self._get_client_credentials_token()
        if not token:
            return []

        try:
            resp = requests.get(
                _SEARCH_URL,
                params={"q": query, "type": "track", "limit": min(max(1, limit), 50)},
                headers={"Authorization": f"Bearer {token}"},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("tracks", {}).get("items", [])
            tracks = []
            for item in items:
                try:
                    artist = item["artists"][0]["name"] if item.get("artists") else "Unknown"
                    tracks.append(Track(
                        name=item.get("name", ""),
                        artist=artist,
                        album=item.get("album", {}).get("name", ""),
                        uri=item.get("uri", ""),
                        duration_ms=item.get("duration_ms", 0),
                    ))
                except (KeyError, IndexError) as exc:
                    logger.debug("SpotifyGateway.search: skipping malformed item — %s", exc)
            logger.info("SpotifyGateway.search: found %d tracks for %r.", len(tracks), query)
            return tracks
        except requests.exceptions.RequestException as exc:
            logger.warning("SpotifyGateway.search: request failed — %s", exc)
            return []

    def play(self, track_uri: str, device_id: Optional[str] = None) -> bool:
        """
        Start playback of a track on an active Spotify device.

        Requires a user-level access token (Authorization Code flow).
        The token must be set via the ``SPOTIFY_ACCESS_TOKEN`` environment variable.

        Parameters
        ----------
        track_uri : str
            Spotify track URI (``spotify:track:<id>``). Obtained from ``search()``.
        device_id : str, optional
            Target device ID. If None, Spotify uses the currently active device.

        Returns
        -------
        bool
            True if the play command was accepted (HTTP 204), False otherwise.
        """
        if not self.is_configured:
            logger.debug("SpotifyGateway.play: not configured.")
            return False

        if not track_uri:
            return False

        # Playback requires user-level auth (Authorization Code flow)
        user_token = os.environ.get("SPOTIFY_ACCESS_TOKEN", "")
        if not user_token:
            logger.warning(
                "SpotifyGateway.play: SPOTIFY_ACCESS_TOKEN not set. "
                "Playback requires a user-level OAuth token from the Authorization Code flow."
            )
            return False

        payload = {"uris": [track_uri]}
        params = {}
        if device_id:
            params["device_id"] = device_id

        try:
            resp = requests.put(
                _PLAY_URL,
                json=payload,
                params=params,
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
            if resp.status_code == 204:
                logger.info("SpotifyGateway.play: playing %s.", track_uri)
                return True
            elif resp.status_code == 404:
                logger.warning(
                    "SpotifyGateway.play: no active device found. "
                    "Open Spotify on a device first."
                )
                return False
            else:
                logger.warning(
                    "SpotifyGateway.play: unexpected HTTP %d — %s",
                    resp.status_code, resp.text[:200],
                )
                return False
        except requests.exceptions.RequestException as exc:
            logger.warning("SpotifyGateway.play: request failed — %s", exc)
            return False

    def get_devices(self) -> list[dict]:
        """
        List available Spotify playback devices.

        Returns
        -------
        list[dict]
            Each dict has ``id``, ``name``, ``type``, ``is_active``.
            Empty on error or if no user token is available.
        """
        user_token = os.environ.get("SPOTIFY_ACCESS_TOKEN", "")
        if not user_token:
            return []
        try:
            resp = requests.get(
                _DEVICES_URL,
                headers={"Authorization": f"Bearer {user_token}"},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json().get("devices", [])
        except Exception as exc:
            logger.debug("SpotifyGateway.get_devices: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal token management
    # ------------------------------------------------------------------

    def _get_client_credentials_token(self) -> str:
        """
        Get a client credentials access token (for search only).

        Caches the token in memory and refreshes it 30 seconds before expiry.

        Returns
        -------
        str
            Bearer token string. Empty string on failure.
        """
        if self._access_token and time.monotonic() < self._token_expiry - 30:
            return self._access_token

        credentials = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()

        try:
            resp = requests.post(
                _TOKEN_URL,
                data={"grant_type": "client_credentials"},
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = time.monotonic() + data.get("expires_in", 3600)
            logger.debug("SpotifyGateway: client credentials token refreshed.")
            return self._access_token
        except (requests.exceptions.RequestException, KeyError) as exc:
            logger.warning("SpotifyGateway._get_client_credentials_token: failed — %s", exc)
            return ""


__all__ = ["SpotifyGateway", "Track", "SPOTIFY_CLIENT_ID_ENV", "SPOTIFY_CLIENT_SECRET_ENV"]

