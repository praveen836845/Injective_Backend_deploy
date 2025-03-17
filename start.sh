#!/bin/bash

# Start agent_server.py in the background
python3 agent_server.py &

# Wait for a few seconds to ensure the server is up (optional)
sleep 5

# Start script.py
python3 script.py
