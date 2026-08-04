from abc import ABC, abstractmethod
from memory.memory_manager import MemoryManager


class BaseAgent(ABC):

    def __init__(self):
        self.memory = MemoryManager()

    @abstractmethod
    def run(self, *args, **kwargs):
        pass

    def log(self, message):
        print(f"[{self.__class__.__name__}] {message}")