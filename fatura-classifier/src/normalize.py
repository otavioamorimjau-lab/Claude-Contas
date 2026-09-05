"""Normalização de descritores de lançamento de fatura.

Função pura, determinística, sem I/O. Ver spec seção 6.
"""
from __future__ import annotations

import re
import unicodedata

PREFIXOS_ADQUIRENTE = [
    "IFD*",
    "JIM.COM*",
    "PAG*",
    "MP*",
    "PICPAY*",
    "EBW*",
    "PP*",
    "SUMUP*",
    "STONE*",
    "CIELO*",
    "REDE*",
    "MERCPAGO*",
]

SUFIXOS_JURIDICOS = [" LTDA", " ME", " EIRELI", " S/A", " SA"]

_RE_PARCELA = re.compile(r"\s*PARC\s*(\d{2})/(\d{2})\s*$")
_RE_PARCELA_GRUDADA = re.compile(r"([A-Z])PARC(\d{2})/(\d{2})$")
_RE_DIGITOS_LONGOS = re.compile(r"^\d{6,}$")


def _remover_acentos(s: str) -> str:
    decomposto = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _remover_prefixo(s: str) -> str:
    for prefixo in PREFIXOS_ADQUIRENTE:
        if s.startswith(prefixo):
            return s[len(prefixo):]
    if "*" in s:
        idx = s.index("*")
        if idx <= 12:
            return s[idx + 1:]
    return s


def _remover_parcela(s: str) -> tuple[str, int | None, int | None]:
    m = _RE_PARCELA.search(s)
    if m:
        num, total = int(m.group(1)), int(m.group(2))
        return s[: m.start()], num, total
    m = _RE_PARCELA_GRUDADA.search(s)
    if m:
        num, total = int(m.group(2)), int(m.group(3))
        return s[: m.start()] + m.group(1), num, total
    return s, None, None


def _remover_digitos_longos(s: str) -> str:
    tokens = [t for t in s.split(" ") if not _RE_DIGITOS_LONGOS.match(t)]
    return " ".join(tokens)


def _colapsar_espacos(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _remover_sufixo_juridico(s: str) -> str:
    for sufixo in SUFIXOS_JURIDICOS:
        if s.endswith(sufixo):
            return s[: -len(sufixo)]
    return s


def _pipeline(descricao: str) -> tuple[str, int | None, int | None]:
    s = descricao.upper()
    s = _remover_acentos(s)
    s = _remover_prefixo(s)
    s, parcela_num, parcela_total = _remover_parcela(s)
    s = _remover_digitos_longos(s)
    s = _colapsar_espacos(s)
    s = _remover_sufixo_juridico(s)
    return s, parcela_num, parcela_total


def normalize(descricao: str) -> str:
    """Normaliza um descritor de lançamento. Pura, determinística, sem I/O."""
    return _pipeline(descricao)[0]


def extract_parcela(descricao: str) -> tuple[int, int] | None:
    """Extrai (parcela_num, parcela_total) do descritor, ou None se à vista."""
    _, num, total = _pipeline(descricao)
    if num is None:
        return None
    return num, total
