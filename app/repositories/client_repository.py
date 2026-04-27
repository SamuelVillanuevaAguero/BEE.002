"""
app/repositories/client_repository.py
Repository pattern implementation for Client model.
Centralizes all database operations for client-related entities.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client import Client
from .base_repository import BaseRepository


class ClientRepository(BaseRepository[Client]):
    """
    Repository for Client model.
    Provides specialized query methods for client operations.
    """

    def __init__(self, db: Session):
        """Initialize ClientRepository with Client model."""
        super().__init__(db, Client)

    def list_all(self) -> List[Client]:
        """
        List all clients ordered by name.

        Returns:
            List of clients sorted by client_name
        """
        stmt = select(Client).order_by(Client.client_name)
        return self.db.execute(stmt).scalars().all()

    def get_by_name(self, name: str) -> Optional[Client]:
        """
        Get a client by its name.

        Args:
            name: The client name

        Returns:
            The Client instance or None if not found
        """
        stmt = select(Client).where(Client.client_name == name)
        return self.db.execute(stmt).scalars().first()

    def get_by_freshdesk_id(self, id_freshdesk: str) -> Optional[Client]:
        """
        Get a client by its Freshdesk ID.

        Args:
            id_freshdesk: The Freshdesk ID

        Returns:
            The Client instance or None if not found
        """
        stmt = select(Client).where(Client.id_freshdesk == id_freshdesk)
        return self.db.execute(stmt).scalars().first()

    def get_by_beecker_id(self, id_beecker: str) -> Optional[Client]:
        """
        Get a client by its Beecker ID.

        Args:
            id_beecker: The Beecker ID

        Returns:
            The Client instance or None if not found
        """
        stmt = select(Client).where(Client.id_beecker == id_beecker)
        return self.db.execute(stmt).scalars().first()
