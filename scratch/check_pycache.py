import json
from abm.memory.chroma_controller import ChromaController
from abm.mobile.retention_housekeeper import COLLECTION_AMBIENT_ARCHIVE

ctrl = ChromaController(persist_directory="./memory/chroma_archive", in_memory=False)
collection = ctrl._client.get_or_create_collection(COLLECTION_AMBIENT_ARCHIVE)

results = collection.get()

# Find any __pycache__ entries
pycache_entries = []
for i, doc in enumerate(results['documents']):
    if '__pycache__' in doc:
        meta = results['metadatas'][i]
        pycache_entries.append(meta)

print(f"Found {len(pycache_entries)} __pycache__ entries.")
for meta in pycache_entries:
    print(meta)
