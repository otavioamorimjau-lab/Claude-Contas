"""Camada 2: similaridade contra as chaves do dicionário.

Só roda se a camada 1 (exata) falhou. O limiar é alto de propósito: a faixa
do meio vai para revisão humana em vez de decisão automática, porque
descritores truncados de estabelecimentos diferentes podem colidir.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from .. import db

LIMIAR_AUTOACEITA = 90
LIMIAR_REVISAO = 75


@dataclass
class SugestaoFuzzy:
    descricao_norm_sugerida: str
    categoria: str
    score: int


def melhor_match(conn: sqlite3.Connection, descricao_norm: str) -> SugestaoFuzzy | None:
    chaves = db.dicionario_listar_chaves(conn)
    if not chaves:
        return None
    resultado = process.extractOne(descricao_norm, chaves, scorer=fuzz.token_sort_ratio)
    if resultado is None:
        return None
    chave_sugerida, score, _ = resultado
    row = db.dicionario_buscar(conn, chave_sugerida)
    return SugestaoFuzzy(descricao_norm_sugerida=chave_sugerida, categoria=row["categoria"], score=round(score))


def classificar(conn: sqlite3.Connection, descricao_norm: str) -> tuple[str, float] | None:
    """Retorna (categoria, confianca) só quando o score >= LIMIAR_AUTOACEITA.
    Entre LIMIAR_REVISAO e LIMIAR_AUTOACEITA, não decide sozinho: quem chama
    deve usar melhor_match() para oferecer a sugestão em `review`."""
    sugestao = melhor_match(conn, descricao_norm)
    if sugestao is None or sugestao.score < LIMIAR_AUTOACEITA:
        return None
    return sugestao.categoria, sugestao.score / 100
