"""Detecção e agrupamento de parcelas (spec seção 7).

compra_key = (descricao_norm, valor_parcela_centavos, parcela_total).
Uma compra parcelada é 1 linha em `compra` + N lançamentos apontando pra ela.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from . import db


def vincular_parcela(
    conn: sqlite3.Connection,
    *,
    descricao_norm: str,
    valor_parcela_centavos: int,
    parcela_total: int,
    competencia_fatura: date,
) -> int:
    """Busca ou cria a `compra` correspondente e retorna seu id."""
    primeira_competencia = competencia_fatura.strftime("%Y-%m")
    return db.buscar_ou_criar_compra(
        conn,
        descricao_norm=descricao_norm,
        valor_parcela_centavos=valor_parcela_centavos,
        parcela_total=parcela_total,
        primeira_competencia=primeira_competencia,
    )


def compromisso_futuro_centavos(conn: sqlite3.Connection) -> int:
    """Soma de (parcelas_restantes * valor_parcela) para todas as compras em aberto.

    parcelas_restantes é calculado a partir da maior parcela_num já lançada
    para cada compra: parcela_total - max(parcela_num).
    """
    linhas = conn.execute(
        """
        SELECT c.id, c.valor_parcela_centavos, c.parcela_total, MAX(l.parcela_num) AS max_num
        FROM compra c
        JOIN lancamento l ON l.compra_id = c.id
        GROUP BY c.id
        """
    ).fetchall()
    total = 0
    for row in linhas:
        restantes = row["parcela_total"] - row["max_num"]
        if restantes > 0:
            total += restantes * row["valor_parcela_centavos"]
    return total
