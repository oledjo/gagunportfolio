import uvicorn
import os
import sys

if __name__ == "__main__":
    # Get port from environment variable (for production) or default to 8000
    port = int(os.getenv("PORT", 8000))
    # Only enable reload in development (when PORT is not set)
    reload = os.getenv("PORT") is None
    
    # Ensure logs go to stdout
    uvicorn.run(
        "api:app", 
        host="0.0.0.0", 
        port=port, 
        reload=reload,
        log_config=None,  # Use default logging config
        log_level="info"
    )

