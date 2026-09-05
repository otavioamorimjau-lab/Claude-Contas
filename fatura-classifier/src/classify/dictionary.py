"""Camada 1: dicionário exato. Resolve a maioria do volume."""
from __future__ import annotations

import sqlite3

from .. import db


def classificar(conn: sqlite3.Connection, descricao_norm: str) -> tuple[str, float] | None:
    row = db.dicionario_buscar(conn, descricao_norm)
    if row is None:
        return None
    db.dicionario_incrementar_ocorrencia(conn, descricao_norm)
    return row["categoria"], 1.0
