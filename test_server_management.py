#!/usr/bin/env python3
"""
Test script for server management improvements
"""

import subprocess
import time
import requests
import psutil
from pathlib import Path

def check_port(port):
    """Check if a port is in use"""
    for proc in psutil.process_iter():
        try:
            connections = proc.net_connections()
            if connections:
                for conn in connections:
                    if conn.laddr.port == port:
                        return True, proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False, None

def test_server_management():
    """Test the improved server management"""
    print("🧪 Testing Server Management Improvements")
    print("=" * 50)
    
    # Check initial state
    print("1. Checking initial port status...")
    backend_in_use, backend_pid = check_port(8000)
    frontend_in_use, frontend_pid = check_port(8080)
    
    print(f"   Port 8000 (Backend): {'In use' if backend_in_use else 'Free'} {f'(PID: {backend_pid})' if backend_pid else ''}")
    print(f"   Port 8080 (Frontend): {'In use' if frontend_in_use else 'Free'} {f'(PID: {frontend_pid})' if frontend_pid else ''}")
    
    if backend_in_use or frontend_in_use:
        print("   ⚠️  Some ports are in use - the server manager should clean these up")
    else:
        print("   ✅ All ports are free")
    
    print("\n2. Testing server startup...")
    print("   Run: python3 run_servers.py")
    print("   Then press Ctrl+C to test shutdown")
    print("   Both servers should stop cleanly")
    
    print("\n3. Testing automatic cleanup...")
    print("   If you run the server manager again, it should:")
    print("   - Kill any existing processes on ports 8000 and 8080")
    print("   - Start fresh servers")
    print("   - Show proper PID information")
    
    print("\n4. Expected improvements:")
    print("   ✅ Automatic cleanup of existing processes")
    print("   ✅ Proper PID display for both servers")
    print("   ✅ Graceful shutdown of both servers")
    print("   ✅ Force kill if graceful shutdown fails")
    print("   ✅ Final cleanup to ensure ports are free")

if __name__ == "__main__":
    test_server_management()
