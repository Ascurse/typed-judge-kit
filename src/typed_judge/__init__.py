"""typed-judge: типизированные вопросы к модели, вердикт в коде, пороги по своим меткам."""
__version__ = "0.1.0"

from .batch import Row, run  # noqa: F401
from .questions import Answer, Choice, Noul, Score  # noqa: F401
from .verdict import Verdict, apply  # noqa: F401
