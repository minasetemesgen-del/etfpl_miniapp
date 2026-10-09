"""
Safety net for the start command.

Railway sometimes guesses `uvicorn main:app` instead of reading railway.json.
This tiny file makes BOTH of these work:
    uvicorn main:app    uvicorn server:app
"""

from server import app  # noqa: F401
