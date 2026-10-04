"""
abm/api/core/bus.py
===================
Decoupled, thread-safe publish/subscribe Event Bus implementation.

Constitutional compliance:
- Rule 6: Services communicate through contracts, not direct coupling.
- Rule 9: The system degrades gracefully, never catastrophically.
  Individual subscriber exceptions are isolated and logged; they never crash the bus.
- ABM_SPEC.md §2: All system events are broadcast across a centralized local
  Event Bus, allowing modules to listen and react asynchronously without
  blocking execution threads.
"""

from __future__ import annotations

import fnmatch
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from abm.api.core.interfaces import (
    Event,
    EventBusInterface,
    EventHandler,
)

logger = logging.getLogger(__name__)


@dataclass
class _Subscription:
    sub_id: str
    topic: str
    handler: EventHandler
    priority: int


class EventBus(EventBusInterface):
    """
    In-memory, thread-safe publish/subscribe Event Bus.

    Supports:
    - Synchronous (`publish`) and asynchronous (`publish_async`) dispatch
    - Topic wildcards ('*' or 'prefix.*' via fnmatchcase)
    - Handler priority ordering (higher priority invoked first)
    - Full error isolation (faulty subscribers never crash dispatch or other subscribers)
    - Clean lifecycle management (start, drain, stop)
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: dict[str, _Subscription] = {}
        self._queue: queue.Queue[Event] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the background worker thread for asynchronous event dispatch.
        Idempotent.
        """
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="abm-event-bus-worker",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info("EventBus: background worker started.")

    def stop(self, timeout: float = 2.0) -> None:
        """
        Drain pending events and stop the background worker thread.
        Idempotent.
        """
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()

        # Drain queued events before joining
        self.drain(timeout=timeout)

        worker = self._worker_thread
        if worker is not None and worker.is_alive():
            worker.join(timeout=timeout)
        self._worker_thread = None
        logger.info("EventBus: background worker stopped.")

    def drain(self, timeout: float = 2.0) -> None:
        """
        Block until all queued asynchronous events have finished processing,
        up to `timeout` seconds.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._queue.unfinished_tasks == 0:
                    return
            time.sleep(0.01)

    # ------------------------------------------------------------------
    # Subscription Management
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        handler: EventHandler,
        *,
        priority: int = 0,
    ) -> str:
        """
        Register an event handler for a topic.

        Parameters
        ----------
        topic : str
            Topic pattern (e.g. "code.changed", "task.*", "*").
        handler : EventHandler
            Callable receiving a single `Event` parameter.
        priority : int
            Invocation priority (higher executes first, default 0).

        Returns
        -------
        str
            Subscription identifier.
        """
        if not callable(handler):
            raise TypeError(f"EventBus.subscribe: handler must be callable, got {type(handler)}")

        sub_id = str(uuid.uuid4())
        subscription = _Subscription(
            sub_id=sub_id,
            topic=topic,
            handler=handler,
            priority=priority,
        )

        with self._lock:
            self._subscriptions[sub_id] = subscription

        logger.debug("EventBus: subscribed %s to '%s' (priority=%d)", sub_id, topic, priority)
        return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscription by ID.
        """
        with self._lock:
            removed = self._subscriptions.pop(subscription_id, None)
        if removed is not None:
            logger.debug("EventBus: unsubscribed %s ('%s')", subscription_id, removed.topic)
            return True
        return False

    def subscriber_count(self, topic: str | None = None) -> int:
        """
        Return the count of active subscribers, optionally matching a topic.
        """
        with self._lock:
            if topic is None:
                return len(self._subscriptions)
            return sum(1 for s in self._subscriptions.values() if self._matches(s.topic, topic))

    def clear(self) -> None:
        """
        Remove all active subscriptions.
        """
        with self._lock:
            self._subscriptions.clear()
        logger.debug("EventBus: all subscriptions cleared.")

    # ------------------------------------------------------------------
    # Publishing & Dispatch
    # ------------------------------------------------------------------

    def publish(self, event: Event) -> int:
        """
        Synchronously dispatch an event to all matching subscribers.
        Subscribers are invoked in priority order (highest first).
        Errors in individual subscribers are caught, logged, and isolated.

        Returns
        -------
        int
            Number of subscriber callbacks invoked.
        """
        if not isinstance(event, Event):
            raise TypeError(f"EventBus.publish: expected Event, got {type(event)}")

        matching = self._get_matching_subscribers(event.topic)
        return self._dispatch_to(matching, event)

    def publish_async(self, event: Event) -> None:
        """
        Enqueue an event for non-blocking asynchronous dispatch.
        Starts the worker if not already running.
        """
        if not isinstance(event, Event):
            raise TypeError(f"EventBus.publish_async: expected Event, got {type(event)}")

        with self._lock:
            if not self._running:
                self.start()
            self._queue.put(event)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _matches(self, pattern: str, topic: str) -> bool:
        """
        Check if an event topic matches a subscriber's topic pattern.
        """
        if pattern == "*" or pattern == topic:
            return True
        return fnmatch.fnmatchcase(topic, pattern)

    def _get_matching_subscribers(self, topic: str) -> list[_Subscription]:
        with self._lock:
            matching = [s for s in self._subscriptions.values() if self._matches(s.topic, topic)]
        # Sort by priority descending (higher numbers first)
        matching.sort(key=lambda s: s.priority, reverse=True)
        return matching

    def _dispatch_to(self, subscribers: list[_Subscription], event: Event) -> int:
        invoked = 0
        for sub in subscribers:
            try:
                sub.handler(event)
                invoked += 1
            except Exception as exc:
                # Constitution Rule 9: degrade gracefully, isolate errors
                logger.error(
                    "EventBus: error executing handler %r for topic '%s' (event_id=%s): %s",
                    sub.handler,
                    event.topic,
                    event.event_id,
                    exc,
                    exc_info=True,
                )
        return invoked

    def _worker_loop(self) -> None:
        """
        Background worker loop consuming async events from queue.
        """
        while not self._stop_event.is_set():
            try:
                event = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue

            try:
                matching = self._get_matching_subscribers(event.topic)
                self._dispatch_to(matching, event)
            finally:
                self._queue.task_done()
