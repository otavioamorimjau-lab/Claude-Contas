"""Cascata de classificação. Para em quem responder primeiro.

Nunca consulta uma camada superior para um lançamento que uma inferior já
resolveu (spec seção 8).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .. import db
from . import dictionary, fuzzy

NAO_CLASSIFICADO = "nao_classificado"


@dataclass
class Classificacao:
    categoria: str | None
    origem: str  # dicionario|fuzzy|cnae|llm|manual|nao_classificado
    confianca: float | None


def classificar(conn: sqlite3.Connection, descricao_norm: str) -> Classificacao:
    hit = dictionary.classificar(conn, descricao_norm)
    if hit is not None:
        categoria, confianca = hit
        return Classificacao(categoria=categoria, origem="dicionario", confianca=confianca)

    hit = fuzzy.classificar(conn, descricao_norm)
    if hit is not None:
        categoria, confianca = hit
        db.dicionario_inserir_automatico(conn, descricao_norm, categoria, origem="fuzzy", confianca=confianca)
        return Classificacao(categoria=categoria, origem="fuzzy", confianca=confianca)

    # Camada 3 (CNAE/Open Finance) e camada 4 (LLM) exigem integrações ainda
    # não conectadas (spec seções 8 e 10) - o lançamento fica pendente para
    # `fatura review`.
    return Classificacao(categoria=None, origem=NAO_CLASSIFICADO, confianca=None)
