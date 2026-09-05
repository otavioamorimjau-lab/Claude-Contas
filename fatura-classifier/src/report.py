"""Saídas: resumo por categoria/portador e relatório de parcelas."""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

from . import installments


def resumo_por_categoria(conn: sqlite3.Connection, competencia: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT l.categoria, SUM(l.valor_centavos) AS total_centavos, COUNT(*) AS qtd
        FROM lancamento l
        JOIN fatura f ON f.id = l.fatura_id
        WHERE strftime('%Y-%m', f.vencimento) = ? AND l.valor_centavos > 0
        GROUP BY l.categoria
        ORDER BY total_centavos DESC
        """,
        (competencia,),
    ).fetchall()


def resumo_por_portador(conn: sqlite3.Connection, competencia: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT l.portador, SUM(l.valor_centavos) AS total_centavos, COUNT(*) AS qtd
        FROM lancamento l
        JOIN fatura f ON f.id = l.fatura_id
        WHERE strftime('%Y-%m', f.vencimento) = ? AND l.valor_centavos > 0
        GROUP BY l.portador
        ORDER BY total_centavos DESC
        """,
        (competencia,),
    ).fetchall()


def relatorio_parcelas(conn: sqlite3.Connection) -> list[dict]:
    linhas = conn.execute(
        """
        SELECT c.id, c.descricao_norm, c.valor_parcela_centavos, c.parcela_total,
               c.valor_total_centavos, MAX(l.parcela_num) AS max_num
        FROM compra c
        JOIN lancamento l ON l.compra_id = c.id
        GROUP BY c.id
        ORDER BY c.descricao_norm
        """
    ).fetchall()
    saida = []
    for row in linhas:
        restantes = row["parcela_total"] - row["max_num"]
        saida.append(
            {
                "descricao_norm": row["descricao_norm"],
                "parcela_atual": row["max_num"],
                "parcela_total": row["parcela_total"],
                "parcelas_restantes": restantes,
                "valor_parcela_centavos": row["valor_parcela_centavos"],
                "compromisso_futuro_centavos": max(restantes, 0) * row["valor_parcela_centavos"],
            }
        )
    return saida


def exportar_csv(conn: sqlite3.Connection, competencia: str, destino: Path) -> int:
    linhas = conn.execute(
        """
        SELECT l.data, l.descricao_original, l.descricao_norm, l.valor_centavos,
               l.portador, l.cartao_final, l.categoria, l.origem_categoria
        FROM lancamento l
        JOIN fatura f ON f.id = l.fatura_id
        WHERE strftime('%Y-%m', f.vencimento) = ?
        ORDER BY l.data
        """,
        (competencia,),
    ).fetchall()
    with open(destino, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["data", "descricao_original", "descricao_norm", "valor_centavos", "portador", "cartao_final", "categoria", "origem_categoria"]
        )
        for row in linhas:
            writer.writerow(list(row))
    return len(linhas)
