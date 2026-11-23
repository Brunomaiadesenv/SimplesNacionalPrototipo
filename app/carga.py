"""Carga do arquivo PGDAS-D nas tabelas PGDASD*.

ATENÇÃO: o layout abaixo é HIPOTÉTICO (campos separados por '|', um tipo de registro por linha), montado a partir dos
nomes de coluna do SL_ISS. Pendência 2 do Guia: trocar por um parser do layout oficial quando houver arquivo real + manual.
O que é definitivo e vale para qualquer layout: hash anti-reimportação, erro por linha, limite de % de erro, transação
única, NumeroLinha em cada registro e escolha da declaração vigente por transmissão (view).
"""
import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from . import db
from .config import S
from .confronto import valida_pa

# tipo -> (tabela, [(coluna, conversor)])  — a ordem é a ordem dos campos no arquivo
def _int(v): return int(v)
def _dec(v): return float(Decimal(v.replace(",", ".")))
def _txt(v): return v.strip()
def _cnpj(v):
    d = re.sub(r"\D", "", v)
    if len(d) != 14:
        raise ValueError("CNPJ deve ter 14 dígitos")
    return int(d)
def _pa(v): return valida_pa(v)
def _dt(v): return datetime.fromisoformat(v.strip()).isoformat(sep=" ")
def _data(v): return datetime.fromisoformat(v.strip()[:10]).date().isoformat()

LAYOUT = {
    "00000": ("PGDASD00000", [("Pgdasd_Num_Recibo", _txt), ("Cnpjmatriz", _cnpj), ("Pa", _pa), ("CodTOM", _int),
                              ("Optante", _int), ("Rpa", _dec), ("Operacao", _int), ("Pgdasd_Dt_Transmissao", _dt)]),
    "01000": ("PGDASD01000", [("Nrpagto", _txt), ("Princ", _dec), ("Multa", _dec), ("Juros", _dec), ("Tdevido", _dec),
                              ("Dtvalcalc", _data), ("Dtvenc", _data), ("Vdas", _dec)]),
    "01100": ("PGDASD01100", [("codmunic", _int), ("valorprinc", _dec), ("valorm", _dec), ("valorj", _dec)]),
    "02000": ("PGDASD02000", [("rbt12", _dec), ("Rba", _dec), ("ICMS", _dec), ("ISS", _dec)]),
    "03000": ("PGDASD03000", [("CNPJ", _cnpj), ("CodTOM", _int), ("Vltotal", _dec)]),
    "03110": ("PGDASD03110", [("CodTOM", _int), ("Valor", _dec), ("ISS", _dec), ("AliApuradaISS", _dec), ("ValorApuradoISS", _dec)]),
}


def analisa(texto: str) -> dict:
    """Lê e valida o arquivo inteiro, sem tocar no banco."""
    linhas = [(i, l.rstrip("\r\n")) for i, l in enumerate(texto.splitlines(), 1) if l.strip()]
    erros, decls, atual, esperado, n_dados = [], [], None, None, 0
    for num, bruta in linhas:
        campos = bruta.split("|")
        tipo = campos[0].strip()
        if tipo == "ARQ":
            try:
                esperado = int(campos[1])
            except (IndexError, ValueError):
                erros.append((num, bruta, "Cabeçalho ARQ inválido (esperado ARQ|qtd_linhas)"))
            continue
        n_dados += 1
        if tipo not in LAYOUT:
            erros.append((num, bruta, f"Tipo de registro desconhecido: {tipo!r}"))
            continue
        tabela, cols = LAYOUT[tipo]
        if len(campos) - 1 != len(cols):
            erros.append((num, bruta, f"Registro {tipo} exige {len(cols)} campos, veio {len(campos) - 1}"))
            if tipo == "00000":
                atual = None
            continue
        try:
            vals = {c: f(v) for (c, f), v in zip(cols, campos[1:])}
        except (ValueError, InvalidOperation) as e:
            erros.append((num, bruta, f"Valor inválido em {tipo}: {e}"))
            if tipo == "00000":
                atual = None   # declaração descartada: filhos dela também serão rejeitados abaixo
            continue
        if tipo == "00000":
            atual = dict(linha=num, cab=vals, filhos=[])
            decls.append(atual)
        elif atual is None:
            erros.append((num, bruta, f"Registro {tipo} sem declaração (00000) válida antes dele"))
        else:
            atual["filhos"].append((tipo, num, vals))
    if esperado is not None and esperado != n_dados:
        erros.append((0, "ARQ", f"QTD_LIN do cabeçalho ({esperado}) diferente das linhas lidas ({n_dados})"))
    return dict(linhas=n_dados, esperado=esperado, declaracoes=decls, erros=erros)


def importa(texto: str, nome: str, usuario: str, so_validar: bool = False) -> dict:
    h = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    an = analisa(texto)
    n_err = len([e for e in an["erros"] if e[0] > 0])
    pct = 100.0 * n_err / an["linhas"] if an["linhas"] else 100.0
    base = dict(hash=h, nome=nome, linhas=an["linhas"], declaracoes=len(an["declaracoes"]), linhas_invalidas=n_err,
                pct_invalidas=round(pct, 2), erros=[dict(linha=n, texto=t[:200], erro=e) for n, t, e in an["erros"][:200]])
    ja = db.fetch(f"SELECT Id, NomeArquivo FROM {db.T('PGDASDAAAAA')} WHERE Hash = ?", [h])
    if ja:
        return dict(base, status="recusado", motivo=f"Arquivo já importado (id {ja[0]['Id']}, {ja[0]['NomeArquivo']}).")
    if not an["declaracoes"]:
        return dict(base, status="recusado", motivo="Nenhuma declaração (00000) válida no arquivo.")
    if pct > S.MAX_ERRO_CARGA_PCT:
        return dict(base, status="revertido",
                    motivo=f"{pct:.1f}% de linhas inválidas (limite {S.MAX_ERRO_CARGA_PCT:g}%). Nada foi gravado.")
    if so_validar:
        return dict(base, status="validado", motivo="Arquivo válido; nada foi gravado (modo validar).")
    agora = datetime.now().isoformat(sep=" ", timespec="seconds")
    with db.tx() as cur:
        aid = db.insert_id(cur, "PGDASDAAAAA", dict(Hash=h, NomeArquivo=nome, DataEnvio=agora, QTD_LIN=an["linhas"], Usuario=usuario))
        for d in an["declaracoes"]:
            cab = dict(d["cab"], idPGDASDAAAAA=aid, NumeroLinha=d["linha"])
            did = db.insert_id(cur, "PGDASD00000", cab)
            for tipo, num, vals in d["filhos"]:
                tabela = LAYOUT[tipo][0]
                dados = dict(vals, idPGDASDAAAAA=aid, idPGDASD00000=did, NumeroLinha=num)
                cols = ", ".join(dados)
                cur.execute(f"INSERT INTO {db.T(tabela)} ({cols}) VALUES ({','.join('?' * len(dados))})", list(dados.values()))
        for num, bruta, erro in an["erros"]:
            cur.execute(f"INSERT INTO {db.T('ArquivoSimplesErro')} (Evento, ArquivoId, NumeroLinha, LinhaBruta, Erro) VALUES (?,?,?,?,?)",
                        ["PGDASD", aid, num, bruta[:2000], erro[:300]])
    return dict(base, status="importado", arquivo_id=aid, motivo="Arquivo importado em uma única transação.")
