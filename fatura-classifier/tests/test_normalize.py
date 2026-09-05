from src.normalize import extract_parcela, normalize

CASOS_TABELA = [
    ("IFD*MARCO AURELIO DA C", "MARCO AURELIO DA C", None),
    ("JIM.COM* AGILEPARC03/12", "AGILE", (3, 12)),
    ("MARAVILHAS DO PARC02/04", "MARAVILHAS DO", (2, 4)),
    ("IFD*63372699 MARLENE T", "MARLENE T", None),
    ("RAIA DROGASIL PARC02/02", "RAIA DROGASIL", (2, 2)),
    ("POSTO JAGUAR 3", "POSTO JAGUAR 3", None),
    ("IFD*L F VINCENZI LTDA", "L F VINCENZI", None),
    ("EMPORIO MISTER BEEF AL", "EMPORIO MISTER BEEF AL", None),
]


def test_tabela_de_casos_obrigatorios():
    for entrada, esperado, _ in CASOS_TABELA:
        assert normalize(entrada) == esperado, f"normalize({entrada!r})"


def test_tabela_de_parcelas():
    for entrada, _, parcela_esperada in CASOS_TABELA:
        assert extract_parcela(entrada) == parcela_esperada, f"extract_parcela({entrada!r})"


def test_nao_remove_numeros_curtos_de_filial():
    assert normalize("POSTO JAGUAR 3") == "POSTO JAGUAR 3"
    assert normalize("PAGUE MENOSA 11") == "PAGUE MENOSA 11"


def test_prefixo_generico_fallback_ate_12_chars():
    assert normalize("XPTO12345*ALGO") == "ALGO"


def test_prefixo_generico_fallback_nao_aplica_acima_de_12_chars():
    texto_longo = "A" * 13 + "*ALGO"
    assert normalize(texto_longo) == texto_longo


def test_parcela_grudada_em_nome_com_hifen():
    assert normalize("CIA TERNO-LESCPARC01/06") == "CIA TERNO-LESC"
    assert extract_parcela("CIA TERNO-LESCPARC01/06") == (1, 6)


def test_remove_acentos():
    assert normalize("AÇÃO É ÓTIMA") == "ACAO E OTIMA"


def test_idempotente():
    for entrada, esperado, _ in CASOS_TABELA:
        assert normalize(esperado) == esperado


def test_deterministico():
    for entrada, esperado, _ in CASOS_TABELA:
        assert normalize(entrada) == normalize(entrada)
