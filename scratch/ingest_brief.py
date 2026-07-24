import os
import sys

# Add the project root to sys.path so we can import from abm
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from abm.memory.chroma_controller import ChromaController, COLLECTION_COGNITIVE_IDENTITY, SCHEMA_COGNITIVE_IDENTITY
from abm.memory.embedding_wrapper import OllamaEmbeddingWrapper
from abm.memory.chunking import chunk_stream_b_technical_mastery

def main():
    print("Ingesting PROJECT_BRIEF.md into Stream D...")
    controller = ChromaController(persist_directory="memory/chroma_store")
    embedder = OllamaEmbeddingWrapper()

    files_to_ingest = [
        "project_context/PROJECT_BRIEF.md"
    ]

    # Clean existing PROJECT_BRIEF chunks
    collection = controller.get_collection(COLLECTION_COGNITIVE_IDENTITY)
    all_data = collection.get()
    ids_to_delete = [doc_id for doc_id in all_data["ids"] if "PROJECT_BRIEF.md" in doc_id]
    if ids_to_delete:
        print(f"Deleting {len(ids_to_delete)} old chunks...")
        collection.delete(ids=ids_to_delete)

    for filepath in files_to_ingest:
        print(f"Reading {filepath}...")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = chunk_stream_b_technical_mastery(content)
        print(f"Split into {len(chunks)} chunks.")

        filename = os.path.basename(filepath)
        for i, chunk_text in enumerate(chunks):
            doc_id = f"identity_{filename}_{i}"
            print(f"Embedding and inserting {doc_id}...")
            embedding = embedder.embed(chunk_text)
            controller.add_document(
                collection_name=COLLECTION_COGNITIVE_IDENTITY,
                doc_id=doc_id,
                text=chunk_text,
                metadata=SCHEMA_COGNITIVE_IDENTITY.copy(),
                embedding=embedding
            )

    print("Ingestion complete.")

if __name__ == "__main__":
    main()
