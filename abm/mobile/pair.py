import argparse
import base64
import json
import logging
import os
import sys

CONFIG_FILE = ".sync_pairing.json"

logger = logging.getLogger(__name__)

def main() -> None:
    parser = argparse.ArgumentParser(description="Pair ABM desktop with mobile node.")
    parser.add_argument("--key", required=True, help="Base64 encoded AES-256-GCM key")
    parser.add_argument("--key-id", dest="key_id", required=True, help="Key ID string")
    
    args = parser.parse_args()
    
    try:
        decoded_key = base64.b64decode(args.key)
        if len(decoded_key) != 32:
            print(f"Error: Invalid key length. Expected 32 bytes for AES-256, got {len(decoded_key)}.", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error decoding base64 key: {e}", file=sys.stderr)
        sys.exit(1)
        
    config = {
        "key": args.key,
        "key_id": args.key_id
    }
    
    # Write to project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    config_path = os.path.join(project_root, CONFIG_FILE)
    
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        print(f"Successfully paired mobile node. Key stored in {config_path}")
    except Exception as e:
        print(f"Error writing to config file {config_path}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
