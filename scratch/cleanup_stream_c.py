from abm.memory.chroma_controller import ChromaController, COLLECTION_AMBIENT_TELEMETRY
from abm.api.core.config import APIConfig

def main():
    config = APIConfig()
    controller = ChromaController(persist_directory=config.chroma_persist_directory)
    collection = controller.get_collection(COLLECTION_AMBIENT_TELEMETRY)
    
    # We query to find the IDs of all documents matching the criteria
    # Chroma doesn't have an easy "delete by exact metadata match" without IDs in older versions, 
    # but we can fetch them first.
    all_data = collection.get(include=["metadatas"])
    
    ids_to_delete = []
    if all_data and all_data.get("ids") and all_data.get("metadatas"):
        ids = all_data["ids"]
        metadatas = all_data["metadatas"]
        
        for i, meta in enumerate(metadatas):
            # Check for hallucination loop artifacts
            if meta.get("source_kind") == "chat_history" or meta.get("source_path") == "console_interaction":
                ids_to_delete.append(ids[i])
                
    if ids_to_delete:
        print(f"Found {len(ids_to_delete)} corrupted chat_history entries in Stream C. Deleting...")
        collection.delete(ids=ids_to_delete)
        print("Deletion complete.")
    else:
        print("No corrupted chat_history entries found.")

if __name__ == "__main__":
    main()
