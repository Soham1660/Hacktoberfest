"""A minimal schema toolkit: each node emits the JSON Schema Ollama uses for constrained decoding
and validates (and strips) the model's reply against the same definition."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


class SchemaError(ValueError):
    def __init__(self, message: str, path: Sequence[Any] = ()):
        super().__init__(message)
        self.message = message
        self.path = list(path)

    def pretty(self) -> str:
        where = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in self.path).lstrip(".")
        return f"✖ {self.message}" + (f"\n  → at {where}" if where else "")


def _type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


class Node:
    def json_schema(self) -> Dict[str, Any]:
        raise NotImplementedError

    def parse(self, value: Any, path: Sequence[Any] = ()) -> Any:
        raise NotImplementedError


class Str(Node):
    def __init__(self, min: Optional[int] = None, max: Optional[int] = None, required: Optional[str] = None, too_long: Optional[str] = None):
        self.min, self.max, self.required, self.too_long = min, max, required, too_long

    def json_schema(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"type": "string"}
        if self.min is not None:
            out["minLength"] = self.min
        if self.max is not None:
            out["maxLength"] = self.max
        return out

    def parse(self, value: Any, path: Sequence[Any] = ()) -> str:
        if not isinstance(value, str):
            raise SchemaError(self.required or f"Invalid input: expected string, received {_type_name(value)}", path)
        if self.min is not None and len(value) < self.min:
            raise SchemaError(f"Too small: expected string to have >={self.min} characters", path)
        if self.max is not None and len(value) > self.max:
            raise SchemaError(self.too_long or f"Too big: expected string to have <={self.max} characters", path)
        return value


class Bool(Node):
    def json_schema(self) -> Dict[str, Any]:
        return {"type": "boolean"}

    def parse(self, value: Any, path: Sequence[Any] = ()) -> bool:
        if not isinstance(value, bool):
            raise SchemaError(f"Invalid input: expected boolean, received {_type_name(value)}", path)
        return value


class Enum(Node):
    def __init__(self, values: Sequence[str]):
        self.values = list(values)

    def json_schema(self) -> Dict[str, Any]:
        return {"type": "string", "enum": self.values}

    def parse(self, value: Any, path: Sequence[Any] = ()) -> str:
        if not isinstance(value, str) or value not in self.values:
            raise SchemaError("Invalid option: expected one of " + "|".join(f'"{v}"' for v in self.values), path)
        return value


class Arr(Node):
    def __init__(self, item: Node, min: Optional[int] = None, max: Optional[int] = None):
        self.item, self.min, self.max = item, min, max

    def json_schema(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.min is not None:
            out["minItems"] = self.min
        if self.max is not None:
            out["maxItems"] = self.max
        out["type"] = "array"
        out["items"] = self.item.json_schema()
        return out

    def parse(self, value: Any, path: Sequence[Any] = ()) -> List[Any]:
        if not isinstance(value, list):
            raise SchemaError(f"Invalid input: expected array, received {_type_name(value)}", path)
        if self.min is not None and len(value) < self.min:
            raise SchemaError(f"Too small: expected array to have >={self.min} items", path)
        if self.max is not None and len(value) > self.max:
            raise SchemaError(f"Too big: expected array to have <={self.max} items", path)
        return [self.item.parse(v, [*path, i]) for i, v in enumerate(value)]


class Obj(Node):
    """Required keys only; unknown keys in a reply are dropped, like a non-strict object parser."""

    def __init__(self, fields: Dict[str, Node], optional: Sequence[str] = ()):
        self.fields, self.optional = fields, set(optional)

    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {k: v.json_schema() for k, v in self.fields.items()},
            "required": [k for k in self.fields if k not in self.optional],
            "additionalProperties": False,
        }

    def parse(self, value: Any, path: Sequence[Any] = ()) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise SchemaError(f"Invalid input: expected object, received {_type_name(value)}", path)
        out: Dict[str, Any] = {}
        for key, node in self.fields.items():
            if key not in value or (value[key] is None and key in self.optional):
                if key in self.optional:
                    continue
                # Report a missing key through the field's own type check, so its custom message applies.
                node.parse(None, [*path, key])
            out[key] = node.parse(value[key], [*path, key])
        return out


def top_level_schema(node: Node) -> Dict[str, Any]:
    """The schema document sent to Ollama: JSON Schema draft 2020-12."""
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **node.json_schema()}
