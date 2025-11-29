import uvicorn
import sys

if __name__ == "__main__":
    # Ensure logs go to stdout
    uvicorn.run(
        "api:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_config=None,  # Use default logging config
        log_level="info"
    )

