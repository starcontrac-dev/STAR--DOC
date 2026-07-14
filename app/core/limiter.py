from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

# Derivar URL de Redis para la DB 1
if settings.REDIS_PASSWORD:
    redis_rate_limit_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"
else:
    redis_rate_limit_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"

import sys
is_testing = "pytest" in sys.modules or "unittest" in sys.modules

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=redis_rate_limit_url,
    storage_options={"socket_connect_timeout": 5},
    default_limits=["200/minute"],
    strategy="fixed-window",
    enabled=not is_testing
)
