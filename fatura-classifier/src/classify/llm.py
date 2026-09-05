"""Camada 4: LLM, último recurso. Única camada com chamada de rede.

Ver spec seção 8. Agrupa em lote todos os descritores desconhecidos da
fatura numa única chamada, passa a lista fechada de categorias e exige
JSON estrito. Ainda não implementada: pelas fases 1-6, mede-se primeiro
quanto volume sobra sem classificação depois das camadas 1 e 2.
"""
from __future__ import annotations

from dataclasses import dataclass

PROMPT_TEMPLATE = """\
Você classifica descritores de fatura de cartão de crédito brasileiro.
Contexto: portador em Jaú/SP. Descritores vêm truncados pela bandeira.
Categorias permitidas (use exatamente estas strings): {categorias}
Responda APENAS um array JSON, sem markdown, no formato:
[{{"descricao": "...", "categoria": "...", "confianca": 0.0, "motivo": "..."}}]
Se não tiver base para decidir, use categoria "Nao identificado" e confianca 0.
Nunca invente um estabelecimento que você não reconhece.
"""


@dataclass
class ItemParaClassificar:
    descricao_norm: str
    valor_centavos: int
    data_iso: str
    vizinhos: list[tuple[str, str]]  # (descricao_norm, categoria) mais similares


def classificar_lote(itens: list[ItemParaClassificar], categorias: list[str]) -> dict[str, tuple[str, float]]:
    raise NotImplementedError(
        "Camada 4 (LLM) ainda não conectada. Implemente aqui a única chamada de "
        "rede do sistema quando sobrar volume relevante após as camadas 1 e 2."
    )
