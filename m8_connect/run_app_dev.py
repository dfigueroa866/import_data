#!/usr/bin/env python3
"""
Development version of the API runner that can start without database checks
"""

import sys
import os
import logging
from pathlib import Path

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def check_environment():
    """Check if environment is properly configured."""
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found")
        print("💡 Copy .env.example to .env and configure your database")
        return False
    
    # Check if DATABASE_URL is configured
    try:
        from data_staging.config import settings
        if not settings.database_url or "your-password" in str(settings.database_url).lower():
            print("❌ DATABASE_URL not properly configured in .env")
            print("💡 Please update DATABASE_URL with your actual database credentials")
            return False
        
        print("✅ Environment configuration looks good")
        print(f"   Database type: {settings.database_type or 'auto-detected'}")
        print(f"   Upload path: {settings.upload_path}")
        return True
        
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        print("💡 Check your .env file format and values")
        return False

def main():
    """Main application entry point for development."""
    setup_logging()
    
    print("🚀 Starting M8 Connect (Development Mode)")
    print("=" * 60)
    print("⚠️  WARNING: Running in development mode without database checks")
    print("=" * 60)
    
    # Check environment
    if not check_environment():
        return 1
    
    # Start the API server without database checks
    try:
        print("\n🌐 Starting API server...")
        print("📍 API will be available at: http://localhost:8000")
        print("📚 API docs at: http://localhost:8000/docs")
        print("🔧 Development mode: Database checks disabled")
        print("\nPress CTRL+C to stop\n")
        
        # Import and run
        import uvicorn
        from data_staging.api.main import app
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            reload=False,  # Disable reload to avoid import issues
            log_level="info"
        )
        
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 