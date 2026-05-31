"""Lightweight query views over KiCad OOP model objects."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Generic, TypeAlias, TypeVar, cast, overload

from ._api_markers import public_api

T = TypeVar("T")
KindFilter: TypeAlias = type | tuple[type, ...] | str | None
_MISSING = object()


@public_api
class KiCadObjectCollection(Sequence[T], Generic[T]):
    """Read-only live view over a model-owned object collection."""

    def __init__(
        self,
        provider: Callable[[], Iterable[T]],
        *,
        owner: object | None = None,
    ) -> None:
        self._provider = provider
        self._owner = owner

    def _items(self) -> list[T]:
        return list(self._provider())

    def __iter__(self) -> Iterator[T]:
        return iter(self._items())

    def __len__(self) -> int:
        return len(self._items())

    @overload
    def __getitem__(self, index: int) -> T:
        ...

    @overload
    def __getitem__(self, index: slice) -> list[T]:
        ...

    def __getitem__(self, index: int | slice) -> T | list[T]:
        return self._items()[index]

    def __repr__(self) -> str:
        owner = type(self._owner).__name__ if self._owner is not None else None
        return f"{type(self).__name__}(owner={owner!r}, count={len(self)})"

    def to_list(self) -> list[T]:
        """Materialize the current view as a list."""
        return self._items()

    def count(
        self,
        value: object = _MISSING,
        **attrs,
    ) -> int:
        """Count items matching an optional type/name and exact attributes."""
        if value is _MISSING:
            return sum(1 for _ in self.where(None, **attrs))
        if _is_kind_filter(value):
            return sum(1 for _ in self.where(cast(KindFilter, value), **attrs))
        if attrs:
            raise TypeError("attribute filters require a type, class-name, or omitted count value")
        return self._items().count(cast(T, value))

    def first(
        self,
        kind: KindFilter = None,
        **attrs,
    ) -> T | None:
        """Return the first matching item, or None."""
        for item in self.where(kind, **attrs):
            return item
        return None

    def of_type(self, kind: type | tuple[type, ...] | str) -> "KiCadObjectCollection[T]":
        """Return a live view filtered by class or class name."""
        return self.where(kind)

    def where(
        self,
        kind: KindFilter = None,
        **attrs,
    ) -> "KiCadObjectCollection[T]":
        """Return a live view filtered by type/name and exact attributes."""

        def provider() -> Iterator[T]:
            for item in self:
                if not _matches_kind(item, kind):
                    continue
                if not _matches_attrs(item, attrs):
                    continue
                yield item

        return KiCadObjectCollection(provider, owner=self._owner)

    def _read_only(self, *args, **kwargs) -> None:
        raise TypeError(
            "KiCadObjectCollection is a read-only view; use the owning model "
            "methods such as add_object() or remove_object()."
        )

    append = _read_only
    clear = _read_only
    extend = _read_only
    insert = _read_only
    pop = _read_only
    remove = _read_only
    reverse = _read_only
    sort = _read_only

    def __setitem__(self, index, value) -> None:
        self._read_only()

    def __delitem__(self, index) -> None:
        self._read_only()


def _matches_kind(
    item: object,
    kind: KindFilter,
) -> bool:
    if kind is None:
        return True
    if isinstance(kind, str):
        return type(item).__name__ == kind
    return isinstance(item, kind)


def _is_kind_filter(value: object) -> bool:
    return isinstance(value, (str, type)) or (
        isinstance(value, tuple) and all(isinstance(part, type) for part in value)
    )


def _matches_attrs(item: object, attrs: dict[str, object]) -> bool:
    for name, expected in attrs.items():
        if getattr(item, name, None) != expected:
            return False
    return True


__all__ = ["KiCadObjectCollection"]
