"""
app/repositories/base_repository.py
Abstract base class for the Repository pattern.
Provides generic CRUD operations for all entities.
"""
from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

# TypeVar para permitir genéricos
T = TypeVar("T")


class BaseRepository(Generic[T]):
    """
    Base repository class providing generic CRUD operations.
    All repositories should inherit from this class.
    """

    def __init__(self, db: Session, model: Type[T]):
        """
        Initialize repository with database session and model class.

        Args:
            db: SQLAlchemy Session instance
            model: The SQLAlchemy model class this repository manages
        """
        self.db = db
        self.model = model

    def create(self, obj_in: dict) -> T:
        """
        Create a new record in the database.

        Args:
            obj_in: Dictionary with model attributes

        Returns:
            The created model instance
        """
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def get_by_id(self, id: Any) -> Optional[T]:
        """
        Get a record by its primary key.

        Args:
            id: The primary key value

        Returns:
            The model instance or None if not found
        """
        return self.db.get(self.model, id)

    def get_all(self) -> List[T]:
        """
        Get all records from the table.

        Returns:
            List of all model instances
        """
        stmt = select(self.model)
        return self.db.execute(stmt).scalars().all()

    def update(self, id: Any, obj_in: dict) -> Optional[T]:
        """
        Update a record by its primary key.

        Args:
            id: The primary key value
            obj_in: Dictionary with attributes to update

        Returns:
            The updated model instance or None if not found
        """
        db_obj = self.get_by_id(id)
        if not db_obj:
            return None

        for field, value in obj_in.items():
            if hasattr(db_obj, field) and value is not None:
                setattr(db_obj, field, value)

        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def delete(self, id: Any) -> bool:
        """
        Delete a record by its primary key.

        Args:
            id: The primary key value

        Returns:
            True if deleted, False if not found
        """
        db_obj = self.get_by_id(id)
        if not db_obj:
            return False

        self.db.delete(db_obj)
        self.db.commit()
        return True

    def exists(self, id: Any) -> bool:
        """
        Check if a record exists.

        Args:
            id: The primary key value

        Returns:
            True if exists, False otherwise
        """
        return self.get_by_id(id) is not None

    def flush(self) -> None:
        """Flush pending changes to the database without committing."""
        self.db.flush()

    def commit(self) -> None:
        """Commit the current transaction."""
        self.db.commit()

    def refresh(self, obj: T) -> None:
        """Refresh an object from the database."""
        self.db.refresh(obj)
