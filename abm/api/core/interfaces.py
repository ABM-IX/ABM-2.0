"""
abm/api/core/interfaces.py
==========================
Abstract service interfaces for the ABM 2.0 architecture.

These interfaces define the contracts for core system dependencies
(Vector Store, Embedder, Model Gateway). By relying on these interfaces
instead of concrete implementations, the ServiceRegistry enables
swappable components (e.g. replacing ChromaDB with another vector
store) without breaking downstream clients.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
import time
from typing import TYPE_CHECKING, Any, Callable
import uuid

if TYPE_CHECKING:
    # Use TYPE_CHECKING to avoid circular imports, as the concrete
    # implementations will import these interfaces to inherit from them.
    from abm.memory.chroma_controller import QueryResult
    from abm.orchestrator.model_gateway import GenerationResponse


EventHandler = Callable[["Event"], Any]


class SystemTopic:
    """
    Standard system event topics per ABM_SPEC.md.
    """
    CODE_CHANGED = "code.changed"
    CONTEXT_STREAM_QUARANTINED = "context.stream.quarantined"
    HARDWARE_SHIFT_DETECTED = "hardware.shift.detected"
    TASK_DISPATCHED = "task.dispatched"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TELEMETRY_INGESTED = "telemetry.ingested"
    SYSTEM_BOOT = "system.boot"
    SYSTEM_SHUTDOWN = "system.shutdown"


@dataclass(frozen=True)
class Event:
    """
    Immutable system event model.
    """
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)


class VectorStoreInterface(abc.ABC):
    """
    Abstract interface for vector database operations.
    """

    @abc.abstractmethod
    def get_collection(self, collection_name: str) -> Any:
        """
        Return the handle for the given collection name.
        """
        pass

    @abc.abstractmethod
    def add_document(
        self,
        collection_name: str,
        doc_id: str,
        text: str,
        metadata: dict[str, Any],
        embedding: list[float],
    ) -> None:
        """
        Add a single document with a pre-computed embedding to the collection.
        """
        pass

    @abc.abstractmethod
    def query_collection(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int = 5,
    ) -> QueryResult:
        """
        Perform a nearest-neighbour vector query against the collection.
        """
        pass


class EmbedderInterface(abc.ABC):
    """
    Abstract interface for text embedding generation.
    """

    @abc.abstractmethod
    def health_check(self) -> bool:
        """
        Verify that the embedding provider is reachable.
        """
        pass

    @abc.abstractmethod
    def embed(self, text: str) -> list[float]:
        """
        Generate a single embedding vector for the given text.
        """
        pass

    @abc.abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for a list of texts.
        """
        pass


class ModelGatewayInterface(abc.ABC):
    """
    Abstract interface for the text-generation model gateway.
    """

    @abc.abstractmethod
    def generate(self, prompt: str, *, max_tokens: int = 0) -> GenerationResponse:
        """
        Send a prompt to the model and return the generated text.

        Parameters
        ----------
        prompt : str
            The prompt text.
        max_tokens : int
            Maximum tokens to generate. 0 means no cap (model default).
        """
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        """
        Check whether the model gateway is reachable and ready.
        """
        pass


class EventBusInterface(abc.ABC):
    """
    Abstract interface for the decoupled publish/subscribe Event Bus subsystem.
    """

    @abc.abstractmethod
    def subscribe(
        self,
        topic: str,
        handler: EventHandler,
        *,
        priority: int = 0,
    ) -> str:
        """
        Subscribe a callback handler to an event topic.

        Parameters
        ----------
        topic : str
            Event topic string to listen to (e.g. "code.changed", "task.*", "*").
        handler : EventHandler
            Callable receiving a single `Event` object.
        priority : int
            Execution priority (higher executes earlier, default 0).

        Returns
        -------
        str
            A unique subscription ID for unsubscribing.
        """
        pass

    @abc.abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe a registered handler using its subscription ID.

        Returns
        -------
        bool
            True if the subscription was found and removed, False otherwise.
        """
        pass

    @abc.abstractmethod
    def publish(self, event: Event) -> int:
        """
        Synchronously dispatch an event to all matching subscribers.

        Parameters
        ----------
        event : Event
            The event to dispatch.

        Returns
        -------
        int
            The number of matching subscriber handlers invoked.
        """
        pass

    @abc.abstractmethod
    def publish_async(self, event: Event) -> None:
        """
        Asynchronously dispatch an event without blocking the caller.

        Parameters
        ----------
        event : Event
            The event to dispatch.
        """
        pass

    @abc.abstractmethod
    def start(self) -> None:
        """
        Start the event bus background workers.
        """
        pass

    @abc.abstractmethod
    def stop(self, timeout: float = 2.0) -> None:
        """
        Drain pending events and stop all background workers.
        """
        pass

    @abc.abstractmethod
    def drain(self, timeout: float = 2.0) -> None:
        """
        Block until all queued asynchronous events have finished processing.
        """
        pass

    @abc.abstractmethod
    def subscriber_count(self, topic: str | None = None) -> int:
        """
        Return the count of active subscribers, optionally filtered by topic.
        """
        pass

    @abc.abstractmethod
    def clear(self) -> None:
        """
        Remove all active subscriptions.
        """
        pass
