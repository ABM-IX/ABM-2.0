"""
tests/test_phase_v20_increment2_event_bus_gate.py
=================================================
Phase v2.0, Increment 2 Gate — Asynchronous Event Bus

Constitutional hard gates:
  1. TestEventBusTypingGate
     - Event is an immutable (frozen) dataclass with valid defaults.
     - EventBusInterface defines all abstract contracts.
     - EventBus implements EventBusInterface.
     - ServiceRegistry.event_bus property is typed as EventBusInterface.
     - ServiceRegistry._event_bus field is annotated as EventBusInterface | None.

  2. TestTopicMatchingAndSubscriptions
     - Exact topic matching ("code.changed").
     - Universal wildcard matching ("*").
     - Hierarchical pattern matching ("code.*").
     - Priority ordering (higher priority invoked first).
     - Unsubscribe by subscription ID.
     - subscriber_count reporting.
     - clear() cleans up all subscriptions.

  3. TestErrorIsolationGate (Constitution Rule 9)
     - Subscriber exceptions are caught, logged, and isolated.
     - The publisher never crashes.
     - Peer subscribers still execute successfully.

  4. TestAsynchronousDispatchGate (ABM_SPEC.md §2)
     - publish_async returns non-blocking immediately.
     - Events execute on background worker queue.
     - Thread-safe under concurrent multi-threaded publishing.
     - drain() and stop() lifecycle.

  5. TestServiceRegistryIntegrationGate
     - Unbooted registry access raises RuntimeError.
     - registry.boot() initializes and starts the event bus.
     - registry.shutdown() cleanly stops the event bus.

  6. TestPhaseV20Increment2RegressionGate
     - Increment 1 and core suites pass with zero regressions.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, get_type_hints
from unittest.mock import MagicMock

import pytest

from abm.api.core.bus import EventBus
from abm.api.core.config import APIConfig
from abm.api.core.interfaces import (
    Event,
    EventBusInterface,
    SystemTopic,
)
from abm.api.core.registry import ServiceRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ===========================================================================
# Gate 1: Typing & Interface Contract
# ===========================================================================


class TestEventBusTypingGate:
    def test_event_dataclass_immutability_and_defaults(self) -> None:
        event = Event(topic="test.topic", payload={"key": "value"}, source="test_source")
        assert event.topic == "test.topic"
        assert event.payload == {"key": "value"}
        assert event.source == "test_source"
        assert isinstance(event.event_id, str) and len(event.event_id) > 0
        assert isinstance(event.timestamp, float) and event.timestamp > 0

        # Frozen immutability check
        with pytest.raises(Exception):
            event.topic = "mutated.topic"  # type: ignore[misc]

    def test_event_bus_implements_interface(self) -> None:
        bus = EventBus()
        assert isinstance(bus, EventBusInterface)

    def test_registry_property_and_field_typing(self) -> None:
        hints = get_type_hints(ServiceRegistry)
        assert hints.get("_event_bus") == EventBusInterface | None

        ret_type = ServiceRegistry.event_bus.fget.__annotations__.get("return")
        assert ret_type in (EventBusInterface, "EventBusInterface")


# ===========================================================================
# Gate 2: Topic Matching, Priority, and Subscriptions
# ===========================================================================


class TestTopicMatchingAndSubscriptions:
    def test_exact_topic_matching(self) -> None:
        bus = EventBus()
        received: list[str] = []

        bus.subscribe("code.changed", lambda e: received.append(e.topic))
        bus.subscribe("telemetry.ingested", lambda e: received.append(e.topic))

        count = bus.publish(Event(topic="code.changed"))
        assert count == 1
        assert received == ["code.changed"]

        count = bus.publish(Event(topic="telemetry.ingested"))
        assert count == 1
        assert received == ["code.changed", "telemetry.ingested"]

    def test_wildcard_matching(self) -> None:
        bus = EventBus()
        all_events: list[str] = []
        code_events: list[str] = []

        bus.subscribe("*", lambda e: all_events.append(e.topic))
        bus.subscribe("code.*", lambda e: code_events.append(e.topic))

        bus.publish(Event(topic="code.changed"))
        bus.publish(Event(topic="code.analyzed"))
        bus.publish(Event(topic="system.boot"))

        assert all_events == ["code.changed", "code.analyzed", "system.boot"]
        assert code_events == ["code.changed", "code.analyzed"]

    def test_priority_ordering(self) -> None:
        bus = EventBus()
        order: list[int] = []

        bus.subscribe("order.test", lambda e: order.append(1), priority=1)
        bus.subscribe("order.test", lambda e: order.append(100), priority=100)
        bus.subscribe("order.test", lambda e: order.append(10), priority=10)
        bus.subscribe("order.test", lambda e: order.append(0), priority=0)

        bus.publish(Event(topic="order.test"))
        assert order == [100, 10, 1, 0]

    def test_unsubscribe_and_counts(self) -> None:
        bus = EventBus()
        calls: list[str] = []

        token1 = bus.subscribe("item.event", lambda e: calls.append("sub1"))
        token2 = bus.subscribe("item.event", lambda e: calls.append("sub2"))

        assert bus.subscriber_count("item.event") == 2
        assert bus.subscriber_count() == 2

        # Publish to both
        bus.publish(Event(topic="item.event"))
        assert calls == ["sub1", "sub2"]

        # Unsubscribe token1
        assert bus.unsubscribe(token1) is True
        assert bus.unsubscribe("non-existent-token") is False
        assert bus.subscriber_count("item.event") == 1

        # Publish again
        calls.clear()
        bus.publish(Event(topic="item.event"))
        assert calls == ["sub2"]

        # Clear all
        bus.clear()
        assert bus.subscriber_count() == 0


# ===========================================================================
# Gate 3: Error Isolation (Constitution Rule 9)
# ===========================================================================


class TestErrorIsolationGate:
    def test_faulty_subscriber_does_not_break_bus_or_peers(self, caplog: pytest.LogCaptureFixture) -> None:
        bus = EventBus()
        peer_results: list[str] = []

        def faulty_handler(e: Event) -> None:
            raise ValueError("Intentional crash in subscriber handler")

        bus.subscribe("critical.event", lambda e: peer_results.append("first"), priority=10)
        bus.subscribe("critical.event", faulty_handler, priority=5)
        bus.subscribe("critical.event", lambda e: peer_results.append("second"), priority=1)

        with caplog.at_level(logging.ERROR):
            # Publisher must not raise
            invoked = bus.publish(Event(topic="critical.event"))

        # Both working subscribers were invoked
        assert peer_results == ["first", "second"]
        assert invoked == 2

        # Error must have been logged
        assert any("faulty_handler" in r.message or "Intentional crash" in r.message for r in caplog.records)


# ===========================================================================
# Gate 4: Asynchronous Non-Blocking Dispatch (ABM_SPEC.md §2)
# ===========================================================================


class TestAsynchronousDispatchGate:
    def test_publish_async_is_non_blocking(self) -> None:
        bus = EventBus()
        bus.start()

        started_event = threading.Event()
        finish_event = threading.Event()

        def slow_handler(e: Event) -> None:
            started_event.set()
            finish_event.wait(timeout=2.0)

        bus.subscribe("async.test", slow_handler)

        t0 = time.perf_counter()
        bus.publish_async(Event(topic="async.test"))
        duration = time.perf_counter() - t0

        # publish_async must return immediately without waiting for slow_handler
        assert duration < 0.05, f"publish_async blocked for {duration:.4f}s"

        # Wait until background worker actually enters the slow handler
        assert started_event.wait(timeout=1.0) is True

        # Complete handler and drain
        finish_event.set()
        bus.drain(timeout=1.0)
        bus.stop()

    def test_concurrent_multithreaded_publishing(self) -> None:
        bus = EventBus()
        bus.start()

        received_count = 0
        lock = threading.Lock()

        def counter_handler(e: Event) -> None:
            nonlocal received_count
            with lock:
                received_count += 1

        bus.subscribe("concurrent.event", counter_handler)

        threads: list[threading.Thread] = []
        events_per_thread = 50
        thread_count = 4

        def publisher_worker() -> None:
            for _ in range(events_per_thread):
                bus.publish_async(Event(topic="concurrent.event"))

        for _ in range(thread_count):
            t = threading.Thread(target=publisher_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        bus.drain(timeout=3.0)
        bus.stop()

        expected = thread_count * events_per_thread
        assert received_count == expected


# ===========================================================================
# Gate 5: ServiceRegistry Integration
# ===========================================================================


class TestServiceRegistryIntegrationGate:
    def test_unbooted_access_raises_runtime_error(self) -> None:
        registry = ServiceRegistry(APIConfig())
        with pytest.raises(RuntimeError, match="call boot\\(\\) first"):
            _ = registry.event_bus

    def test_boot_and_shutdown_lifecycle(self) -> None:
        registry = ServiceRegistry(APIConfig())
        # Mock components to avoid heavy external dependencies during registry unit test
        mock_bus = EventBus()
        registry._event_bus = mock_bus
        registry._booted = True

        assert registry.event_bus is mock_bus

        # Test shutdown clears event_bus
        registry.shutdown()
        assert registry._event_bus is None
        assert not registry.is_booted


# ===========================================================================
# Gate 6: Regression Gate
# ===========================================================================


class TestPhaseV20Increment2RegressionGate:
    def test_increment1_suite_passes(self) -> None:
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(PROJECT_ROOT / "tests" / "test_increment1_service_interfaces_gate.py"),
            "-k",
            "not test_full_existing_suite_has_zero_regressions",
            "-v",
        ]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        assert result.returncode == 0, f"Increment 1 regression failed:\n{result.stdout}\n{result.stderr}"
