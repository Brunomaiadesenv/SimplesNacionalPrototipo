"""Ações do fiscal sobre cada divergência (todas exigem uma execução GRAVADA do confronto)."""
import smtplib
from datetime import date, datetime, timedelta
from decimal import Decimal
from email.message import EmailMessage

from . import cadastros, colunas as C, db, mapeamento as M
from .config import S
from .confronto import d2

ACOES = {"D00": "alerta", "D01": "eventual", "D02": "notificar", "D03": "notificar", "D06": "notificar",
         "D07": "notificar", "D08": "notificar", "D04": "calculo", "D05": "calculo"}


def carrega(div_id: int) -> dict:
    r = db.fetch(f"SELECT d.Id, d.ExecucaoId, d.DeclaracaoId, d.Cnpj, d.CodigoContribuinte, d.Codigo, d.VrDeclarado, d.VrEscriturado, "
                 f"d.Tratamento, d.Justificativa, e.Pa FROM {db.T('ConfrontoDivergencia')} d "
                 f"JOIN {db.T('ConfrontoExecucao')} e ON e.Id = d.ExecucaoId WHERE d.Id = ?", [div_id])
    if not r:
        raise ValueError("Divergência não encontrada.")
    return r[0]


def _exige(d: dict, acao: str):
    if ACOES.get(d["Codigo"]) != acao:
        raise ValueError(f"A divergência {d['Codigo']} não admite esta ação.")


def _marca(cur, div_ids, tratamento, nota=None):
    for i in div_ids:
        cur.execute(f"UPDATE {db.T('ConfrontoDivergencia')} SET Tratamento = ?, Justificativa = COALESCE(?, Justificativa) WHERE Id = ?",
                    [tratamento, nota, i])


def _acao(cur, d: dict, tipo: str, ref: str, usuario: str, detalhe: str):
    db.ins(cur, "ConfrontoAcao", dict(DivergenciaId=d["Id"], ExecucaoId=d["ExecucaoId"], Tipo=tipo, Referencia=ref, Usuario=usuario,
                                      DtAcao=datetime.now().isoformat(sep=" ", timespec="seconds"), Detalhe=detalhe[:500]))


def _ja_feito(d: dict, tipo: str):
    """Evita repetir a ação para o mesmo contribuinte e PA (em qualquer execução)."""
    r = db.fetch(f"SELECT a.Referencia FROM {db.T('ConfrontoAcao')} a JOIN {db.T('ConfrontoExecucao')} e ON e.Id = a.ExecucaoId "
                 f"JOIN {db.T('ConfrontoDivergencia')} x ON x.Id = a.DivergenciaId WHERE a.Tipo = ? AND e.Pa = ? AND x.Cnpj = ? "
                 + ("AND x.Codigo = ?" if tipo == "NOTIFICACAO" else ""),
                 [tipo, d["Pa"], d["Cnpj"]] + ([d["Codigo"]] if tipo == "NOTIFICACAO" else []))
    return r[0]["Referencia"] if r else None


# ============================================================================== D01 — cadastrar como Eventual
def cadastrar_eventual(div_id: int, razao_social: str, usuario: str, extras: dict | None = None) -> dict:
    d = carrega(div_id)
    _exige(d, "eventual")
    if cadastros.busca_por_documento(d["Cnpj"]):
        raise ValueError("Este CNPJ já consta em dbo.Contribu. Reexecute o confronto.")
    dados = dict(cnpj=d["Cnpj"], nome=razao_social, simples="S", **(extras or {}))
    with db.tx() as cur:
        # CNPJ vem da declaração do Simples (Receita Federal): não revalida dígito verificador.
        cod = cadastros.cria_contribuinte(dados, prefixo="5", validar_dv=False, cur=cur)
        _acao(cur, d, "EVENTUAL", cod, usuario, f"Cadastrado como Eventual a partir da declaração {d['DeclaracaoId']}")
        _marca(cur, [d["Id"]], "R", f"Cadastrado como Eventual, código {cod}")
    return dict(codigo=cod, cnpj=d["Cnpj"])


# ============================================================================== notificação
def _brl(v):
    return "—" if v is None else "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


MODELOS = {
    "D02": ("Declaração do Simples Nacional sem escrituração no ISSWEB",
            "Consta na declaração PGDAS-D da competência {pa} receita com ISS devido a este Município de {declarado}, "
            "porém não foi localizada escrituração de serviços como optante do Simples Nacional no sistema ISSWEB."),
    "D03": ("Escrituração como optante do Simples Nacional sem declaração PGDAS-D",
            "Foi localizada escrituração no ISSWEB da competência {pa} como optante do Simples Nacional, com ISS de {escriturado}, "
            "mas não consta declaração PGDAS-D vigente para esta competência."),
    "D06": ("Divergência de alíquota entre o PGDAS-D e o ISSWEB",
            "A alíquota de ISS apurada no PGDAS-D da competência {pa} ({declarado}%) difere da alíquota escriturada no ISSWEB ({escriturado}%)."),
    "D07": ("Divergência entre o pagamento declarado no PGDAS-D e o valor baixado",
            "O valor do ISS destinado a este Município no PGDAS-D da competência {pa} ({declarado}) difere do valor autenticado/baixado "
            "no sistema ({escriturado}), diferença de {diferenca}."),
    "D08": ("Contribuinte sem adesão vigente ao Simples Nacional na competência",
            "A competência {pa} está fora do período de adesão ao Simples Nacional registrado para este contribuinte, embora "
            "conste declaração/escrituração como optante."),
}


def _pa_fmt(pa):
    return f"{str(pa)[4:]}/{str(pa)[:4]}"


def previa_notificacao(div_id: int) -> dict:
    d = carrega(div_id)
    _exige(d, "notificar")
    cont = cadastros.busca_por_documento(d["Cnpj"]) or {}
    assunto, tpl = MODELOS[d["Codigo"]]
    if d["Codigo"] == "D06":
        decl, esc, dif = (f"{float(d['VrDeclarado'] or 0):.2f}".replace(".", ","), f"{float(d['VrEscriturado'] or 0):.2f}".replace(".", ","), "")
    else:
        decl, esc, dif = _brl(d["VrDeclarado"]), _brl(d["VrEscriturado"]), _brl(abs(float(d["VrDeclarado"] or 0) - float(d["VrEscriturado"] or 0)))
    fato = tpl.format(pa=_pa_fmt(d["Pa"]), declarado=decl, escriturado=esc, diferenca=dif)
    prazo = date.today() + timedelta(days=S.DIAS_PRAZO_NOTIF)
    nome = cont.get("nome") or f"CNPJ {d['Cnpj']}"
    texto = (f"NOTIFICAÇÃO FISCAL — SIMPLES NACIONAL\n\nContribuinte: {nome}\nCNPJ: {d['Cnpj']}"
             + (f"\nCódigo: {cont['codigo']}" if cont.get("codigo") else "") + f"\nCompetência: {_pa_fmt(d['Pa'])}\nReferência: divergência {d['Codigo']} — {C.DIVERGENCIAS[d['Codigo']]['nome']}\n\n"
             f"Fica o contribuinte NOTIFICADO de que, no confronto realizado pela Fiscalização Tributária entre o PGDAS-D e o ISSWEB:\n\n{fato}\n\n"
             f"Solicita-se que, no prazo de {S.DIAS_PRAZO_NOTIF} dias (até {prazo.strftime('%d/%m/%Y')}), o contribuinte apresente esclarecimentos "
             f"e a documentação que comprove os valores declarados, ou regularize sua situação junto à Fiscalização.\n\n"
             f"O não atendimento poderá ensejar o lançamento de ofício do crédito tributário e a aplicação das penalidades previstas na legislação municipal.")
    return dict(codigo=d["Codigo"], assunto=assunto, texto=texto, destinatario=cont.get("email"), contribuinte=nome,
                ja_enviada=_ja_feito(d, "NOTIFICACAO"), prazo=prazo.isoformat())


def _envia_email(destino: str, assunto: str, texto: str):
    smtp = getattr(S, "SMTP", {}) or {}
    if not (smtp.get("host") and destino):
        return None
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, smtp.get("remetente") or smtp.get("usuario"), destino
    msg.set_content(texto)
    with smtplib.SMTP(smtp["host"], smtp["porta"], timeout=15) as s:
        s.starttls()
        if smtp.get("usuario"):
            s.login(smtp["usuario"], smtp["senha"])
        s.send_message(msg)
    return "E-mail"


def enviar_notificacao(div_id: int, assunto: str, texto: str, usuario: str) -> dict:
    """Método único de envio. Registra a notificação (SimplesNotificacao) e tenta os canais configurados.
    Ponto de extensão: acrescentar aqui o canal DTE (Domicílio Tributário Eletrônico) quando o módulo existir."""
    d = carrega(div_id)
    _exige(d, "notificar")
    assunto, texto = (assunto or "").strip()[:200], (texto or "").strip()
    if len(texto) < 20:
        raise ValueError("O texto da notificação está vazio ou muito curto.")
    if _ja_feito(d, "NOTIFICACAO"):
        raise ValueError("Já existe notificação deste tipo para este contribuinte nesta competência.")
    cont = cadastros.busca_por_documento(d["Cnpj"]) or {}
    canal, situacao, erro = "Registro interno", "E", None       # E = emitida (aguardando ciência)
    try:
        enviado = _envia_email(cont.get("email"), assunto, texto)
        if enviado:
            canal, situacao = enviado, "V"                       # V = enviada
    except Exception as e:
        erro, situacao = str(e)[:300], "F"                       # F = falha no envio (registro mantido)
    hoje = date.today()
    with db.tx() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {db.T('SimplesNotificacao')} WHERE Ano = ?", [hoje.year])
        seq = int(cur.fetchone()[0]) + 1
        numero = f"{seq:05d}/{hoje.year}"
        db.ins(cur, "SimplesNotificacao", dict(
            Numero=numero, Ano=hoje.year, DivergenciaId=d["Id"], ExecucaoId=d["ExecucaoId"], CodigoContribuinte=d["CodigoContribuinte"] or cont.get("codigo"),
            Cnpj=d["Cnpj"], Pa=d["Pa"], Codigo=d["Codigo"], Assunto=assunto, Texto=texto, Canal=canal, Situacao=situacao,
            DtEmissao=datetime.now().isoformat(sep=" ", timespec="seconds"), DtPrazo=(hoje + timedelta(days=S.DIAS_PRAZO_NOTIF)).isoformat(),
            Usuario=usuario, Erro=erro))
        _acao(cur, d, "NOTIFICACAO", numero, usuario, f"{canal} · {assunto}")
        _marca(cur, [d["Id"]], "N", f"Notificação {numero}")
    return dict(numero=numero, canal=canal, situacao=situacao, erro=erro)


def lista_notificacoes(div_id: int | None = None):
    rows = db.fetch(f"SELECT Id, Numero, Cnpj, Pa, Codigo, Assunto, Canal, Situacao, DtEmissao, DtPrazo, Usuario FROM {db.T('SimplesNotificacao')}"
                    + (" WHERE DivergenciaId = ?" if div_id else "") + " ORDER BY Id DESC", [div_id] if div_id else [])
    for r in rows:
        r["DtEmissao"] = str(r["DtEmissao"])[:19]
        r["DtPrazo"] = str(r["DtPrazo"])[:10]
    return rows[:300]


def notificacao(nid: int):
    r = db.fetch(f"SELECT * FROM {db.T('SimplesNotificacao')} WHERE Id = ?", [nid])
    if not r:
        raise ValueError("Notificação não encontrada.")
    return r[0]


# ============================================================================== D04/D05 — gerar cálculo
def _linhas_calculo(d: dict):
    return db.fetch(f"SELECT Id, Codigo, VrDeclarado, VrEscriturado, DeclaracaoId FROM {db.T('ConfrontoDivergencia')} "
                    f"WHERE ExecucaoId = ? AND Cnpj = ? AND Codigo IN ('D04','D05')", [d["ExecucaoId"], d["Cnpj"]])


def previa_calculo(div_id: int) -> dict:
    d = carrega(div_id)
    _exige(d, "calculo")
    linhas = {r["Codigo"]: r for r in _linhas_calculo(d)}
    prop = dict(cnpj=d["Cnpj"], pa=d["Pa"], divergencias=[r["Id"] for r in linhas.values()], ja_gerado=_ja_feito(d, "CALCULO"),
                modulo=S.MODULO_CALCULO, grupo=S.GRUPO_CALCULO, habilitado=bool(S.CALCULO_HABILITADO))
    cont = cadastros.busca_por_documento(d["Cnpj"])
    prop["contribuinte"] = cont
    if "D05" in linhas:
        r = linhas["D05"]
        dif = d2(r["VrDeclarado"]) - d2(r["VrEscriturado"])
        prop.update(criterio="Diferença de ISS (declarado − escriturado)", base=float(d2(r["VrDeclarado"])), valor=float(max(dif, Decimal(0))), aliquota=None)
        if "D04" in linhas:
            prop["criterio"] += "; D04 e D05 geram um único cálculo"
    else:
        r = linhas["D04"]
        dif_rec = d2(r["VrDeclarado"]) - d2(r["VrEscriturado"])
        t = db.fetch(f"SELECT SUM(Valor) AS rec, SUM(ValorApuradoISS) AS iss FROM {db.tb('PGDASD03110', 'x')} WHERE x.idPGDASD00000 = ? AND x.CodTOM = ?",
                     [r["DeclaracaoId"], S.COD_TOM])[0]
        aliq = (Decimal(str(t["iss"] or 0)) / Decimal(str(t["rec"]))) * 100 if t["rec"] else Decimal(0)
        prop.update(criterio="Receita não escriturada × alíquota efetiva declarada", base=float(max(dif_rec, Decimal(0))),
                    aliquota=float(aliq.quantize(Decimal("0.0001"))), valor=float((max(dif_rec, Decimal(0)) * aliq / 100).quantize(Decimal("0.01"))))
    prop["vencimento"] = (date.today() + timedelta(days=S.DIAS_VENCIMENTO)).isoformat()
    prop["valor"] = round(prop["valor"], 2)
    if prop["valor"] <= 0:
        prop["bloqueio"] = "O valor declarado não é maior que o escriturado: não há ISS a lançar."
    elif prop["ja_gerado"]:
        prop["bloqueio"] = f"Cálculo já gerado para este contribuinte e competência (nº {prop['ja_gerado']})."
    elif not cont:
        prop["bloqueio"] = "Contribuinte não cadastrado em dbo.Contribu (veja D01)."
    elif not S.CALCULO_HABILITADO:
        prop["bloqueio"] = "Geração de cálculo desabilitada em Configuração (confirme o mapeamento de Calc1/Parcelam/Parcelas antes de habilitar)."
    return prop


def gerar_calculo(div_id: int, usuario: str) -> dict:
    d = carrega(div_id)
    p = previa_calculo(div_id)
    if p.get("bloqueio"):
        raise ValueError(p["bloqueio"])
    cod = p["contribuinte"]["codigo"]
    c1, pm, pa_ = M.CALC1, M.PARCELAM, M.PARCELAS
    hoje = date.today().isoformat()
    with db.tx() as cur:
        cur.execute(f"SELECT MAX({c1['numero']}) FROM {db.T(c1['tabela'])}{db.lock_hint()}")
        ncalc = int(cur.fetchone()[0] or 0) + 1
        cur.execute(f"SELECT MAX(CAST({pm['numero']} AS BIGINT)) FROM {db.T(pm['tabela'])}{db.lock_hint()}")
        nparc = str(int(cur.fetchone()[0] or 0) + 1)
        v = {c1["numero"]: ncalc, c1["contribuinte"]: cod, c1["competencia"]: str(d["Pa"]), c1["modulo"]: S.MODULO_CALCULO, c1["grupo"]: S.GRUPO_CALCULO,
             c1["base"]: p["base"], c1["valor"]: p["valor"], c1["data"]: hoje, c1["usuario"]: usuario, c1["origem"]: M.ORIGEM_CALCULO}
        v.update(M.CALC1_PADRAO)
        db.ins(cur, c1["tabela"], {k: x for k, x in v.items() if k})
        v = {pm["numero"]: nparc, pm["calculo"]: ncalc, pm["contribuinte"]: cod, pm["parcela"]: "01", pm["valor"]: p["valor"], pm["vencimento"]: p["vencimento"]}
        v.update(M.PARCELAM_PADRAO)
        db.ins(cur, pm["tabela"], {k: x for k, x in v.items() if k})
        v = {pa_["contribuinte"]: cod, pa_["competencia"]: str(d["Pa"]), pa_["parcelamento"]: nparc, pa_["parcela"]: "01", pa_["valor"]: p["valor"],
             pa_["vencimento"]: p["vencimento"], pa_["emissao"]: None, pa_["qtd"]: 0}
        v.update(M.PARCELAS_PADRAO)
        db.ins(cur, pa_["tabela"], {k: x for k, x in v.items() if k})
        _acao(cur, d, "CALCULO", str(ncalc), usuario, f"Parcelamento {nparc}, parcela 01, valor {p['valor']:.2f}, vencimento {p['vencimento']}")
        _marca(cur, p["divergencias"], "L", f"Cálculo {ncalc} / parcelamento {nparc}")
    return dict(calculo=ncalc, parcelamento=nparc, parcela="01", valor=p["valor"], vencimento=p["vencimento"])
