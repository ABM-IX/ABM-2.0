"""
abm/strategic_wing/decision_journal.py
======================================
Internal decision tracking journal for Phase v0.5.
A durable record of strategic decisions written into Stream D.
"""

import time
import uuid

from abm.memory.chroma_controller import (
    COLLECTION_COGNITIVE_IDENTITY,
    SCHEMA_COGNITIVE_IDENTITY,
    ChromaController,
)
from abm.memory.embedding_wrapper import OllamaEmbeddingWrapper


class DecisionJournal:
    """
    Logs strategic corporate decisions into Stream D (abm_cognitive_identity).
    
    Adheres strictly to the existing metadata schema:
    {"owner": "ABM", "target_entity": "FirstMinds", "volatility": "immutable"}
    """

    def __init__(
        self, controller: ChromaController, embedder: OllamaEmbeddingWrapper
    ) -> None:
        self.controller = controller
        self.embedder = embedder

    def log_decision(
        self, what_decided: str, why_decided: str, epoch: int | None = None
    ) -> str:
        """
        Records a decision into the vector memory.
        
        Because the metadata schema is immutable and strict, the decision payload
        is formatted directly into the document text.
        
        :param what_decided: Summary of the strategic decision made.
        :param why_decided: Rationale and underlying corporate philosophy.
        :param epoch: Optional unix timestamp. Defaults to current time.
        :return: The generated document ID.
        """
        ts = epoch if epoch is not None else int(time.time())
        doc_id = f"DECISION_{ts}_{uuid.uuid4().hex[:8]}"

        # Format the text payload
        text_payload = (
            f"STRATEGIC DECISION RECORD\n"
            f"TIMESTAMP: {ts}\n"
            f"DECISION: {what_decided}\n"
            f"REASONING: {why_decided}\n"
        )

        # Generate embedding
        embedding = self.embedder.embed(text_payload)

        # Write to Stream D using exact strict metadata
        self.controller.add_document(
            collection_name=COLLECTION_COGNITIVE_IDENTITY,
            doc_id=doc_id,
            text=text_payload,
            metadata=dict(SCHEMA_COGNITIVE_IDENTITY),  # Copy the strict dictionary
            embedding=embedding,
        )

        return doc_id
