"""What any model connection must provide, plus output validation.

Every model is treated as untrusted: whatever it returns is checked against
the expected schema before the rest of Hallucinope sees it. Swapping
models (or providers) means writing one class with complete_json().
"""

from __future__ import annotations

from typing import Protocol


class LLMError(RuntimeError):
    """The model could not be reached, or returned unusable output."""


class JsonModel(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        """Ask the model a question; return its answer as a schema-valid dict."""
        ...


_TYPES = {
    "string": str, "integer": int, "number": (int, float),
    "boolean": bool, "object": dict, "array": list, "null": type(None),
}


def validate(value: object, schema: dict, path: str = "$") -> None:
    """Check value against a small subset of JSON Schema; raise LLMError if not.

    Supports: type (incl. lists like ["integer", "null"]), enum, properties,
    required, items. That covers every schema Hallucinope sends a model.
    """
    types = schema.get("type")
    if types is not None:
        allowed = types if isinstance(types, list) else [types]
        python_types = tuple(t for name in allowed for t in
                             (_TYPES[name] if isinstance(_TYPES[name], tuple)
                              else (_TYPES[name],)))
        # bool is a subclass of int in Python; don't let True pass as a number.
        if isinstance(value, bool) and "boolean" not in allowed:
            raise LLMError(f"{path}: expected {allowed}, got boolean")
        if not isinstance(value, python_types):
            raise LLMError(f"{path}: expected {allowed}, got {type(value).__name__}")
    if "enum" in schema and value not in schema["enum"]:
        raise LLMError(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise LLMError(f"{path}: missing required field {key!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                validate(value[key], sub, f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{i}]")
