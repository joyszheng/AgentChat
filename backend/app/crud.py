"""Compatibility facade for domain-specific repository modules.

New code should import from ``app.repositories`` directly when it is already
working in a single domain. Existing routers and services can keep using this
module while the codebase is migrated gradually.
"""

from . import models, schemas  # noqa: F401
from .repositories.chat import *  # noqa: F401,F403
from .repositories.documents import *  # noqa: F401,F403
from .repositories.settings import *  # noqa: F401,F403
from .repositories.tasks import *  # noqa: F401,F403
from .repositories.users import *  # noqa: F401,F403
