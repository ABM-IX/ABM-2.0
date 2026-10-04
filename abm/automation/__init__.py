"""
abm/automation/__init__.py
===========================
ABM 2.0 Automation Layer — Tier 1 (safe, no confirmation required)

Exposes:
  - DynamicLauncher : launch any application by name or path
  - SpotifyGateway  : Spotify Web API client (search + play)

Tier 2 (WhatsApp) is in abm.automation.whatsapp_gateway and requires
explicit manual confirmation before any message is sent.
"""

from .launcher_map import DynamicLauncher, LaunchResult
from .spotify_gateway import SpotifyGateway, Track

__all__ = [
    "DynamicLauncher",
    "LaunchResult",
    "SpotifyGateway",
    "Track",
]
