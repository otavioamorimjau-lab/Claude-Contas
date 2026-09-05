import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from src import cli as cli_module

PDF_PATH = Path(__file__).parent.parent / "faturas" / "PicPay_082026.pdf"

pytestmark = pytest.mark.skipif(not PDF_PATH.exists(), reason="PDF real não está presente (gitignored)")


def test_importar_o_mesmo_pdf_duas_vezes_nao_duplica(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, "DB_PATH", tmp_path / "fatura.db")
    runner = CliRunner()

    r1 = runner.invoke(cli_module.cli, ["import", str(PDF_PATH)])
    assert r1.exit_code == 0, r1.output

    r2 = runner.invoke(cli_module.cli, ["import", str(PDF_PATH)])
    assert r2.exit_code == 0, r2.output
    assert "já processada" in r2.output

    conn = sqlite3.connect(tmp_path / "fatura.db")
    assert conn.execute("SELECT COUNT(*) FROM lancamento").fetchone()[0] == 74
    assert conn.execute("SELECT COUNT(*) FROM fatura").fetchone()[0] == 1


def test_importar_nao_reclassifica_entrada_ja_confirmada(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, "DB_PATH", tmp_path / "fatura.db")
    runner = CliRunner()
    runner.invoke(cli_module.cli, ["import", str(PDF_PATH)])

    from src import db

    conn = db.conectar(tmp_path / "fatura.db")
    db.dicionario_set_manual(conn, "LUAD", "Pet")

    r2 = runner.invoke(cli_module.cli, ["dict", "list"])
    assert "LUAD" in r2.output
    row = db.dicionario_buscar(conn, "LUAD")
    assert row["categoria"] == "Pet"
    assert row["confirmado"] == 1
