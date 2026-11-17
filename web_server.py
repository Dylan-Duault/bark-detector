"""Compatibility launcher for the FastAPI dashboard."""
import sys
from app.cli import main

if __name__ == "__main__":
    main(["web", *sys.argv[1:]])
