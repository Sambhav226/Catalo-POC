from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


DType = Literal["string", "int", "float", "bool", "enum"]


class SchemaField(BaseModel):
    name: str
    dtype: DType = "string"
    unit: str | None = None
    enum_values: list[Any] | None = None
    required: bool = False
    description: str | None = None
    examples: list[Any] | None = None
    min: float | None = None
    max: float | None = None
    aliases: list[str] = Field(default_factory=list)


class CategorySchema(BaseModel):
    category: str
    version: str = "1.0.0"
    fields: list[SchemaField]
    induced_from: list[str] = Field(default_factory=list)

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def by_name(self) -> dict[str, SchemaField]:
        return {f.name: f for f in self.fields}
