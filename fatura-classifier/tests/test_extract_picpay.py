import json
from dataclasses import asdict
from pathlib import Path

import pytest

from src.extract.base import ExtracaoInconsistenteError
from src.extract.picpay import PicPayExtractor

FIXTURES = Path(__file__).parent / "fixtures"
PDF_PATH = Path(__file__).parent.parent / "faturas" / "PicPay_082026.pdf"

pytestmark = pytest.mark.skipif(not PDF_PATH.exists(), reason="PDF real não está presente (gitignored)")


def _extrair():
    return PicPayExtractor().extract(PDF_PATH)


def test_total_geral_bate_com_a_fatura():
    fx = _extrair()
    assert fx.total_centavos == 605585


def test_numero_de_lancamentos_positivos():
    fx = _extrair()
    positivos = [l for l in fx.lancamentos if l.valor_centavos >= 0]
    assert len(positivos) == 73


def test_soma_dos_positivos_bate_com_total():
    fx = _extrair()
    soma = sum(l.valor_centavos for l in fx.lancamentos if l.valor_centavos >= 0)
    assert soma == fx.total_centavos


def test_vencimento_e_fechamento():
    fx = _extrair()
    assert fx.vencimento.isoformat() == "2026-09-05"
    assert fx.fechamento.isoformat() == "2026-08-27"


def test_pagamento_de_fatura_extraido_com_valor_negativo():
    fx = _extrair()
    pagamentos = [l for l in fx.lancamentos if l.descricao_original == "PAGAMENTO DE FATURA"]
    assert len(pagamentos) == 1
    assert pagamentos[0].valor_centavos == -861378
    assert pagamentos[0].portador is None


def test_contra_golden_file():
    fx = _extrair()
    esperado = json.loads((FIXTURES / "picpay_2026-09.json").read_text(encoding="utf-8"))

    assert fx.emissor == esperado["emissor"]
    assert fx.vencimento.isoformat() == esperado["vencimento"]
    assert fx.fechamento.isoformat() == esperado["fechamento"]
    assert fx.total_centavos == esperado["total_centavos"]

    obtido = []
    for l in fx.lancamentos:
        d = asdict(l)
        d["data"] = l.data.isoformat()
        obtido.append(d)
    assert obtido == esperado["lancamentos"]


def test_extracao_e_deterministica():
    fx1 = _extrair()
    fx2 = _extrair()
    assert len(fx1.lancamentos) == len(fx2.lancamentos)
    assert fx1.total_centavos == fx2.total_centavos


def test_subtotal_por_bloco_diverge_levanta_erro(monkeypatch):
    extractor = PicPayExtractor()
    linhas = [
        "NOME FALSO",
        "Picpay Card final 9999",
        "Transações Nacionais",
        "Data Estabelecimento Valor (R$)",
        "01/08 LOJA TESTE 10,00",
        "Subtotal dos lançamentos 99,00",
        "Total geral dos lançamentos 10,00",
    ]
    from datetime import date
    with pytest.raises(ExtracaoInconsistenteError):
        extractor._processar_linhas(linhas, date(2026, 9, 5), date(2026, 8, 27))


def test_total_geral_diverge_levanta_erro():
    extractor = PicPayExtractor()
    linhas = [
        "NOME FALSO",
        "Picpay Card final 9999",
        "Transações Nacionais",
        "Data Estabelecimento Valor (R$)",
        "01/08 LOJA TESTE 10,00",
        "Subtotal dos lançamentos 10,00",
        "Total geral dos lançamentos 20,00",
    ]
    from datetime import date
    with pytest.raises(ExtracaoInconsistenteError):
        extractor._processar_linhas(linhas, date(2026, 9, 5), date(2026, 8, 27))
