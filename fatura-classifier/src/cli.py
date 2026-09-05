from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import click

from . import db, installments, report
from .classify import engine, fuzzy
from .extract.base import ExtracaoInconsistenteError
from .extract.picpay import PicPayExtractor
from .normalize import extract_parcela, normalize

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "data" / "fatura.db"
SEED_PATH = RAIZ / "data" / "seed_dicionario.json"
CATEGORIAS_PATH = RAIZ / "data" / "categorias.json"


def _fmt_reais(centavos: int) -> str:
    """Formatação pt-BR. Só usada na camada de apresentação (CLAUDE.md)."""
    negativo = centavos < 0
    texto = f"{abs(centavos) / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{'-' if negativo else ''}R$ {texto}"


def _conectar() -> sqlite3.Connection:
    conn = db.conectar(DB_PATH)
    db.criar_schema(conn)
    if SEED_PATH.exists():
        db.carregar_seed(conn, SEED_PATH)
    return conn


def _carregar_categorias() -> list[str]:
    return json.loads(CATEGORIAS_PATH.read_text(encoding="utf-8"))


@click.group()
def cli():
    """Classificador automático de faturas de cartão."""


@cli.command("import")
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
def importar(pdf_path: Path):
    """Extrai, valida, classifica e grava uma fatura."""
    conn = _conectar()

    arquivo_hash = db.computar_arquivo_hash(pdf_path)
    existente = db.buscar_fatura_por_hash(conn, arquivo_hash)
    if existente is not None:
        click.echo(
            f"Fatura já processada em {existente['processado_em']} "
            f"(vencimento {existente['vencimento']}). Nada a fazer."
        )
        return

    try:
        fx = PicPayExtractor().extract(pdf_path)
    except ExtracaoInconsistenteError as e:
        raise click.ClickException(str(e)) from e

    try:
        fatura_id = db.inserir_fatura(
            conn, fx.emissor, fx.vencimento, fx.fechamento, fx.total_centavos, arquivo_hash
        )
    except sqlite3.IntegrityError as e:
        raise click.ClickException(
            f"Já existe uma fatura de {fx.emissor} com vencimento {fx.vencimento} "
            f"(arquivo diferente). {e}"
        ) from e

    novos = 0
    duplicados = 0
    classificados = {"dicionario": 0, "fuzzy": 0, "nao_classificado": 0}

    for l in fx.lancamentos:
        descricao_norm = normalize(l.descricao_original)
        parcela = extract_parcela(l.descricao_original)
        compra_id = None
        parcela_num = parcela_total = None
        if parcela is not None:
            parcela_num, parcela_total = parcela
            compra_id = installments.vincular_parcela(
                conn,
                descricao_norm=descricao_norm,
                valor_parcela_centavos=l.valor_centavos,
                parcela_total=parcela_total,
                competencia_fatura=fx.vencimento,
            )

        classificacao = engine.classificar(conn, descricao_norm)
        classificados[classificacao.origem] = classificados.get(classificacao.origem, 0) + 1

        inserido = db.inserir_lancamento(
            conn,
            fatura_id=fatura_id,
            data_lanc=l.data,
            descricao_original=l.descricao_original,
            descricao_norm=descricao_norm,
            valor_centavos=l.valor_centavos,
            portador=l.portador,
            cartao_final=l.cartao_final,
            parcela_num=parcela_num,
            parcela_total=parcela_total,
            compra_id=compra_id,
            categoria=classificacao.categoria,
            origem_categoria=classificacao.origem,
            confianca=classificacao.confianca,
        )
        if inserido:
            novos += 1
        else:
            duplicados += 1

    total = len(fx.lancamentos)
    resolvidos = classificados.get("dicionario", 0) + classificados.get("fuzzy", 0)
    taxa = (resolvidos / total * 100) if total else 0.0
    click.echo(f"Fatura {fx.vencimento} importada: {novos} lançamentos novos, {duplicados} já existiam.")
    click.echo(
        f"Classificação automática: {resolvidos}/{total} ({taxa:.1f}%) - "
        f"dicionario={classificados.get('dicionario', 0)} fuzzy={classificados.get('fuzzy', 0)} "
        f"pendente={classificados.get('nao_classificado', 0)}"
    )


@cli.command("review")
def review():
    """Lista o não classificado e a faixa 75-90 de fuzzy; pergunta interativamente."""
    conn = _conectar()
    categorias = _carregar_categorias()

    pendentes = conn.execute(
        "SELECT DISTINCT descricao_norm FROM lancamento WHERE origem_categoria = 'nao_classificado'"
    ).fetchall()

    if not pendentes:
        click.echo("Nada pendente de revisão.")
        return

    for row in pendentes:
        descricao_norm = row["descricao_norm"]
        exemplo = conn.execute(
            "SELECT descricao_original, valor_centavos, data FROM lancamento WHERE descricao_norm = ? LIMIT 1",
            (descricao_norm,),
        ).fetchone()
        click.echo(
            f"\n{descricao_norm}  (ex: '{exemplo['descricao_original']}', "
            f"{_fmt_reais(exemplo['valor_centavos'])} em {exemplo['data']})"
        )
        sugestao = fuzzy.melhor_match(conn, descricao_norm)
        if sugestao and fuzzy.LIMIAR_REVISAO <= sugestao.score < fuzzy.LIMIAR_AUTOACEITA:
            click.echo(
                f"  sugestão: {sugestao.categoria} "
                f"(parecido com '{sugestao.descricao_norm_sugerida}', score={sugestao.score})"
            )
        for i, cat in enumerate(categorias, 1):
            click.echo(f"  {i}) {cat}")
        escolha = click.prompt("Categoria (número) ou 's' para pular", default="s")
        if escolha.lower() == "s":
            continue
        try:
            categoria = categorias[int(escolha) - 1]
        except (ValueError, IndexError):
            click.echo("Opção inválida, pulando.")
            continue
        db.dicionario_set_manual(conn, descricao_norm, categoria)
        conn.execute(
            "UPDATE lancamento SET categoria = ?, origem_categoria = 'manual', confianca = 1.0 "
            "WHERE descricao_norm = ?",
            (categoria, descricao_norm),
        )
        conn.commit()
        click.echo(f"  gravado: {descricao_norm} -> {categoria}")


@cli.command("report")
@click.option("--mes", "competencia", help="Competência YYYY-MM (mês de vencimento da fatura).")
@click.option("--parcelas", "modo_parcelas", is_flag=True, help="Compromisso futuro mês a mês.")
def report_cmd(competencia: str | None, modo_parcelas: bool):
    """Resumo por categoria, portador, parcelas."""
    conn = _conectar()

    if modo_parcelas:
        linhas = report.relatorio_parcelas(conn)
        total_futuro = installments.compromisso_futuro_centavos(conn)
        for l in linhas:
            click.echo(
                f"{l['descricao_norm']}: parcela {l['parcela_atual']}/{l['parcela_total']}, "
                f"restam {l['parcelas_restantes']}, compromisso futuro "
                f"{_fmt_reais(l['compromisso_futuro_centavos'])}"
            )
        click.echo(f"\nCompromisso futuro total: {_fmt_reais(total_futuro)}")
        return

    if not competencia:
        raise click.UsageError("Use --mes YYYY-MM ou --parcelas.")

    click.echo(f"Resumo por categoria - {competencia}")
    for row in report.resumo_por_categoria(conn, competencia):
        click.echo(f"  {row['categoria'] or '(sem categoria)'}: {_fmt_reais(row['total_centavos'])} ({row['qtd']})")

    click.echo(f"\nResumo por portador - {competencia}")
    for row in report.resumo_por_portador(conn, competencia):
        click.echo(f"  {row['portador'] or '(sem portador)'}: {_fmt_reais(row['total_centavos'])} ({row['qtd']})")


@cli.group("dict")
def dict_group():
    """Consulta e edita o dicionário de aprendizado."""


@dict_group.command("list")
def dict_list():
    conn = _conectar()
    for row in conn.execute("SELECT descricao_norm, categoria, origem, confirmado, ocorrencias FROM dicionario ORDER BY descricao_norm"):
        marca = "*" if row["confirmado"] else " "
        click.echo(f"{marca} {row['descricao_norm']:<40} {row['categoria']:<30} {row['origem']:<10} ({row['ocorrencias']}x)")


@dict_group.command("set")
@click.argument("descricao")
@click.argument("categoria")
def dict_set(descricao: str, categoria: str):
    conn = _conectar()
    categorias_validas = _carregar_categorias()
    if categoria not in categorias_validas:
        raise click.ClickException(f"Categoria inválida: {categoria!r}. Válidas: {categorias_validas}")
    db.dicionario_set_manual(conn, descricao.upper(), categoria)
    click.echo(f"{descricao.upper()} -> {categoria} (confirmado)")


@dict_group.command("export")
@click.option("--destino", type=click.Path(path_type=Path), default=None)
def dict_export(destino: Path | None):
    conn = _conectar()
    dados = {}
    for row in conn.execute("SELECT * FROM dicionario ORDER BY descricao_norm"):
        dados[row["descricao_norm"]] = {
            "categoria": row["categoria"],
            "origem": row["origem"],
            "confirmado": row["confirmado"],
        }
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    if destino:
        destino.write_text(texto + "\n", encoding="utf-8")
        click.echo(f"Exportado para {destino}")
    else:
        click.echo(texto)


@cli.command("export")
@click.option("--mes", "competencia", required=True, help="Competência YYYY-MM.")
@click.option("--format", "formato", type=click.Choice(["csv", "xlsx"]), default="csv")
@click.option("--destino", type=click.Path(path_type=Path), default=None)
def export_cmd(competencia: str, formato: str, destino: Path | None):
    conn = _conectar()
    if formato == "xlsx":
        raise click.ClickException(
            "Formato xlsx requer uma dependência (ex.: openpyxl) ainda não adicionada ao "
            "projeto - ver CLAUDE.md: 'não adicione dependência sem justificar no PR'. "
            "Use --format csv por enquanto."
        )
    destino = destino or RAIZ / "data" / f"export_{competencia}.csv"
    n = report.exportar_csv(conn, competencia, destino)
    click.echo(f"{n} lançamentos exportados para {destino}")


if __name__ == "__main__":
    cli()
