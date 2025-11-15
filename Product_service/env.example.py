"""Environment configuration template for Product Service.

Copy this file to env.py and update with your actual values.
"""

import os
from typing import Final

# Redis configuration
REDIS_HOST: Final[str] = os.getenv("REDIS_HOST", "your-redis-host.com")
REDIS_PORT: Final[int] = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD: Final[str] = os.getenv("REDIS_PASSWORD", "your-redis-password")
