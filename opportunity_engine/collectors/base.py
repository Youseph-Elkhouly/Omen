from typing import Protocol
from ..models import RawItem
class Collector(Protocol):
    def fetch(self) -> list[RawItem]: ...
