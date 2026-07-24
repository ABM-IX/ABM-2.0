import os
import sys

# Setup paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from abm.api.core.config import APIConfig
from abm.api.core.registry import ServiceRegistry
from abm.mobile.retention_housekeeper import StreamCRetentionHousekeeper
import logging

logging.basicConfig(level=logging.DEBUG)

def main():
    config = APIConfig()
    registry = ServiceRegistry(config)
    registry.boot()
    
    try:
        print("Running retention housekeeper...")
        housekeeper = StreamCRetentionHousekeeper(
            controller=registry.controller,
            embedder=registry.embedder,
        )
        
        # force run
        res = housekeeper.force_run()
        print("Result:", res)
    finally:
        registry.shutdown()

if __name__ == "__main__":
    main()
