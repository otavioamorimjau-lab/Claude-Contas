import json
from datetime import date
from pathlib import Path

from src import db, installments
from src.normalize import extract_parcela, normalize

FIXTURE = Path(__file__).parent / "fixtures" / "picpay_2026-09.json"


def _banco(tmp_path: Path):
    conn = db.conectar(tmp_path / "test.db")
    db.criar_schema(conn)
    return conn


def _importar_golden(conn, dados) -> date:
    vencimento = date.fromisoformat(dados["vencimento"])
    fatura_id = db.inserir_fatura(
        conn, dados["emissor"], vencimento, date.fromisoformat(dados["fechamento"]),
        dados["total_centavos"], "hash-teste",
    )
    for l in dados["lancamentos"]:
        descricao_norm = normalize(l["descricao_original"])
        parcela = extract_parcela(l["descricao_original"])
        compra_id = None
        parcela_num = parcela_total = None
        if parcela is not None:
            parcela_num, parcela_total = parcela
            compra_id = installments.vincular_parcela(
                conn,
                descricao_norm=descricao_norm,
                valor_parcela_centavos=l["valor_centavos"],
                parcela_total=parcela_total,
                competencia_fatura=vencimento,
            )
        db.inserir_lancamento(
            conn,
            fatura_id=fatura_id,
            data_lanc=date.fromisoformat(l["data"]),
            descricao_original=l["descricao_original"],
            descricao_norm=descricao_norm,
            valor_centavos=l["valor_centavos"],
            portador=l["portador"],
            cartao_final=l["cartao_final"],
            parcela_num=parcela_num,
            parcela_total=parcela_total,
            compra_id=compra_id,
            categoria=None,
            origem_categoria="nao_classificado",
            confianca=None,
        )
    return vencimento


def test_compromisso_futuro_bate_com_fatura_referencia(tmp_path):
    conn = _banco(tmp_path)
    dados = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _importar_golden(conn, dados)

    # Valor consolidado das parcelas futuras impresso na fatura real: R$ 15.431,73
    assert installments.compromisso_futuro_centavos(conn) == 1_543_173


def test_mesma_compra_key_reaproveita_a_linha_de_compra(tmp_path):
    conn = _banco(tmp_path)
    vencimento = date(2026, 9, 5)
    id1 = installments.vincular_parcela(
        conn, descricao_norm="LOJA X", valor_parcela_centavos=1000, parcela_total=3,
        competencia_fatura=vencimento,
    )
    id2 = installments.vincular_parcela(
        conn, descricao_norm="LOJA X", valor_parcela_centavos=1000, parcela_total=3,
        competencia_fatura=vencimento,
    )
    assert id1 == id2


def test_compra_key_diferente_por_valor_ou_total_nao_colide(tmp_path):
    conn = _banco(tmp_path)
    vencimento = date(2026, 9, 5)
    id_a = installments.vincular_parcela(
        conn, descricao_norm="LOJA Y", valor_parcela_centavos=1000, parcela_total=3,
        competencia_fatura=vencimento,
    )
    id_b = installments.vincular_parcela(
        conn, descricao_norm="LOJA Y", valor_parcela_centavos=2000, parcela_total=3,
        competencia_fatura=vencimento,
    )
    assert id_a != id_b


def test_parcela_totalmente_paga_nao_conta_no_compromisso_futuro(tmp_path):
    conn = _banco(tmp_path)
    vencimento = date(2026, 9, 5)
    compra_id = installments.vincular_parcela(
        conn, descricao_norm="LOJA Z", valor_parcela_centavos=5000, parcela_total=2,
        competencia_fatura=vencimento,
    )
    db.inserir_fatura(conn, "picpay", vencimento, date(2026, 8, 27), 5000, "hash-z")
    db.inserir_lancamento(
        conn, fatura_id=1, data_lanc=vencimento, descricao_original="LOJA Z PARC02/02",
        descricao_norm="LOJA Z", valor_centavos=5000, portador=None, cartao_final=None,
        parcela_num=2, parcela_total=2, compra_id=compra_id, categoria=None,
        origem_categoria="nao_classificado", confianca=None,
    )
    assert installments.compromisso_futuro_centavos(conn) == 0
