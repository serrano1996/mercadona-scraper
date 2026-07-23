from abc import ABC, abstractmethod


class SearchStrategy(ABC):
    
    @abstractmethod
    def search(self, warehouse: str) -> list[dict]:
        """Devuelve lista de productos crudos que coinciden con el término de búsqueda."""
