"""
Beecker platform implementations and exceptions.

Provides platform-specific clients (Cloud, Hub) and a platform map for dynamic selection.
"""

from .base_platform import (
    BasePlatform,
    PlatformError,
    PlatformAuthError,
    PlatformConnectionError,
    PlatformNotFoundError,
    PlatformAPIError,
)
from .cloud_platform import CloudPlatform
from .hub_platform import HubPlatform


# Mapping of platform names to their implementation classes
PLATFORM_MAP = {
    "cloud": CloudPlatform,
    "hub": HubPlatform,
}

__all__ = [
    "BasePlatform",
    "CloudPlatform",
    "HubPlatform",
    "PLATFORM_MAP",
    "PlatformError",
    "PlatformAuthError",
    "PlatformConnectionError",
    "PlatformNotFoundError",
    "PlatformAPIError",
]
