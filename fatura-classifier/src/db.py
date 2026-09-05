"""Schema e acesso ao SQLite. Toda escrita no banco passa por aqui."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import date
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fatura (
    id                INTEGER PRIMARY KEY,
    emissor           TEXT NOT NULL,
    vencimento        TEXT NOT NULL,
    fechamento        TEXT NOT NULL,
    total_centavos    INTEGER NOT NULL,
    arquivo_hash      TEXT NOT NULL UNIQUE,
    processado_em     TEXT NOT NULL,
    UNIQUE(emissor, vencimento)
);

CREATE TABLE IF NOT EXISTS compra (
    id                     INTEGER PRIMARY KEY,
    descricao_norm         TEXT NOT NULL,
    valor_parcela_centavos INTEGER NOT NULL,
    parcela_total          INTEGER NOT NULL,
    valor_total_centavos   INTEGER NOT NULL,
    primeira_competencia   TEXT,
    categoria              TEXT
);

CREATE TABLE IF NOT EXISTS lancamento (
    id                  INTEGER PRIMARY KEY,
    fatura_id           INTEGER NOT NULL REFERENCES fatura(id),
    data                TEXT NOT NULL,
    descricao_original  TEXT NOT NULL,
    descricao_norm      TEXT NOT NULL,
    valor_centavos      INTEGER NOT NULL,
    portador            TEXT,
    cartao_final        TEXT,
    parcela_num         INTEGER,
    parcela_total       INTEGER,
    compra_id           INTEGER REFERENCES compra(id),
    categoria           TEXT,
    origem_categoria    TEXT NOT NULL,
    confianca           REAL,
    hash_dedupe         TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dicionario (
    descricao_norm    TEXT PRIMARY KEY,
    categoria         TEXT NOT NULL,
    origem            TEXT NOT NULL,
    confirmado        INTEGER NOT NULL DEFAULT 0,
    ocorrencias       INTEGER NOT NULL DEFAULT 1,
    cnpj              TEXT,
    cnae              TEXT,
    razao_social      TEXT,
    observacao        TEXT,
    atualizado_em     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lanc_norm ON lancamento(descricao_norm);
CREATE INDEX IF NOT EXISTS idx_lanc_fatura ON lancamento(fatura_id);
"""


def conectar(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def criar_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _agora_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def computar_arquivo_hash(pdf_path: Path) -> str:
    return hashlib.sha256(pdf_path.read_bytes()).hexdigest()


def computar_hash_dedupe(
    emissor: str,
    data_lanc: date,
    descricao_original: str,
    valor_centavos: int,
    cartao_final: str | None,
) -> str:
    chave = f"{emissor}|{data_lanc.isoformat()}|{descricao_original}|{valor_centavos}|{cartao_final or ''}"
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def buscar_fatura_por_hash(conn: sqlite3.Connection, arquivo_hash: str) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM fatura WHERE arquivo_hash = ?", (arquivo_hash,))
    return cur.fetchone()


def inserir_fatura(
    conn: sqlite3.Connection,
    emissor: str,
    vencimento: date,
    fechamento: date,
    total_centavos: int,
    arquivo_hash: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO fatura (emissor, vencimento, fechamento, total_centavos, arquivo_hash, processado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (emissor, vencimento.isoformat(), fechamento.isoformat(), total_centavos, arquivo_hash, _agora_iso()),
    )
    conn.commit()
    return cur.lastrowid


def buscar_ou_criar_compra(
    conn: sqlite3.Connection,
    descricao_norm: str,
    valor_parcela_centavos: int,
    parcela_total: int,
    primeira_competencia: str | None,
) -> int:
    cur = conn.execute(
        """
        SELECT id FROM compra
        WHERE descricao_norm = ? AND valor_parcela_centavos = ? AND parcela_total = ?
        """,
        (descricao_norm, valor_parcela_centavos, parcela_total),
    )
    row = cur.fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        """
        INSERT INTO compra (descricao_norm, valor_parcela_centavos, parcela_total,
                             valor_total_centavos, primeira_competencia, categoria)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (
            descricao_norm,
            valor_parcela_centavos,
            parcela_total,
            valor_parcela_centavos * parcela_total,
            primeira_competencia,
        ),
    )
    conn.commit()
    return cur.lastrowid


def inserir_lancamento(
    conn: sqlite3.Connection,
    *,
    fatura_id: int,
    data_lanc: date,
    descricao_original: str,
    descricao_norm: str,
    valor_centavos: int,
    portador: str | None,
    cartao_final: str | None,
    parcela_num: int | None,
    parcela_total: int | None,
    compra_id: int | None,
    categoria: str | None,
    origem_categoria: str,
    confianca: float | None,
) -> bool:
    """Insere o lançamento. Retorna False (sem inserir) se já existir (idempotência)."""
    hash_dedupe = computar_hash_dedupe(
        _emissor_da_fatura(conn, fatura_id), data_lanc, descricao_original, valor_centavos, cartao_final
    )
    try:
        conn.execute(
            """
            INSERT INTO lancamento (
                fatura_id, data, descricao_original, descricao_norm, valor_centavos,
                portador, cartao_final, parcela_num, parcela_total, compra_id,
                categoria, origem_categoria, confianca, hash_dedupe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fatura_id,
                data_lanc.isoformat(),
                descricao_original,
                descricao_norm,
                valor_centavos,
                portador,
                cartao_final,
                parcela_num,
                parcela_total,
                compra_id,
                categoria,
                origem_categoria,
                confianca,
                hash_dedupe,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False


def _emissor_da_fatura(conn: sqlite3.Connection, fatura_id: int) -> str:
    row = conn.execute("SELECT emissor FROM fatura WHERE id = ?", (fatura_id,)).fetchone()
    return row["emissor"] if row else ""


def dicionario_buscar(conn: sqlite3.Connection, descricao_norm: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM dicionario WHERE descricao_norm = ?", (descricao_norm,)
    ).fetchone()


def dicionario_incrementar_ocorrencia(conn: sqlite3.Connection, descricao_norm: str) -> None:
    conn.execute(
        "UPDATE dicionario SET ocorrencias = ocorrencias + 1, atualizado_em = ? WHERE descricao_norm = ?",
        (_agora_iso(), descricao_norm),
    )
    conn.commit()


def dicionario_inserir_automatico(
    conn: sqlite3.Connection,
    descricao_norm: str,
    categoria: str,
    origem: str,
    confianca: float | None = None,
) -> None:
    """Grava uma entrada nova vinda das camadas 2/3/4. Nunca sobrescreve uma existente
    (se já existe, é confirmada ou já resolveria via camada 1 antes de chegar aqui)."""
    conn.execute(
        """
        INSERT INTO dicionario (descricao_norm, categoria, origem, confirmado, ocorrencias, atualizado_em)
        VALUES (?, ?, ?, 0, 1, ?)
        ON CONFLICT(descricao_norm) DO NOTHING
        """,
        (descricao_norm, categoria, origem, _agora_iso()),
    )
    conn.commit()


def dicionario_set_manual(conn: sqlite3.Connection, descricao_norm: str, categoria: str) -> None:
    """Correção manual do usuário. Sempre confirmado=1. Nunca é sobrescrita depois."""
    conn.execute(
        """
        INSERT INTO dicionario (descricao_norm, categoria, origem, confirmado, ocorrencias, atualizado_em)
        VALUES (?, ?, 'manual', 1, 1, ?)
        ON CONFLICT(descricao_norm) DO UPDATE SET
            categoria = excluded.categoria,
            origem = 'manual',
            confirmado = 1,
            atualizado_em = excluded.atualizado_em
        """,
        (descricao_norm, categoria, _agora_iso()),
    )
    conn.commit()


def dicionario_listar_chaves(conn: sqlite3.Connection) -> list[str]:
    return [row["descricao_norm"] for row in conn.execute("SELECT descricao_norm FROM dicionario")]


def carregar_seed(conn: sqlite3.Connection, seed_path: Path) -> int:
    """Carrega data/seed_dicionario.json. Idempotente: nunca sobrescreve entrada existente."""
    import json

    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    inseridos = 0
    for descricao_norm, info in seed.items():
        existente = dicionario_buscar(conn, descricao_norm)
        if existente is not None:
            continue
        conn.execute(
            """
            INSERT INTO dicionario (descricao_norm, categoria, origem, confirmado, ocorrencias, atualizado_em)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                descricao_norm,
                info["categoria"],
                info.get("origem", "seed"),
                1 if info.get("confirmado", 1) else 0,
                _agora_iso(),
            ),
        )
        inseridos += 1
    conn.commit()
    return inseridos
