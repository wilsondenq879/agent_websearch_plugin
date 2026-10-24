"""Agent-independent local browser search. No Open WebUI imports."""
__version__ = "0.1.0"

from .client import Client

__all__ = ["Client", "__version__"]
