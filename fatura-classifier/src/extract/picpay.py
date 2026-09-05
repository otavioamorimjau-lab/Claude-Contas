"""Extrator de fatura PicPay (PDF).

Lançamentos vêm em duas colunas lado a lado. A leitura correta atravessa
página: coluna esquerda -> coluna direita -> coluna esquerda da página
seguinte (um bloco de portador pode começar numa coluna e terminar na
seguinte). Ver spec seção 5.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pdfplumber

from .base import ExtracaoInconsistenteError, FaturaExtraida, LancamentoBruto

_RE_VENC_FECH = re.compile(
    r"Vencimento:\s*(\d{2}/\d{2}/\d{4})\s*\|\s*Fechamento:\s*(\d{2}/\d{2}/\d{4})"
)
_RE_TXN = re.compile(r"^(\d{2})/(\d{2})\s+(.+?)\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})$")
_RE_CARTAO_FINAL = re.compile(r"^Picpay Card final (\d{4})$")
_RE_CARTAO_SOZINHO = re.compile(r"^Picpay Card$")
_RE_SUBTOTAL = re.compile(r"^Subtotal dos lançamentos\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})$")
_RE_TOTAL_GERAL = re.compile(r"^Total geral dos lançamentos\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})$")


def _parse_valor_centavos(texto: str) -> int:
    negativo = texto.startswith("-")
    texto = texto.lstrip("-").replace(".", "").replace(",", "")
    valor = int(texto)
    return -valor if negativo else valor


def _parse_data_br(s: str) -> date:
    dia, mes, ano = s.split("/")
    return date(int(ano), int(mes), int(dia))


def _inferir_ano(mes: int, fechamento: date) -> int:
    # Lançamento de parcela antiga aparece sem ano, só "DD/MM". Se o mês é
    # posterior ao mês de fechamento, o lançamento é do ano anterior.
    return fechamento.year if mes <= fechamento.month else fechamento.year - 1


def _reconstruir_colunas(page) -> tuple[list[str], list[str]]:
    xmid = page.width / 2
    words = page.extract_words()
    esquerda: dict[int, list] = defaultdict(list)
    direita: dict[int, list] = defaultdict(list)
    for w in words:
        alvo = esquerda if w["x0"] < xmid else direita
        alvo[round(w["top"])].append(w)

    def montar(coluna: dict[int, list]) -> list[str]:
        linhas = []
        for top in sorted(coluna):
            palavras = sorted(coluna[top], key=lambda w: w["x0"])
            linhas.append(" ".join(p["text"] for p in palavras))
        return linhas

    return montar(esquerda), montar(direita)


def _linha_e_portador(proxima_linha: str | None) -> bool:
    return proxima_linha is not None and bool(_RE_CARTAO_FINAL.match(proxima_linha))


class PicPayExtractor:
    emissor = "picpay"

    def extract(self, pdf_path: Path) -> FaturaExtraida:
        with pdfplumber.open(pdf_path) as pdf:
            texto_pagina0 = pdf.pages[0].extract_text() or ""
            m = _RE_VENC_FECH.search(texto_pagina0)
            if not m:
                raise ExtracaoInconsistenteError(
                    "Não encontrei 'Vencimento: ... | Fechamento: ...' na primeira página."
                )
            vencimento = _parse_data_br(m.group(1))
            fechamento = _parse_data_br(m.group(2))

            linhas: list[str] = []
            for page in pdf.pages:
                texto = page.extract_text() or ""
                if "Transações Nacionais" not in texto:
                    continue
                esquerda, direita = _reconstruir_colunas(page)
                linhas.extend(esquerda)
                linhas.extend(direita)

        return self._processar_linhas(linhas, vencimento, fechamento)

    def _processar_linhas(
        self, linhas: list[str], vencimento: date, fechamento: date
    ) -> FaturaExtraida:
        lancamentos: list[LancamentoBruto] = []
        subtotais_divergentes: list[str] = []

        portador: str | None = None
        cartao_final: str | None = None
        bloco_atual: list[LancamentoBruto] = []
        bloco_soma = 0
        total_centavos: int | None = None

        def fechar_bloco() -> None:
            nonlocal bloco_atual, bloco_soma
            lancamentos.extend(bloco_atual)
            bloco_atual = []
            bloco_soma = 0

        i = 0
        n = len(linhas)
        while i < n:
            linha = linhas[i]
            proxima = linhas[i + 1] if i + 1 < n else None

            if _RE_CARTAO_SOZINHO.match(linha):
                fechar_bloco()
                portador = None
                cartao_final = None
                i += 1
                continue

            m_cartao = _RE_CARTAO_FINAL.match(linha)
            if m_cartao:
                cartao_final = m_cartao.group(1)
                i += 1
                continue

            if _linha_e_portador(proxima):
                fechar_bloco()
                portador = linha.strip()
                cartao_final = None
                i += 1
                continue

            m_txn = _RE_TXN.match(linha)
            if m_txn:
                dia, mes, descricao, valor_str = m_txn.groups()
                ano = _inferir_ano(int(mes), fechamento)
                data_lanc = date(ano, int(mes), int(dia))
                valor_centavos = _parse_valor_centavos(valor_str)
                bloco_atual.append(
                    LancamentoBruto(
                        data=data_lanc,
                        descricao_original=descricao.strip(),
                        valor_centavos=valor_centavos,
                        portador=portador,
                        cartao_final=cartao_final,
                    )
                )
                bloco_soma += valor_centavos
                i += 1
                continue

            m_subtotal = _RE_SUBTOTAL.match(linha)
            if m_subtotal:
                esperado = _parse_valor_centavos(m_subtotal.group(1))
                if esperado != bloco_soma:
                    subtotais_divergentes.append(
                        f"portador={portador!r} cartao={cartao_final!r}: "
                        f"esperado R$ {esperado / 100:.2f}, calculado R$ {bloco_soma / 100:.2f}"
                    )
                fechar_bloco()
                i += 1
                continue

            m_total = _RE_TOTAL_GERAL.match(linha)
            if m_total:
                fechar_bloco()
                total_centavos = _parse_valor_centavos(m_total.group(1))
                i += 1
                continue

            i += 1

        fechar_bloco()

        if total_centavos is None:
            raise ExtracaoInconsistenteError(
                "Não encontrei a linha 'Total geral dos lançamentos' no PDF."
            )

        if subtotais_divergentes:
            raise ExtracaoInconsistenteError(
                "Subtotais divergentes por bloco:\n" + "\n".join(subtotais_divergentes)
            )

        soma_positivos = sum(l.valor_centavos for l in lancamentos if l.valor_centavos >= 0)
        if soma_positivos != total_centavos:
            delta = (soma_positivos - total_centavos) / 100
            raise ExtracaoInconsistenteError(
                f"Total geral divergente: impresso R$ {total_centavos / 100:.2f}, "
                f"calculado R$ {soma_positivos / 100:.2f} (delta R$ {delta:.2f})"
            )

        return FaturaExtraida(
            emissor=self.emissor,
            vencimento=vencimento,
            fechamento=fechamento,
            total_centavos=total_centavos,
            lancamentos=lancamentos,
        )
