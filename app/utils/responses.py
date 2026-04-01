"""
app/utils/responses.py
======================
Core module of reusable OpenAPI responses for all routers.

IMPORTANT: Swagger shows "string" when a response code has only
"description" but no "content" with "schema". Both fields are required
for Swagger to render the example correctly.

Usage:
    from app.utils.responses import R200, R201, R202, R204, R401, R404, R422, R500, COMMON

    @router.post("/", responses={**R201, **COMMON})
    @router.get("/", responses={**R200_list(ClientResponse), **COMMON})
    @router.delete("/", responses={**R204, **R404, **COMMON})
"""
from __future__ import annotations
from typing import Any


# ── Schemas de error base ─────────────────────────────────────────────────────

_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {"anyOf": [{"type": "string"}, {"type": "array"}]}
    },
}

_VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "loc":  {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
                    "msg":  {"type": "string"},
                    "type": {"type": "string"},
                },
            },
        }
    },
}


# ── Error codes ─────────────────────────────────────────────────────────────

R401: dict[int, Any] = {
    401: {
        "description": "API Key inválida o ausente",
        "content": {
            "application/json": {
                "schema": _ERROR_SCHEMA,
                "example": {"detail": "Invalid or missing API Key"},
            }
        },
    }
}

R404: dict[int, Any] = {
    404: {
        "description": "Recurso no encontrado",
        "content": {
            "application/json": {
                "schema": _ERROR_SCHEMA,
                "example": {"detail": "El recurso solicitado no existe."},
            }
        },
    }
}

R422: dict[int, Any] = {
    422: {
        "description": "Error de validación en el payload",
        "content": {
            "application/json": {
                "schema": _VALIDATION_SCHEMA,
                "example": {
                    "detail": [
                        {
                            "loc": ["body", "campo_invalido"],
                            "msg": "Extra inputs are not permitted",
                            "type": "extra_forbidden",
                        }
                    ]
                },
            }
        },
    }
}

R500: dict[int, Any] = {
    500: {
        "description": "Error interno del servidor",
        "content": {
            "application/json": {
                "schema": _ERROR_SCHEMA,
                "example": {"detail": "Internal server error"},
            }
        },
    }
}

# No content (successful DELETE)
R204: dict[int, Any] = {
    204: {
        "description": "Eliminado exitosamente (sin contenido)",
    }
}

# Common groupings
COMMON: dict[int, Any] = {**R401, **R422, **R500}


# ── Helpers for success status codes with inline example ───────────────────

def R200(example: Any, description: str = "OK") -> dict[int, Any]:
    """200 response with example object."""
    return {
        200: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"type": "object"},
                    "example": example,
                }
            },
        }
    }


def R200_list(example: list[Any], description: str = "OK") -> dict[int, Any]:
    """200 response with example list."""
    return {
        200: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"type": "array", "items": {"type": "object"}},
                    "example": example,
                }
            },
        }
    }


def R200_str_list(example: list[str], description: str = "OK") -> dict[int, Any]:
    """200 response with example list of strings."""
    return {
        200: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"type": "array", "items": {"type": "string"}},
                    "example": example,
                }
            },
        }
    }


def R201(example: Any, description: str = "Created successfully") -> dict[int, Any]:
    """201 response with example."""
    return {
        201: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"type": "object"},
                    "example": example,
                }
            },
        }
    }


def R202(example: Any, description: str = "Accepted") -> dict[int, Any]:
    """202 response with example."""
    return {
        202: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"type": "object"},
                    "example": example,
                }
            },
        }
    }