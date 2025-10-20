#!/usr/bin/env python3
"""
RxVerify Server Manager
Starts both backend and frontend servers with proper process management
"""

import os
import sys
import time
import signal
import subprocess
import threading
import psutil
from pathlib import Path

class ServerManager:
    def __init__(self):
        self.backend_process = None
        self.frontend_process = None
        self.running = False
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"\n🛑 Received signal {signum}, shutting down...")
        self.shutdown()
        sys.exit(0)
        
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def check_venv(self):
        """Check if virtual environment is activated"""
        if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            print("❌ Virtual environment not detected!")
            print("Please activate your virtual environment first:")
            print("  source venv/bin/activate")
            print("  # or for fish shell:")
            print("  source venv/bin/activate.fish")
            return False
        return True
        
    def check_dependencies(self):
        """Check if required packages are installed"""
        try:
            import uvicorn
            import fastapi
            import psutil
            return True
        except ImportError:
            print("❌ Required packages not installed!")
            print("Please install dependencies first:")
            print("  pip install -r requirements.txt")
            return False
    
    def kill_existing_processes(self):
        """Kill any existing processes on ports 8000 and 8080"""
        print("🔍 Checking for existing processes...")
        
        # Kill processes on port 8000 (backend)
        self._kill_processes_on_port(8000, "Backend")
        
        # Kill processes on port 8080 (frontend)
        self._kill_processes_on_port(8080, "Frontend")
        
        # Give processes time to die
        time.sleep(2)
    
    def _kill_processes_on_port(self, port, service_name):
        """Kill processes running on a specific port"""
        try:
            for proc in psutil.process_iter():
                try:
                    connections = proc.net_connections()
                    if connections:
                        for conn in connections:
                            if conn.laddr.port == port:
                                print(f"   🗑️  Killing existing {service_name} process (PID: {proc.pid}) on port {port}")
                                proc.terminate()
                                try:
                                    proc.wait(timeout=3)
                                except psutil.TimeoutExpired:
                                    proc.kill()
                                break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception as e:
            print(f"   ⚠️  Warning: Could not check for existing processes: {e}")
            
    def start_backend(self):
        """Start the backend server"""
        print("🚀 Starting RxVerify Backend...")
        try:
            self.backend_process = subprocess.Popen([
                sys.executable, "-m", "uvicorn", 
                "app.main:app", "--reload", "--port", "8000"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print("✅ Backend started (PID: {})".format(self.backend_process.pid))
            return True
        except Exception as e:
            print(f"❌ Failed to start backend: {e}")
            return False
            
    def start_frontend(self):
        """Start the frontend server"""
        print("🌐 Starting RxVerify Frontend...")
        try:
            frontend_dir = Path("frontend")
            if not frontend_dir.exists():
                print("❌ Frontend directory not found!")
                return False
                
            # Use custom server that handles Socket.IO requests gracefully
            self.frontend_process = subprocess.Popen([
                sys.executable, "server.py"
            ], cwd=frontend_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print("✅ Frontend started (PID: {})".format(self.frontend_process.pid))
            return True
        except Exception as e:
            print(f"❌ Failed to start frontend: {e}")
            return False
            
    def wait_for_backend(self):
        """Wait for backend to be ready"""
        print("⏳ Waiting for backend to be ready...")
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                import requests
                response = requests.get("http://localhost:8000/health", timeout=1)
                if response.status_code == 200:
                    print("✅ Backend is ready!")
                    return True
            except:
                pass
            time.sleep(1)
            if attempt % 5 == 0:
                print(f"   Still waiting... ({attempt + 1}/{max_attempts})")
                
        print("❌ Backend failed to start within timeout")
        return False
        
    def wait_for_frontend(self):
        """Wait for frontend to be ready"""
        print("⏳ Waiting for frontend to be ready...")
        max_attempts = 10
        for attempt in range(max_attempts):
            try:
                import requests
                response = requests.get("http://localhost:8080", timeout=1)
                if response.status_code == 200:
                    print("✅ Frontend is ready!")
                    return True
            except:
                pass
            time.sleep(1)
            
        print("❌ Frontend failed to start within timeout")
        return False
        
    def start(self):
        """Start both servers"""
        print("🚀 RxVerify Server Manager")
        print("=" * 40)
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Check prerequisites
        if not self.check_venv():
            return False
        if not self.check_dependencies():
            return False
        
        # Kill any existing processes on our ports
        self.kill_existing_processes()
            
        # Start servers
        if not self.start_backend():
            return False
            
        # Wait for backend to be ready
        if not self.wait_for_backend():
            self.shutdown()
            return False
            
        if not self.start_frontend():
            self.shutdown()
            return False
            
        # Wait for frontend to be ready
        if not self.wait_for_frontend():
            self.shutdown()
            return False
            
        self.running = True
        self.show_status()
        
        # Keep running and monitor processes
        try:
            while self.running:
                time.sleep(1)
                if self.backend_process and self.backend_process.poll() is not None:
                    print("❌ Backend process died unexpectedly")
                    break
                if self.frontend_process and self.frontend_process.poll() is not None:
                    print("❌ Frontend process died unexpectedly")
                    break
        except KeyboardInterrupt:
            pass
            
        self.shutdown()
        return True
        
    def show_status(self):
        """Show server status and URLs"""
        print("\n🎉 Both servers are running successfully!")
        print("=" * 50)
        print("Backend API:  http://localhost:8000")
        print("Frontend UI:  http://localhost:8080")
        print("Health Check: http://localhost:8000/health")
        print("API Docs:    http://localhost:8000/docs")
        print("=" * 50)
        print("Press Ctrl+C to stop both servers")
        print()
        
    def shutdown(self):
        """Shutdown both servers gracefully"""
        print("🛑 Shutting down servers...")
        self.running = False
        
        # Stop backend process
        if self.backend_process:
            print("   Stopping backend...")
            try:
                self.backend_process.terminate()
                self.backend_process.wait(timeout=5)
                print("   ✅ Backend stopped gracefully")
            except subprocess.TimeoutExpired:
                print("   ⚠️  Backend didn't stop gracefully, forcing kill...")
                self.backend_process.kill()
                try:
                    self.backend_process.wait(timeout=2)
                    print("   ✅ Backend killed")
                except subprocess.TimeoutExpired:
                    print("   ❌ Failed to kill backend process")
            except Exception as e:
                print(f"   ❌ Error stopping backend: {e}")
        
        # Stop frontend process
        if self.frontend_process:
            print("   Stopping frontend...")
            try:
                self.frontend_process.terminate()
                self.frontend_process.wait(timeout=5)
                print("   ✅ Frontend stopped gracefully")
            except subprocess.TimeoutExpired:
                print("   ⚠️  Frontend didn't stop gracefully, forcing kill...")
                self.frontend_process.kill()
                try:
                    self.frontend_process.wait(timeout=2)
                    print("   ✅ Frontend killed")
                except subprocess.TimeoutExpired:
                    print("   ❌ Failed to kill frontend process")
            except Exception as e:
                print(f"   ❌ Error stopping frontend: {e}")
        
        # Final cleanup - kill any remaining processes on our ports
        print("   🧹 Final cleanup...")
        self._kill_processes_on_port(8000, "Backend")
        self._kill_processes_on_port(8080, "Frontend")
        
        print("✅ All servers stopped")

def main():
    """Main entry point"""
    manager = ServerManager()
    success = manager.start()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
