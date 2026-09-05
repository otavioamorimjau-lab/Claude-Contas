"""Interface comum aos extratores de fatura."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from pathlib import Path


class ExtracaoInconsistenteError(Exception):
    """Levantada quando a soma dos lançamentos não bate com o total impresso.

    O pipeline nunca deve continuar depois disso: um extrator que erra
    silenciosamente contamina todo o histórico.
    """


@dataclass
class LancamentoBruto:
    data: date
    descricao_original: str
    valor_centavos: int
    portador: str | None
    cartao_final: str | None


@dataclass
class FaturaExtraida:
    emissor: str
    vencimento: date
    fechamento: date
    total_centavos: int  # o total IMPRESSO, lido do PDF
    lancamentos: list[LancamentoBruto]


class Extractor(Protocol):
    def extract(self, pdf_path: Path) -> FaturaExtraida: ...
