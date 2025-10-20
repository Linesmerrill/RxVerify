#!/usr/bin/env python3
"""
Start just the frontend server with Socket.IO fallback handling
"""

import sys
import os
from pathlib import Path

# Change to frontend directory
frontend_dir = Path(__file__).parent / "frontend"
os.chdir(frontend_dir)

# Import and run the custom server
from server import run_server

if __name__ == "__main__":
    run_server(port=8080)
