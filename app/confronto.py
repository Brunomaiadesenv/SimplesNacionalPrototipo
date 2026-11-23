"""Regras de negócio do confronto declarado (PGDAS-D) x escriturado (ISSWEB/Bia) x pago.

As consultas agregam no banco (portável); o cruzamento (FULL JOIN por CNPJ) e as regras D00–D08
ficam aqui, em Python, para serem testáveis e idênticas em SQL Server e SQLite.
"""
import calendar
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from . import db, queries as Q
from .config import S
from . import colunas as C

LOTE = 500  # tamanho do IN (...) — abaixo do limite de parâmetros do ODBC


def d2(x) -> Decimal:
    return Decimal(str(x if x is not None else 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def norm_cnpj(x) -> str:
    return str(int(x)).zfill(14) if str(x).strip().isdigit() else "".join(ch for ch in str(x) if ch.isdigit()).zfill(14)


def to_date(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.fromisoformat(str(v)[:10]).date()


def lotes(lista, n=LOTE):
    lista = list(lista)
    for i in range(0, len(lista), n):
        yield lista[i:i + n]


def valida_pa(pa) -> int:
    try:
        pa = int(pa)
    except (TypeError, ValueError):
        raise ValueError("PA inválida. Use AAAAMM, por exemplo 202510.")
    if not (200001 <= pa <= 209912) or not (1 <= pa % 100 <= 12):
        raise ValueError("PA inválida. Use AAAAMM, por exemplo 202510.")
    return pa


def periodo(pa: int):
    a, m = divmod(pa, 100)
    return date(a, m, 1), date(a, m, calendar.monthrange(a, m)[1])


def adesao_ativa(linhas, ini, fim):
    """Regra de transição: sem histórico => None (segue o flag do cadastro, sem D08)."""
    if not linhas:
        return None
    for l in linhas:
        ad, ca = to_date(l["dt_adesao"]), to_date(l["dt_cancel"])
        if ad and ad <= fim and (ca is None or ca >= ini):
            return True
    return False


def calcula(pa, tom=None, tol_abs=None, tol_aliq=None) -> dict:
    """Roda o confronto da PA (somente leitura). Devolve resumo + lista de divergências."""
    pa = valida_pa(pa)
    tom = S.COD_TOM if tom is None else tom
    tol = d2(S.TOLERANCIA_ABS if tol_abs is None else tol_abs)
    tol_a = Decimal(str(S.TOLERANCIA_ALIQ if tol_aliq is None else tol_aliq))
    ini, fim = periodo(pa)

    decls = db.fetch(Q.sql_declaracoes(), [tom, tom, pa])
    esc = {norm_cnpj(r["cnpj"]): r for r in db.fetch(Q.sql_escrituracao(), [str(pa)])}
    pag = {r["decl_id"]: r for r in db.fetch(Q.sql_pagamento_declarado(), [S.COD_MUNIC_01100, pa])}
    parc_rows = db.fetch(Q.sql_parcelas(), [str(pa)])
    parc = {}
    for r in parc_rows:
        parc.setdefault(norm_cnpj(r["cnpj"]), []).append(r)

    divs, bloqueados, dec_por_cnpj = [], set(), {}

    def add(cod, cnpj, decl_id, vd, ve, cont=None, nota=""):
        divs.append(dict(codigo=cod, cnpj=cnpj, decl_id=decl_id, codigo_contribuinte=cont,
                         vr_declarado=None if vd is None else float(vd), vr_escriturado=None if ve is None else float(ve),
                         vr_diferenca=float((vd or 0) - (ve or 0)) if vd is not None or ve is not None else None, nota=nota))

    # --- D00: consistência interna da declaração ------------------------------------------------
    cand = []
    for d in decls:
        cnpj = norm_cnpj(d["cnpj_est"])
        if d["soma_03110"] is not None and d["total_02000"] is not None and abs(d2(d["soma_03110"]) - d2(d["total_02000"])) > tol:
            bloqueados.add(cnpj)
            add("D00", cnpj, d["decl_id"], d2(d["soma_03110"]), d2(d["total_02000"]), nota="Σ03110.ValorApuradoISS x 02000.ISS")
            continue
        dec_por_cnpj[cnpj] = d
        cand.append(cnpj)

    # --- cadastro (D01) e adesão (D08) em lotes ------------------------------------------------
    cadastro = {}
    precisam = [c for c in cand if c not in esc]
    for lote in lotes(precisam):
        for r in db.fetch(Q.sql_cadastro(len(lote)), lote):
            cadastro[norm_cnpj(r["cnpj"])] = r["cod"]
    codigo_de = {c: esc[c]["cod"] for c in esc}
    codigo_de.update(cadastro)

    # --- cruzamento FULL JOIN por CNPJ -----------------------------------------------------------
    for cnpj in sorted(set(dec_por_cnpj) | set(esc)):
        d, e = dec_por_cnpj.get(cnpj), esc.get(cnpj)
        cod = codigo_de.get(cnpj)
        if d and not e:
            if cnpj not in cadastro:
                add("D01", cnpj, d["decl_id"], d2(d["iss"]), None, nota="CNPJ sem cadastro em Contribu")
            elif d2(d["receita"]) > 0:
                add("D02", cnpj, d["decl_id"], d2(d["iss"]), None, cod, "Receita declarada ao município sem Bia de Simples")
        elif e and not d:
            if cnpj not in bloqueados:
                add("D03", cnpj, None, None, d2(e["iss"]), cod, "Bia de Simples sem declaração vigente na PA")
        elif d and e:
            if abs(d2(d["receita"]) - d2(e["receita"])) > tol:
                add("D04", cnpj, d["decl_id"], d2(d["receita"]), d2(e["receita"]), cod)
            if abs(d2(d["iss"]) - d2(e["iss"])) > tol:
                add("D05", cnpj, d["decl_id"], d2(d["iss"]), d2(e["iss"]), cod)
            if abs(Decimal(str(d["aliq"] or 0)) - Decimal(str(e["aliq"] or 0))) > tol_a:
                add("D06", cnpj, d["decl_id"], Decimal(str(d["aliq"] or 0)).quantize(Decimal("0.0001")),
                    Decimal(str(e["aliq"] or 0)).quantize(Decimal("0.0001")), cod, "valores em % (alíquota ponderada)")

    # --- D07: pagamento declarado (01100) x baixado em Parcelas ---------------------------------
    for cnpj, d in dec_por_cnpj.items():
        p = pag.get(d["decl_id"])
        linhas = [r for r in parc.get(cnpj, []) if r["vr_aut"] is not None]   # NULL = ainda não baixado (não é D07)
        if p and linhas:
            baixado = sum((d2(r["vr_aut"]) for r in linhas), Decimal(0))
            if abs(d2(p["princ"]) - baixado) > tol:
                add("D07", cnpj, d["decl_id"], d2(p["princ"]), baixado, codigo_de.get(cnpj), "01100.valorprinc x Parcelas.VrAutenticadoSuperSimples")

    # --- D08: optante sem adesão vigente ---------------------------------------------------------
    cods = {codigo_de[c]: c for c in (set(dec_por_cnpj) | set(esc)) if codigo_de.get(c)}
    hist = {}
    for lote in lotes(cods):
        for r in db.fetch(Q.sql_adesao(len(lote)), lote):
            hist.setdefault(r["cod"], []).append(r)
    for cod, cnpj in cods.items():
        if adesao_ativa(hist.get(cod), ini, fim) is False:
            d, e = dec_por_cnpj.get(cnpj), esc.get(cnpj)
            add("D08", cnpj, d["decl_id"] if d else None, d2(d["iss"]) if d else None, d2(e["iss"]) if e else None, cod,
                f"PA {pa} fora do período de adesão em SuperSimples")

    ordem = {k: i for i, k in enumerate(C.DIVERGENCIAS)}
    divs.sort(key=lambda x: (x["cnpj"], ordem[x["codigo"]]))
    por_codigo = {k: 0 for k in C.DIVERGENCIAS}
    for x in divs:
        por_codigo[x["codigo"]] += 1
    return dict(pa=pa, tom=tom, tolerancia_abs=float(tol), tolerancia_aliq=float(tol_a),
                declaracoes_vigentes=len(decls), declaracoes_confrontadas=len(cand), escrituradas=len(esc),
                contribuintes_com_divergencia=len({x["cnpj"] for x in divs}), total_divergencias=len(divs),
                por_codigo=por_codigo, divergencias=divs)


def persiste(res: dict, usuario: str) -> int:
    """Grava ConfrontoExecucao + ConfrontoDivergencia numa transação única (exige escrita liberada)."""
    with db.tx() as cur:
        eid = db.insert_id(cur, "ConfrontoExecucao", dict(
            Pa=res["pa"], DtExecucao=datetime.now().isoformat(sep=" ", timespec="seconds"), Usuario=usuario,
            ToleranciaAbs=res["tolerancia_abs"], Situacao="A"))
        for x in res["divergencias"]:
            cur.execute(
                f"INSERT INTO {db.T('ConfrontoDivergencia')} (ExecucaoId, DeclaracaoId, Cnpj, CodigoContribuinte, Codigo, "
                f"VrDeclarado, VrEscriturado, Tratamento, Justificativa) VALUES (?,?,?,?,?,?,?,?,?)",
                [eid, x["decl_id"], x["cnpj"], x["codigo_contribuinte"], x["codigo"], x["vr_declarado"], x["vr_escriturado"], "P", x["nota"]])
    return eid


# --------------------------------------------------------------------------- baixa / estorno
def plano_baixa(pa) -> dict:
    """Simula a baixa: o que seria gravado em Parcelas.VrAutenticadoSuperSimples (UPDATE absoluto, idempotente)."""
    pa = valida_pa(pa)
    decls = db.fetch(Q.sql_declaracoes(), [S.COD_TOM, S.COD_TOM, pa])
    pag = {r["decl_id"]: r for r in db.fetch(Q.sql_pagamento_declarado(), [S.COD_MUNIC_01100, pa])}
    parc = {}
    for r in db.fetch(Q.sql_parcelas(), [str(pa)]):
        parc.setdefault(norm_cnpj(r["cnpj"]), []).append(r)
    itens = []
    for d in decls:
        cnpj = norm_cnpj(d["cnpj_est"])
        p = pag.get(d["decl_id"])
        if not p:
            continue
        valor = d2(p["princ"])
        ps = parc.get(cnpj, [])
        if d["soma_03110"] is not None and d["total_02000"] is not None and abs(d2(d["soma_03110"]) - d2(d["total_02000"])) > d2(S.TOLERANCIA_ABS):
            acao, pid, atual = "bloqueada_d00", None, None   # carga inconsistente: não baixa declaração com D00
        elif not ps:
            acao, pid, atual = "sem_parcela", None, None
        elif len(ps) > 1:
            acao, pid, atual = "ambigua", None, None   # mais de uma parcela: não adivinha, vai para tratamento manual
        else:
            pid, atual = ps[0]["parcela_id"], ps[0]["vr_aut"]
            if atual is None:
                acao = "gravar"                      # ainda não baixado
            elif d2(atual) == valor:
                acao = "igual"                       # já está correto (reexecutar a baixa não muda nada)
            else:
                acao = "sobrescrever"                # já há valor diferente: só grava com confirmação explícita
        itens.append(dict(cnpj=cnpj, decl_id=d["decl_id"], parcela_id=pid,
                          valor_atual=None if atual is None else float(d2(atual)), valor_novo=float(valor), acao=acao))
    resumo = {}
    for i in itens:
        resumo[i["acao"]] = resumo.get(i["acao"], 0) + 1
    return dict(pa=pa, resumo=resumo, itens=itens)


def execucao_aberta(pa: int):
    r = db.fetch(f"SELECT Id, Situacao FROM {db.T('ConfrontoExecucao')} WHERE Pa = ? ORDER BY Id DESC", [pa])
    return r[0] if r else None


def baixar(pa, usuario: str, sobrescrever: bool = False) -> dict:
    pa = valida_pa(pa)
    ex = execucao_aberta(pa)
    if not ex:
        raise ValueError("Execute e grave o confronto desta PA antes da baixa.")
    if ex["Situacao"] == "B":
        raise ValueError("A última execução desta PA já está baixada. Estorne antes de baixar novamente.")
    plano = plano_baixa(pa)
    agora = datetime.now().isoformat(sep=" ", timespec="seconds")
    n = 0
    with db.tx() as cur:
        for i in plano["itens"]:
            if i["acao"] != "gravar" and not (sobrescrever and i["acao"] == "sobrescrever"):
                continue
            cur.execute(f"INSERT INTO {db.T('ConfrontoBaixa')} (ExecucaoId, ParcelaId, ValorAnterior, ValorGravado, Usuario, DtBaixa) "
                        f"VALUES (?,?,?,?,?,?)", [ex["Id"], i["parcela_id"], i["valor_atual"], i["valor_novo"], usuario, agora])
            cur.execute(f"UPDATE {db.T('Parcelas')} SET VrAutenticadoSuperSimples = ? WHERE Id = ?", [i["valor_novo"], i["parcela_id"]])
            n += 1
        cur.execute(f"UPDATE {db.T('ConfrontoExecucao')} SET Situacao = 'B' WHERE Id = ?", [ex["Id"]])
    return dict(pa=pa, execucao_id=ex["Id"], parcelas_gravadas=n, resumo=plano["resumo"])


def estornar(pa, usuario: str) -> dict:
    pa = valida_pa(pa)
    ex = execucao_aberta(pa)
    if not ex or ex["Situacao"] != "B":
        raise ValueError("Não há baixa ativa para estornar nesta PA.")
    agora = datetime.now().isoformat(sep=" ", timespec="seconds")
    itens = db.fetch(f"SELECT Id, ParcelaId, ValorAnterior FROM {db.T('ConfrontoBaixa')} WHERE ExecucaoId = ? AND DtEstorno IS NULL", [ex["Id"]])
    with db.tx() as cur:
        for b in itens:   # devolve o valor que estava antes da baixa (não zera cegamente)
            cur.execute(f"UPDATE {db.T('Parcelas')} SET VrAutenticadoSuperSimples = ? WHERE Id = ?", [b["ValorAnterior"], b["ParcelaId"]])
            cur.execute(f"UPDATE {db.T('ConfrontoBaixa')} SET DtEstorno = ? WHERE Id = ?", [agora, b["Id"]])
        cur.execute(f"UPDATE {db.T('ConfrontoExecucao')} SET Situacao = 'A' WHERE Id = ?", [ex["Id"]])
    return dict(pa=pa, execucao_id=ex["Id"], parcelas_estornadas=len(itens))
