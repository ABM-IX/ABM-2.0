import sys

with open('interfaces.md', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

content = content.replace('device_source always "dynamic_mobile_node"', 'device_source defaults to "desktop_workspace" but respects constructor arg')

target2 = '3. Retention Housekeeper Loop'
grace = 'Gracefully handles `SIGINT` (Ctrl+C) and `SIGTERM` by signaling an internal threading event, shutting down the HTTP server, and executing a clean `ServiceRegistry.shutdown()`.'
grace_rep = '4. Background Ollama subprocess (if `ollama serve` is not already running), including `phi3:mini` pre-warming.\n\nGracefully handles `SIGINT` (Ctrl+C) and `SIGTERM` by signaling an internal threading event, shutting down the HTTP server, and executing a clean `ServiceRegistry.shutdown()`. Also cleanly terminates the Ollama subprocess if it was started by the launcher.'
content = content.replace(grace, grace_rep)

with open('interfaces.md', 'w', encoding='utf-8') as f:
    f.write(content)
