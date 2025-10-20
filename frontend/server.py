#!/usr/bin/env python3
"""
Custom HTTP server for RxVerify frontend with Socket.IO fallback handling
"""

import http.server
import socketserver
import json
import urllib.parse
from pathlib import Path

class RxVerifyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler that handles Socket.IO requests gracefully"""
    
    def do_GET(self):
        """Handle GET requests with Socket.IO fallback"""
        # Check if this is a Socket.IO request
        if self.path.startswith('/socket.io/'):
            self.send_socket_io_response()
            return
        
        # For all other requests, use the default handler
        super().do_GET()
    
    def send_socket_io_response(self):
        """Send a friendly response for Socket.IO requests"""
        response_data = {
            "message": "Socket.IO not configured - using REST API instead",
            "status": "ok"
        }
        
        response_json = json.dumps(response_data)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response_json)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        self.wfile.write(response_json.encode('utf-8'))
    
    def log_message(self, format, *args):
        """Custom log message format"""
        # Only log non-Socket.IO requests to reduce noise
        if not args[0].startswith('/socket.io/'):
            super().log_message(format, *args)

def run_server(port=8080):
    """Run the custom HTTP server"""
    handler = RxVerifyHTTPRequestHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"🌐 RxVerify Frontend Server running on port {port}")
        print(f"📁 Serving files from: {Path.cwd()}")
        print("🔧 Socket.IO requests will be handled gracefully")
        print("Press Ctrl+C to stop the server")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped")

if __name__ == "__main__":
    run_server()
