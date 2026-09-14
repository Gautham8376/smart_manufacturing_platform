import uvicorn
import os
import sys

def main():
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    
    print("=" * 70)
    print("  AERO-MES 4.0 | SMART MANUFACTURING & PRODUCTION CONTROL PLATFORM")
    print("=" * 70)
    print(f"  * Control Dashboard: http://{host}:{port}")
    print(f"  * REST API Docs:     http://{host}:{port}/docs")
    print(f"  * Real-Time Stream:  ws://{host}:{port}/ws/factory")
    print("=" * 70)
    print("  Press Ctrl+C to shutdown.")
    print("=" * 70)

    uvicorn.run("backend.main:app", host=host, port=port, reload=False, log_level="info")

if __name__ == "__main__":
    main()
