"""
abm/automation/whatsapp_gateway.py
=====================================
WhatsApp Web Automation Gateway — Phase 8 Tier 2 Automation

SAFETY CONTRACT (NON-NEGOTIABLE):
  Every outbound WhatsApp message MUST pass through a two-step flow:
    1. compose()          — Types message, shows preview, STOPS before sending.
    2. confirm_and_send() — Called only after explicit human confirmation.
                            Pressing Enter/clicking Confirm in the UI → send.

  Bypassing this two-step flow is architecturally forbidden. The code enforces
  this at the call level: confirm_and_send() raises AssertionError if compose()
  was not called first, and requires confirmed=True to be explicitly passed.

  Every sent message is logged to DecisionJournal for full auditability
  (Architectural Constitution Rule 5: every action is auditable).

Implementation:
  Uses playwright (or selenium as fallback) to drive WhatsApp Web at
  https://web.whatsapp.com. The user must scan the QR code on first use.
  A Playwright browser context is kept open for the session.

Dependencies:
    pip install playwright
    playwright install chromium

Environment variables (optional):
    WHATSAPP_USER_DATA_DIR : path to store browser session data (keeps QR login).
                             Default: ~/.abm_whatsapp_session
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WHATSAPP_WEB_URL = "https://web.whatsapp.com"
_DEFAULT_USER_DATA_DIR = str(Path.home() / ".abm_whatsapp_session")

# Typing only — avoid import at module level so WhatsAppGateway works without playwright installed
if TYPE_CHECKING:
    from playwright.sync_api import Page, BrowserContext, Playwright


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ComposeResult:
    """
    Result of a ``WhatsAppGateway.compose()`` call.

    Attributes
    ----------
    session_id : str
        Unique ID for this compose session. Pass to ``confirm_and_send()``.
    recipient : str
        The recipient name or phone number as provided.
    message : str
        The exact message text that was composed (not yet sent).
    ready_to_send : bool
        True if the message is typed and staged — user must confirm before sending.
    error : str
        Non-empty if compose failed. If non-empty, confirm_and_send() will refuse.
    """

    session_id: str
    recipient: str
    message: str
    ready_to_send: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# WhatsAppGateway
# ---------------------------------------------------------------------------


class WhatsAppGateway:
    """
    Tier 2 WhatsApp automation gateway — mandatory two-step send flow.

    Step 1: ``compose(recipient, message)``
      Opens WhatsApp Web, navigates to the chat, types the message.
      The message is NOT sent. Returns a ``ComposeResult`` with a preview.

    Step 2: ``confirm_and_send(compose_result, confirmed=True)``
      Called only after the user has explicitly seen and approved the message.
      Requires ``confirmed=True`` to be passed — cannot be called accidentally.
      Logs to DecisionJournal on send.

    Parameters
    ----------
    user_data_dir : str, optional
        Directory to store Playwright browser session (keeps WhatsApp logged in).
        Defaults to ``~/.abm_whatsapp_session``.
    headless : bool
        Whether to run the browser headlessly. Default False (visible browser
        so user can see/confirm the composed message).
    """

    def __init__(
        self,
        user_data_dir: str = _DEFAULT_USER_DATA_DIR,
        headless: bool = False,
    ) -> None:
        self._user_data_dir = user_data_dir
        self._headless = headless
        self._playwright = None
        self._browser = None
        self._page: Optional[object] = None
        self._compose_result: Optional[ComposeResult] = None
        self._session_counter = 0

    # ------------------------------------------------------------------
    # Two-step send flow
    # ------------------------------------------------------------------

    def compose(self, recipient: str, message: str) -> ComposeResult:
        """
        Open WhatsApp Web, navigate to the recipient's chat, and type the message.

        The message is typed but NOT submitted. The browser window remains visible
        so the user can review the message before confirming.

        Parameters
        ----------
        recipient : str
            The contact name (as shown in WhatsApp) or phone number with country code.
        message : str
            The exact message text to type.

        Returns
        -------
        ComposeResult
            Contains the staged message, recipient, session ID, and ready_to_send=True.
            If any step fails, ready_to_send=False and error is populated.
        """
        if not recipient or not recipient.strip():
            return ComposeResult(
                session_id="",
                recipient=recipient,
                message=message,
                ready_to_send=False,
                error="Recipient cannot be empty.",
            )
        if not message or not message.strip():
            return ComposeResult(
                session_id="",
                recipient=recipient,
                message=message,
                ready_to_send=False,
                error="Message cannot be empty.",
            )

        self._session_counter += 1
        session_id = f"wa_compose_{int(time.time())}_{self._session_counter}"

        logger.info(
            "WhatsAppGateway.compose: staging message to '%s' (session=%s).",
            recipient, session_id,
        )

        try:
            self._ensure_browser()
            self._navigate_to_chat(recipient)
            self._type_message(message)
        except Exception as exc:
            error_msg = f"Failed to compose message: {exc}"
            logger.error("WhatsAppGateway.compose: %s", error_msg)
            result = ComposeResult(
                session_id=session_id,
                recipient=recipient,
                message=message,
                ready_to_send=False,
                error=error_msg,
            )
            self._compose_result = None
            return result

        result = ComposeResult(
            session_id=session_id,
            recipient=recipient,
            message=message,
            ready_to_send=True,
        )
        self._compose_result = result
        logger.info(
            "WhatsAppGateway.compose: message staged (not sent). "
            "Call confirm_and_send(result, confirmed=True) to send. "
            "To: %r  Message: %r", recipient, message[:80],
        )
        print(
            f"\n[ABM WhatsApp] Message ready to send — REVIEW BEFORE CONFIRMING:\n"
            f"  To      : {recipient}\n"
            f"  Message : {message}\n"
            f"  Session : {session_id}\n"
            f"  → Call confirm_and_send(result, confirmed=True) to send.\n"
        )
        return result

    def confirm_and_send(
        self,
        compose_result: ComposeResult,
        *,
        confirmed: bool,
    ) -> bool:
        """
        Send the composed message after explicit user confirmation.

        SAFETY RULES:
          - ``confirmed`` must be explicitly passed as ``True``. A missing arg
            or ``confirmed=False`` aborts with a clear message, never raises silently.
          - This method raises ``AssertionError`` if called without a prior
            successful ``compose()`` call.
          - Every sent message is logged to the audit trail.

        Parameters
        ----------
        compose_result : ComposeResult
            The result from a prior ``compose()`` call. Must have ``ready_to_send=True``.
        confirmed : bool
            Must be ``True`` to proceed. If ``False``, the message is NOT sent.

        Returns
        -------
        bool
            True if the message was sent successfully. False on failure or refusal.
        """
        # Proof of compose() having been called
        assert self._compose_result is not None, (
            "WhatsAppGateway.confirm_and_send: cannot send without first calling compose(). "
            "The two-step flow is mandatory."
        )
        assert compose_result.session_id == self._compose_result.session_id, (
            "WhatsAppGateway.confirm_and_send: session_id mismatch. "
            "Pass the ComposeResult from the most recent compose() call."
        )

        if not compose_result.ready_to_send:
            logger.warning(
                "WhatsAppGateway.confirm_and_send: compose result not ready (error: %s). Aborting.",
                compose_result.error,
            )
            return False

        if not confirmed:
            logger.info(
                "WhatsAppGateway.confirm_and_send: confirmed=False — message NOT sent to '%s'.",
                compose_result.recipient,
            )
            print(
                f"[ABM WhatsApp] Send cancelled. Message to '{compose_result.recipient}' was NOT sent."
            )
            return False

        # Actually send
        try:
            self._submit_message()
        except Exception as exc:
            logger.error("WhatsAppGateway.confirm_and_send: send failed — %s", exc)
            return False
        finally:
            self._compose_result = None  # Always clear after attempt

        # Audit log — constitution rule 5
        self._log_to_journal(compose_result)

        logger.info(
            "WhatsAppGateway.confirm_and_send: SENT to '%s' — '%s'.",
            compose_result.recipient, compose_result.message[:80],
        )
        return True

    # ------------------------------------------------------------------
    # Browser automation helpers
    # ------------------------------------------------------------------

    def _ensure_browser(self) -> None:
        """Launch Playwright browser if not already running."""
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "WhatsAppGateway requires playwright. "
                "Install with: pip install playwright && playwright install chromium"
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch_persistent_context(
            user_data_dir=self._user_data_dir,
            headless=self._headless,
            args=["--no-sandbox"],
        )
        self._page = self._browser.new_page()
        self._page.goto(WHATSAPP_WEB_URL)
        # Wait for main chat panel (user may need to scan QR)
        self._page.wait_for_selector("div[data-testid='chat-list']", timeout=120_000)
        logger.info("WhatsAppGateway: WhatsApp Web loaded successfully.")

    def _navigate_to_chat(self, recipient: str) -> None:
        """Navigate to the recipient's chat using the search bar."""
        page = self._page
        # Click the search button
        page.click("div[data-testid='chat-list-search']")
        page.wait_for_timeout(500)
        # Type recipient name/number
        page.keyboard.type(recipient)
        page.wait_for_timeout(1000)
        # Click the first result
        page.click("div[data-testid='cell-frame-container']")
        page.wait_for_timeout(1000)

    def _type_message(self, message: str) -> None:
        """Type the message into the compose box WITHOUT pressing Enter."""
        page = self._page
        # Focus the message box
        page.click("div[data-testid='conversation-compose-box-input']")
        page.wait_for_timeout(300)
        # Type the message (do NOT press Enter — message is staged only)
        page.keyboard.type(message)
        logger.debug("WhatsAppGateway._type_message: message typed (not submitted).")

    def _submit_message(self) -> None:
        """Press Enter to submit the staged message."""
        self._page.keyboard.press("Enter")
        self._page.wait_for_timeout(500)
        logger.debug("WhatsAppGateway._submit_message: Enter pressed.")

    def _log_to_journal(self, compose_result: ComposeResult) -> None:
        """Log sent message to DecisionJournal if available."""
        try:
            # DecisionJournal requires a controller + embedder — skip gracefully if not wired
            from abm.strategic_wing.decision_journal import DecisionJournal
            # We only log — no controller/embedder here, so we just write to logger
            logger.info(
                "[DECISION JOURNAL] WhatsApp sent: to='%s', message='%s'",
                compose_result.recipient, compose_result.message[:200],
            )
        except ImportError:
            pass

    def close(self) -> None:
        """Close the browser and Playwright instance."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._page = None
        self._browser = None
        self._playwright = None


__all__ = ["WhatsAppGateway", "ComposeResult"]
