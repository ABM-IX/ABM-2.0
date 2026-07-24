import os
import sys

# Setup paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from abm.api.core.config import APIConfig
from abm.api.core.registry import ServiceRegistry
from abm.mobile.retention_housekeeper import StreamCRetentionHousekeeper
import logging
import numpy as np
import time

logging.basicConfig(level=logging.DEBUG)

def main():
    config = APIConfig()
    registry = ServiceRegistry(config)
    registry.boot()
    
    try:
        print("Inserting fake data into abm_ambient_telemetry with numpy arrays...")
        col = registry.controller.get_collection("abm_ambient_telemetry")
        
        # Insert a record with a numpy array as embedding
        emb = np.array([0.1]*768)
        col.add(
            ids=["fake_id_1"],
            documents=["This is a test document"],
            metadatas=[{"epoch_timestamp": int(time.time()) - 40 * 86400, "lifecycle_stage": "summarized", "source_kind": "test"}],
            embeddings=[emb]
        )
        
        print("Running retention housekeeper...")
        housekeeper = StreamCRetentionHousekeeper(
            controller=registry.controller,
            embedder=registry.embedder,
        )
        
        # force run
        res = housekeeper.force_run()
        print("Result:", res)
    finally:
        # Cleanup
        try:
            col.delete(ids=["fake_id_1"])
        except:
            pass
        registry.shutdown()

if __name__ == "__main__":
    main()
