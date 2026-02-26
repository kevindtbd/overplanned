"""
MockSASession -- test helper that wraps AsyncMock(spec=AsyncSession)
with Prisma-like ergonomics using a call queue dispatcher.

Prevents 3x verbosity explosion from raw SA mock chains.

Usage:
    session = MockSASession()
    session.returns_one(trip_obj)             # next execute -> scalars().first()
    session.returns_many([trip1, trip2])       # next execute -> scalars().all()
    session.returns_none()                     # next execute -> scalars().first() = None
    session.returns_rowcount(1)               # next execute -> .rowcount
    session.returns_row(invite_token, trip)   # next execute -> .first() = (token, trip)

Chain for sequential calls:
    session.returns_one(candidate).returns_none()

Assert via:
    session.mock.execute.assert_called_once()
    session.mock.commit.assert_called_once()
"""

from __future__ import annotations

from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock

_UNSET = object()  # sentinel for distinguishing None from unset


class _ScalarsResult:
    """Mock for result.scalars() return value."""

    def __init__(self, items: list[Any] | None, single: Any | None = None):
        self._items = items
        self._single = single

    def all(self) -> list[Any]:
        return self._items if self._items is not None else []

    def first(self) -> Any | None:
        if self._single is not None:
            return self._single
        if self._items:
            return self._items[0]
        return None


class _MappingRow:
    """Mock for a raw SQL row with ._mapping attribute (used by dict(r._mapping))."""

    def __init__(self, data: dict):
        self._mapping = data


class _ExecuteResult:
    """Mock for session.execute() return value."""

    def __init__(
        self,
        *,
        scalars_items: list[Any] | None = None,
        scalars_single: Any | None = None,
        rowcount: int | None = None,
        row: tuple | None = None,
        rows: list[tuple] | None = None,
        scalar_value: Any = _UNSET,
    ):
        self._scalars_items = scalars_items
        self._scalars_single = scalars_single
        self._rowcount = rowcount
        self._row = row
        self._rows = rows
        self._scalar_value = scalar_value

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._scalars_items, self._scalars_single)

    @property
    def rowcount(self) -> int:
        return self._rowcount if self._rowcount is not None else 0

    def scalar(self) -> Any:
        """Return a single scalar value (e.g. from SELECT COUNT(*))."""
        if self._scalar_value is not _UNSET:
            return self._scalar_value
        return None

    def first(self) -> tuple | None:
        return self._row

    def all(self) -> list[tuple]:
        return self._rows if self._rows is not None else []

    def fetchall(self) -> list[tuple]:
        return self.all()

    def mappings(self) -> _MappingsResult:
        return _MappingsResult(self._rows)


class _MappingsResult:
    """Mock for result.mappings()."""

    def __init__(self, rows: list | None):
        self._rows = rows or []

    def all(self) -> list:
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class MockSASession:
    """
    Test helper wrapping AsyncMock(spec=AsyncSession) with a call queue
    dispatcher for sequential return values.
    """

    def __init__(self) -> None:
        self._queue: deque[_ExecuteResult] = deque()
        self._get_queue: deque[Any] = deque()
        self.mock = AsyncMock()
        self.mock.commit = AsyncMock()
        self.mock.rollback = AsyncMock()
        self.mock.close = AsyncMock()
        self.mock.flush = AsyncMock()
        self.mock.add = MagicMock()
        self.mock.refresh = AsyncMock()

        async def _execute_side_effect(*args, **kwargs):
            if self._queue:
                return self._queue.popleft()
            # Default: empty result
            return _ExecuteResult()

        async def _get_side_effect(*args, **kwargs):
            if self._get_queue:
                return self._get_queue.popleft()
            return None

        self.mock.execute = AsyncMock(side_effect=_execute_side_effect)
        self.mock.get = AsyncMock(side_effect=_get_side_effect)

    def returns_one(self, obj: Any) -> MockSASession:
        """Next execute() call returns this single object via scalars().first()."""
        self._queue.append(_ExecuteResult(scalars_single=obj))
        return self

    def returns_many(self, items: list[Any]) -> MockSASession:
        """Next execute() call returns these items via scalars().all()."""
        self._queue.append(_ExecuteResult(scalars_items=items))
        return self

    def returns_none(self) -> MockSASession:
        """Next execute() call returns None via scalars().first()."""
        self._queue.append(_ExecuteResult())
        return self

    def returns_rowcount(self, count: int) -> MockSASession:
        """Next execute() call returns this rowcount."""
        self._queue.append(_ExecuteResult(rowcount=count))
        return self

    def returns_row(self, *values: Any) -> MockSASession:
        """Next execute() call returns a row tuple via .first()."""
        self._queue.append(_ExecuteResult(row=values))
        return self

    def returns_rows(self, rows: list[tuple]) -> MockSASession:
        """Next execute() call returns multiple row tuples via .all()."""
        self._queue.append(_ExecuteResult(rows=rows))
        return self

    def returns_mappings(self, rows: list[dict]) -> MockSASession:
        """Next execute() call returns mapping rows."""
        self._queue.append(_ExecuteResult(rows=rows))
        return self

    def returns_scalar(self, value: Any) -> MockSASession:
        """Next execute() call returns a scalar value via .scalar()."""
        self._queue.append(_ExecuteResult(scalar_value=value))
        return self

    def returns_mapping_rows(self, rows: list[dict]) -> MockSASession:
        """Next execute() call returns rows with ._mapping attr (for raw SQL).

        Usage for routers that do: [dict(r._mapping) for r in result.fetchall()]
        """
        mapping_rows = [_MappingRow(r) for r in rows]
        self._queue.append(_ExecuteResult(rows=mapping_rows))
        return self

    def returns_get(self, obj: Any) -> MockSASession:
        """Next db.get() call returns this object."""
        self._get_queue.append(obj)
        return self
