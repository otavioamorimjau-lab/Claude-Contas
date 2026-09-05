# Regras deste projeto

- Dinheiro sempre em centavos, inteiro. Nunca float, nem em variável intermediária.
- Datas sempre ISO (YYYY-MM-DD) internamente. Formatação pt-BR só na camada de apresentação.
- `normalize()` é função pura: sem I/O, sem estado, sem acesso a banco. Determinística.
- Toda escrita no banco passa por `db.py`. Nada de SQL espalhado pelos módulos.
- Extração que não bate com o total impresso levanta exceção. Nunca continue com aviso.
- Entrada de dicionário com `confirmado=1` jamais é sobrescrita por camada automática.
- A cascata de classificação para na primeira camada que responde.
- Nenhuma chamada de rede fora de `classify/llm.py` (e dos módulos de Open Finance,
  se/quando a seção 10 da spec for implementada - nesse dia, atualize esta regra).
- Escreva o teste antes da implementação em `normalize.py` e `installments.py`.
- Não adicione dependência sem justificar no PR. A lista atual é: pdfplumber, rapidfuzz, click, pytest.
