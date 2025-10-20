#!/usr/bin/env python3
"""
Emergency script to kill RxVerify servers
Use this if the normal shutdown doesn't work
"""

import psutil
import time

def kill_servers():
    """Kill all RxVerify server processes"""
    print("🚨 Emergency Server Cleanup")
    print("=" * 30)
    
    ports_to_clean = [8000, 8080]
    killed_processes = []
    
    for port in ports_to_clean:
        print(f"🔍 Checking port {port}...")
        
        for proc in psutil.process_iter():
            try:
                connections = proc.net_connections()
                if connections:
                    for conn in connections:
                        if conn.laddr.port == port:
                            pid = proc.pid
                            name = proc.name()
                            print(f"   🗑️  Killing process {name} (PID: {pid}) on port {port}")
                            
                            try:
                                proc.terminate()
                                proc.wait(timeout=3)
                                killed_processes.append(f"{name} (PID: {pid})")
                                print(f"   ✅ Process killed")
                            except psutil.TimeoutExpired:
                                print(f"   ⚠️  Process didn't stop, forcing kill...")
                                proc.kill()
                                killed_processes.append(f"{name} (PID: {pid}) - FORCED")
                                print(f"   ✅ Process force killed")
                            except Exception as e:
                                print(f"   ❌ Error killing process: {e}")
                            break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    
    if killed_processes:
        print(f"\n✅ Cleanup complete! Killed {len(killed_processes)} processes:")
        for proc in killed_processes:
            print(f"   - {proc}")
    else:
        print("\n✅ No processes found on ports 8000 or 8080")
    
    print("\n🎯 You can now start the servers again with: python3 run_servers.py")

if __name__ == "__main__":
    kill_servers()
