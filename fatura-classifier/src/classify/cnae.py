"""Camada 3: CNPJ/CNAE via enriquecimento do Open Finance.

Só roda se as camadas 1 e 2 falharam e houver enriquecimento disponível.
Sem Open Finance conectado (ver spec seção 10), esta camada é pulada -
não há como resolver nome de pessoa física por CNAE sem esses dados, e
não se deve inventar consulta a API pública de CNPJ a partir de um nome.
"""
from __future__ import annotations


def classificar(descricao_norm: str, merchant_info: dict | None = None) -> tuple[str, float] | None:
    if merchant_info is None:
        return None
    cnae = merchant_info.get("cnae")
    if cnae is None:
        return None
    raise NotImplementedError(
        "Camada 3 requer data/cnae_map.json e integração Open Finance (spec seção 10), "
        "ainda não conectados."
    )
