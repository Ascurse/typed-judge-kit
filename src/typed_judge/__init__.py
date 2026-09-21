"""typed-judge: типизированные вопросы к модели, вердикт в коде, пороги по своим меткам."""
from importlib.metadata import version as _version

# Версия живёт только в pyproject; дубль строкой здесь уже разъезжался молча (бид jnk).
__version__ = _version("typed-judge")

from .batch import Row, run  # noqa: F401
from .questions import Answer, Choice, Noul, Score  # noqa: F401
from .verdict import Verdict, apply  # noqa: F401
