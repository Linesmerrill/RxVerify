#!/usr/bin/env python3
"""
Quota Management Script for RxVerify

This script helps manage OpenAI API quota usage by providing options to:
1. Disable embeddings to use fallback mode
2. Check current usage
3. Enable/disable different features to reduce API calls
"""

import os
import sys
from pathlib import Path

def set_environment_variable(key: str, value: str):
    """Set environment variable in .env file."""
    env_file = Path(".env")
    
    # Read existing .env file
    env_vars = {}
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env_vars[k] = v
    
    # Update the variable
    env_vars[key] = value
    
    # Write back to .env file
    with open(env_file, 'w') as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")
    
    print(f"✅ Set {key}={value}")

def disable_embeddings():
    """Disable embeddings to use fallback mode."""
    set_environment_variable("DISABLE_EMBEDDINGS", "true")
    print("🔧 Embeddings disabled - system will use fallback embeddings")
    print("   This will reduce API calls but may slightly reduce search quality")

def enable_embeddings():
    """Re-enable embeddings."""
    set_environment_variable("DISABLE_EMBEDDINGS", "false")
    print("✅ Embeddings enabled - system will use OpenAI API")

def use_fallback_only():
    """Use fallback embeddings only to conserve quota."""
    set_environment_variable("USE_FALLBACK_EMBEDDINGS", "true")
    print("🔧 Using fallback embeddings only to conserve API quota")

def check_current_config():
    """Check current configuration."""
    print("📊 Current Configuration:")
    print(f"   DISABLE_EMBEDDINGS: {os.getenv('DISABLE_EMBEDDINGS', 'false')}")
    print(f"   USE_FALLBACK_EMBEDDINGS: {os.getenv('USE_FALLBACK_EMBEDDINGS', 'false')}")
    print(f"   OPENAI_API_KEY: {'Set' if os.getenv('OPENAI_API_KEY') else 'Not set'}")

def show_help():
    """Show help information."""
    print("""
🚀 RxVerify Quota Management

This script helps manage OpenAI API quota usage.

Commands:
  disable     - Disable embeddings (use fallback mode)
  enable      - Re-enable embeddings
  fallback    - Use fallback embeddings only
  check       - Check current configuration
  help        - Show this help

Environment Variables:
  DISABLE_EMBEDDINGS=true     - Completely disable embeddings
  USE_FALLBACK_EMBEDDINGS=true - Use fallback embeddings only
  OPENAI_API_KEY=your_key     - Your OpenAI API key

Quota Management Tips:
  1. Use 'disable' if you've exceeded your quota
  2. Use 'fallback' to conserve quota while keeping some functionality
  3. Check your OpenAI dashboard for usage statistics
  4. Consider upgrading your OpenAI plan for higher limits

For more information about OpenAI quotas:
  https://platform.openai.com/docs/guides/rate-limits
    """)

def main():
    """Main function."""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == "disable":
        disable_embeddings()
    elif command == "enable":
        enable_embeddings()
    elif command == "fallback":
        use_fallback_only()
    elif command == "check":
        check_current_config()
    elif command == "help":
        show_help()
    else:
        print(f"❌ Unknown command: {command}")
        show_help()

if __name__ == "__main__":
    main()
