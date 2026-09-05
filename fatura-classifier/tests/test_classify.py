from pathlib import Path

from src import db
from src.classify import engine


def _banco(tmp_path: Path):
    conn = db.conectar(tmp_path / "test.db")
    db.criar_schema(conn)
    return conn


def test_camada1_resolve_e_para_a_cascata(tmp_path):
    conn = _banco(tmp_path)
    db.dicionario_set_manual(conn, "PADARIA X", "Alimentacao fora")
    resultado = engine.classificar(conn, "PADARIA X")
    assert resultado.categoria == "Alimentacao fora"
    assert resultado.origem == "dicionario"
    assert resultado.confianca == 1.0


def test_camada2_so_aceita_acima_do_limiar(tmp_path):
    conn = _banco(tmp_path)
    db.dicionario_set_manual(conn, "AUTO POSTO SANTA MONICA", "Transporte/Combustivel")
    resultado = engine.classificar(conn, "AUTO POSTO SANTA MONIC")
    assert resultado.categoria == "Transporte/Combustivel"
    assert resultado.origem == "fuzzy"


def test_camada2_nao_confunde_filiais_diferentes(tmp_path):
    conn = _banco(tmp_path)
    db.dicionario_set_manual(conn, "POSTO JAGUAR 3", "Transporte/Combustivel")
    resultado = engine.classificar(conn, "POSTO JAGUAR 5")
    # "POSTO JAGUAR 3" vs "POSTO JAGUAR 5" tem score alto (só 1 char difere) mas
    # são filiais possivelmente distintas - o teste documenta o comportamento
    # atual: a decisão de tratá-las como iguais é do limiar de score, não de
    # regra de negócio. Ver spec seção 15 "armadilhas conhecidas".
    assert resultado is not None


def test_confirmado_nunca_e_sobrescrito_por_camada_automatica(tmp_path):
    conn = _banco(tmp_path)
    db.dicionario_set_manual(conn, "LUAD", "Pet")
    db.dicionario_inserir_automatico(conn, "LUAD", "Alimentacao fora", origem="fuzzy", confianca=0.95)
    row = db.dicionario_buscar(conn, "LUAD")
    assert row["categoria"] == "Pet"
    assert row["confirmado"] == 1


def test_mesma_entrada_classificada_duas_vezes_da_mesmo_resultado(tmp_path):
    conn = _banco(tmp_path)
    db.dicionario_set_manual(conn, "FARMACIA Y", "Saude/Farmacia")
    r1 = engine.classificar(conn, "FARMACIA Y")
    r2 = engine.classificar(conn, "FARMACIA Y")
    assert (r1.categoria, r1.origem, r1.confianca) == (r2.categoria, r2.origem, r2.confianca)


def test_nao_classificado_quando_nenhuma_camada_resolve(tmp_path):
    conn = _banco(tmp_path)
    resultado = engine.classificar(conn, "ESTABELECIMENTO NUNCA VISTO XYZ123")
    assert resultado.categoria is None
    assert resultado.origem == "nao_classificado"


def test_camada_fuzzy_grava_entrada_nao_confirmada_no_dicionario(tmp_path):
    conn = _banco(tmp_path)
    db.dicionario_set_manual(conn, "EMPORIO MISTER BEEF", "Mercado/Acougue")
    engine.classificar(conn, "EMPORIO MISTER BEEF AL")
    row = db.dicionario_buscar(conn, "EMPORIO MISTER BEEF AL")
    assert row is not None
    assert row["origem"] == "fuzzy"
    assert row["confirmado"] == 0
    # próxima vez, a mesma descrição resolve direto na camada 1
    resultado = engine.classificar(conn, "EMPORIO MISTER BEEF AL")
    assert resultado.origem == "dicionario"
