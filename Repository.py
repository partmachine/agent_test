from abc import ABC, abstractmethod

class Repository(ABC):
    """
    Abstract base class for a repository.
    """

    @abstractmethod
    def create(self, repo_name, description="", private=False, base_directory=None, sdk_version="7.0.400"):
        """
        create a .NET Core repository.
        Args:
            item: The item to add.
        """
        pass

    