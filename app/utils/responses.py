"""
app/utils/responses.py
======================
Módulo central de respuestas OpenAPI reutilizables para todos los routers.

IMPORTANTE: Swagger muestra "string" cuando un código de respuesta tiene solo
"description" pero no "content" con "schema". Ambos campos son obligatorios
para que Swagger renderice el ejemplo correctamente.

Uso:
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


# ── Códigos de error ──────────────────────────────────────────────────────────

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

# Sin contenido (DELETE exitoso)
R204: dict[int, Any] = {
    204: {
        "description": "Eliminado exitosamente (sin contenido)",
    }
}

# Agrupaciones comunes
COMMON: dict[int, Any] = {**R401, **R422, **R500}


# ── Helpers para códigos de éxito con ejemplo inline ─────────────────────────

def R200(example: Any, description: str = "OK") -> dict[int, Any]:
    """Respuesta 200 con ejemplo de objeto."""
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
    """Respuesta 200 con ejemplo de lista."""
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
    """Respuesta 200 con ejemplo de lista de strings."""
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


def R201(example: Any, description: str = "Creado exitosamente") -> dict[int, Any]:
    """Respuesta 201 con ejemplo."""
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


def R202(example: Any, description: str = "Aceptado") -> dict[int, Any]:
    """Respuesta 202 con ejemplo."""
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