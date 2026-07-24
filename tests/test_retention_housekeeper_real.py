import os
import sys
import unittest
import time
import numpy as np
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.api.core.config import APIConfig
from abm.api.core.registry import ServiceRegistry
from abm.mobile.retention_housekeeper import StreamCRetentionHousekeeper

class TestRetentionHousekeeperReal(unittest.TestCase):
    def setUp(self):
        # We will use a temporary real ChromaDB to test the housekeeper
        self.persist_dir = "./memory/test_chroma_store"
        self.archive_dir = "./memory/test_chroma_archive"
        
        # Clean up any leftover test data
        if os.path.exists(self.persist_dir):
            shutil.rmtree(self.persist_dir)
        if os.path.exists(self.archive_dir):
            shutil.rmtree(self.archive_dir)
            
        self.config = APIConfig()
        self.registry = ServiceRegistry(self.config)
        
        # Override the controller to use our test directory
        from abm.memory.chroma_controller import ChromaController
        self.registry._controller = ChromaController(persist_directory=self.persist_dir, in_memory=False)
        from abm.memory.embedding_wrapper import OllamaEmbeddingWrapper
        self.registry._embedder = OllamaEmbeddingWrapper()
        
    def tearDown(self):
        self.registry.shutdown()
        if os.path.exists(self.persist_dir):
            shutil.rmtree(self.persist_dir, ignore_errors=True)
        if os.path.exists(self.archive_dir):
            shutil.rmtree(self.archive_dir, ignore_errors=True)

    def test_real_collection_does_not_throw_truth_value_error(self):
        """
        Verify that using real query results from ChromaDB containing numpy arrays
        doesn't raise 'truth value of an array with more than one element is ambiguous'
        when evaluated by the housekeeper.
        """
        col = self.registry._controller._client.get_or_create_collection("abm_ambient_telemetry")
        
        # Insert a record with a numpy array as embedding
        emb = np.array([0.1]*768)
        col.add(
            ids=["fake_id_1"],
            documents=["This is a test document"],
            metadatas=[{"epoch_timestamp": int(time.time()), "lifecycle_stage": "raw", "source_kind": "test"}],
            embeddings=[emb.tolist()]
        )
        
        # Add another with raw numpy array to simulate older chromadb behavior if it happens
        # In current chromadb versions it converts it to list, but we bypass checking to be safe.
        class FakeGetResult(dict):
            def __bool__(self):
                # Simulate the ambiguous truth value error when evaluated directly
                raise ValueError("The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()")
            
        original_get_collection = self.registry._controller.get_collection
        def fake_get_collection(name):
            collection = original_get_collection(name)
            original_get = collection.get
            
            def fake_get(*args, **kwargs):
                res = original_get(*args, **kwargs)
                fake_res = FakeGetResult(res)
                if fake_res.get("embeddings") is not None and len(fake_res.get("embeddings", [])) > 0:
                    fake_res["embeddings"] = np.array(fake_res["embeddings"])
                return fake_res
                
            collection.get = fake_get
            return collection
            
        self.registry._controller.get_collection = fake_get_collection
        
        housekeeper = StreamCRetentionHousekeeper(
            controller=self.registry._controller,
            embedder=self.registry._embedder,
            archive_persist_dir=self.archive_dir
        )
        
        # This call should not crash with a truth value ambiguity
        res = housekeeper.force_run()
        if "truth value of an array" in str(res.error):
            self.fail(f"Housekeeper crashed with ambiguous truth value error: {res.error}")

if __name__ == "__main__":
    unittest.main()
