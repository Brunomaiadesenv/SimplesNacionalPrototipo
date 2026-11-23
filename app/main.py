import csv
import io
import secrets
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse

from . import acoes, auth as A, cadastros, carga, colunas as C, confronto, db, queries as Q, settings as ST
from .auth import admin, auth
from .config import S

app = FastAPI(title="Fiscalização do Simples Nacional — ISS Digital", docs_url="/docs")
STATIC = Path(__file__).parent / "static"


ST.aplica()      # carrega data/config.json (ou .env) para o objeto S


# ---------------------------------------------------------------- registro de uso
def log_uso(ip, usuario, endpoint, detalhe, linhas, ms, status):
    try:
        c = sqlite3.connect(S.USO_DB)
        c.execute("CREATE TABLE IF NOT EXISTS uso(ts TEXT, ip TEXT, usuario TEXT, endpoint TEXT, detalhe TEXT, linhas INT, ms INT, status TEXT)")
        c.execute("INSERT INTO uso VALUES (?,?,?,?,?,?,?,?)",
                  (datetime.now().isoformat(timespec="seconds"), ip, usuario, endpoint, detalhe, linhas, ms, status))
        c.commit(); c.close()
    except Exception:
        pass


def executa(request: Request, usuario: str, endpoint: str, detalhe: str, fn):
    """Trava de concorrência + mapeamento de erros + log de uso (mesmo padrão do protótipo de auditoria)."""
    t0, status, linhas = time.time(), "ok", 0
    try:
        with db.slot():
            res = fn()
        linhas = len(res) if isinstance(res, list) else 0
        return res
    except db.Ocupado:
        status = "ocupado"
        raise HTTPException(429, "Servidor ocupado. Tente novamente em instantes.")
    except db.EscritaBloqueada:
        status = "bloqueado"
        raise HTTPException(403, "Gravação bloqueada neste ambiente (ESCRITA_PERMITIDA=false). A consulta/simulação continua disponível.")
    except ValueError as e:      # regra de negócio / validação
        status = "recusado"
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        status = "erro"
        msg = str(e)
        if "timeout" in msg.lower() or "HYT00" in msg:
            raise HTTPException(504, f"A consulta excedeu {S.TIMEOUT_CONSULTA}s e foi cancelada.")
        raise HTTPException(500, f"Erro na operação: {msg[:300]}")
    finally:
        log_uso(request.client.host if request.client else "", usuario, endpoint, detalhe, linhas, int((time.time() - t0) * 1000), status)


def _no_periodo(pa: int) -> bool:
    ini, fim = S.PERIODO_INI, S.PERIODO_FIM
    return not ((ini and pa < int(ini)) or (fim and pa > int(fim)))


def pa_ok(pa: int) -> int:
    try:
        pa = confronto.valida_pa(pa)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not _no_periodo(pa):
        raise HTTPException(400, f"Competência fora do período ativo do cliente ({S.PERIODO_INI or '…'} a {S.PERIODO_FIM or '…'}). Ajuste em Configuração.")
    return pa


# ---------------------------------------------------------------- rotas
@app.get("/", include_in_schema=False)
def home(request: Request):
    if not A.le_token(request.cookies.get(A.COOKIE)):
        return RedirectResponse("/login", status_code=302)
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if A.le_token(request.cookies.get(A.COOKIE)):
        return RedirectResponse("/", status_code=302)
    return FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-store"})


@app.post("/api/login")
async def login(request: Request, response: Response, dados: dict = Body(...)):
    ip = request.client.host if request.client else ""
    u = await run_in_threadpool(lambda: A.autentica(str(dados.get("usuario") or "")[:60], str(dados.get("senha") or "")[:60], ip))
    response.set_cookie(A.COOKIE, A.emite_token(u), httponly=True, samesite="lax", secure=S.COOKIE_SEGURO, max_age=S.SESSAO_HORAS * 3600, path="/")
    log_uso(ip, u["nome"], "login", "", 0, 0, "ok")
    return {"ok": True, "usuario": u["nome"], "adm": u["adm"]}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(A.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/sessao")
def sessao(s: dict = Depends(A.sessao)):
    return {"usuario": s["nome"], "completo": s["completo"], "adm": s["adm"]}


@app.get("/api/publico")
def publico():
    return ST.publico()


@app.get("/api/brasao", include_in_schema=False)
def brasao():
    if ST.BRASAO.exists():
        tipo = ST.BRASAO_TIPO.read_text().strip() if ST.BRASAO_TIPO.exists() else "image/png"
        return Response(ST.BRASAO.read_bytes(), media_type=tipo, headers={"Cache-Control": "no-cache"})
    return FileResponse(STATIC / "brasao.svg", media_type="image/svg+xml")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi import Response
    return Response(status_code=204)


@app.get("/api/config")
def config(_: str = Depends(auth)):
    return {"modo": S.DB_MODE, "municipio": S.MUNICIPIO_NOME, "cliente": S.CLIENTE, "periodo_ini": S.PERIODO_INI, "periodo_fim": S.PERIODO_FIM,
            "modulo_calculo": S.MODULO_CALCULO, "grupo_calculo": S.GRUPO_CALCULO, "calculo_habilitado": S.CALCULO_HABILITADO, "dias_prazo": S.DIAS_PRAZO_NOTIF, "cod_tom": S.COD_TOM, "escrita": S.ESCRITA_PERMITIDA,
            "tolerancia_abs": S.TOLERANCIA_ABS, "tolerancia_aliq": S.TOLERANCIA_ALIQ, "max_erro_carga_pct": S.MAX_ERRO_CARGA_PCT,
            "divergencias": C.DIVERGENCIAS, "tratamentos": C.TRATAMENTOS, "tam_pagina_max": S.TAM_PAGINA_MAX}


@app.get("/api/competencias")
async def competencias(request: Request, user: str = Depends(auth)):
    rows = await run_in_threadpool(lambda: executa(request, user, "competencias", "", lambda: db.fetch(Q.sql_competencias())))
    return {"competencias": [r["pa"] for r in rows if _no_periodo(int(r["pa"]))]}


# ---- confronto -------------------------------------------------------------------------------
@app.post("/api/confronto/executar")
async def executar(request: Request, pa: int, gravar: bool = False, user: str = Depends(auth)):
    """Roda o confronto. Sem 'gravar' é simulação (somente leitura). Com 'gravar' cria ConfrontoExecucao + Divergencias."""
    pa = pa_ok(pa)
    t0 = time.time()

    def run():
        res = confronto.calcula(pa)
        res["execucao_id"] = confronto.persiste(res, user) if gravar else None
        return res

    res = await run_in_threadpool(lambda: executa(request, user, "confronto", f"pa={pa} gravar={gravar}", run))
    res["persistido"] = bool(res["execucao_id"])
    res["ms"] = int((time.time() - t0) * 1000)
    return res


@app.get("/api/execucoes")
async def execucoes(request: Request, pa: int | None = None, user: str = Depends(auth)):
    sql = (f"SELECT e.Id, e.Pa, e.DtExecucao, e.Usuario, e.ToleranciaAbs, e.Situacao, "
           f"(SELECT COUNT(*) FROM {db.T('ConfrontoDivergencia')} d WHERE d.ExecucaoId = e.Id) AS divergencias "
           f"FROM {db.T('ConfrontoExecucao')} e" + (" WHERE e.Pa = ?" if pa else "") + " ORDER BY e.Id DESC")
    rows = await run_in_threadpool(lambda: executa(request, user, "execucoes", f"pa={pa}", lambda: db.fetch(sql, [pa] if pa else [])))
    for r in rows:
        r["DtExecucao"] = str(r["DtExecucao"])[:19]
        r["ToleranciaAbs"] = float(r["ToleranciaAbs"])
        r["SituacaoNome"] = {"A": "Aberta", "B": "Baixada", "F": "Fechada"}.get(r["Situacao"], r["Situacao"])
    return {"itens": rows}


@app.get("/api/divergencias")
async def divergencias(request: Request, execucao_id: int, codigo: str | None = None, tratamento: str | None = None,
                       cnpj: str | None = None, pagina: int = Query(1, ge=1), tamanho: int = Query(100, ge=10),
                       user: str = Depends(auth)):
    tamanho = min(tamanho, S.TAM_PAGINA_MAX)
    where, p = ["d.ExecucaoId = ?"], [execucao_id]
    if codigo:
        if codigo not in C.DIVERGENCIAS:
            raise HTTPException(400, "Código de divergência inválido.")
        where.append("d.Codigo = ?"); p.append(codigo)
    if tratamento:
        if tratamento not in C.TRATAMENTOS:
            raise HTTPException(400, "Tratamento inválido.")
        where.append("d.Tratamento = ?"); p.append(tratamento)
    if cnpj:
        dig = "".join(ch for ch in cnpj if ch.isdigit())
        if not dig:
            raise HTTPException(400, "Informe apenas números no CNPJ.")
        where.append("d.Cnpj LIKE ?"); p.append(dig.zfill(14) if len(dig) >= 14 else dig + "%")
    base = (f"SELECT d.Id, d.DeclaracaoId, d.Cnpj, d.CodigoContribuinte, d.Codigo, d.VrDeclarado, d.VrEscriturado, "
            f"d.Tratamento, d.Justificativa FROM {db.T('ConfrontoDivergencia')} d WHERE " + " AND ".join(where))
    sql, params = db.pagina(base, p, "d.Cnpj, d.Codigo", (pagina - 1) * tamanho, tamanho + 1)
    rows = await run_in_threadpool(lambda: executa(request, user, "divergencias", f"exec={execucao_id} cod={codigo}", lambda: db.fetch(sql, params)))
    tem = len(rows) > tamanho
    itens = []
    for r in rows[:tamanho]:
        vd, ve = r["VrDeclarado"], r["VrEscriturado"]
        itens.append(dict(id=r["Id"], decl_id=r["DeclaracaoId"], cnpj=r["Cnpj"], codigo_contribuinte=r["CodigoContribuinte"],
                          codigo=r["Codigo"], nome=C.DIVERGENCIAS[r["Codigo"]]["nome"], gravidade=C.DIVERGENCIAS[r["Codigo"]]["gravidade"],
                          vr_declarado=None if vd is None else float(vd), vr_escriturado=None if ve is None else float(ve),
                          vr_diferenca=round(float(vd or 0) - float(ve or 0), 2) if (vd is not None or ve is not None) else None,
                          tratamento=r["Tratamento"], tratamento_nome=C.TRATAMENTOS.get(r["Tratamento"]), nota=r["Justificativa"]))
    return {"itens": itens, "pagina": pagina, "tamanho": tamanho, "tem_proxima": tem}


@app.patch("/api/divergencias/{div_id}/tratamento")
async def tratar(request: Request, div_id: int, dados: dict = Body(...), user: str = Depends(auth)):
    t = dados.get("tratamento")
    just = (dados.get("justificativa") or "").strip()
    if t not in ("P", "J", "N"):      # L e R só são gravados pelas ações (cálculo / cadastro)
        raise HTTPException(400, "Tratamento inválido (P, J ou N).")
    if t == "J" and len(just) < 5:
        raise HTTPException(400, "Informe a justificativa (mínimo 5 caracteres) para marcar como Justificada.")

    def run():
        with db.tx() as cur:
            cur.execute(f"UPDATE {db.T('ConfrontoDivergencia')} SET Tratamento = ?, Justificativa = COALESCE(?, Justificativa) WHERE Id = ?",
                        [t, just or None, div_id])
            if cur.rowcount == 0:
                raise ValueError("Divergência não encontrada.")
        return []

    await run_in_threadpool(lambda: executa(request, user, "tratar", f"div={div_id} t={t}", run))
    return {"ok": True}


@app.get("/api/resumo")
async def resumo(request: Request, execucao_id: int, user: str = Depends(auth)):
    sql = (f"SELECT Codigo, Tratamento, COUNT(*) AS n, COUNT(DISTINCT Cnpj) AS contrib FROM {db.T('ConfrontoDivergencia')} "
           f"WHERE ExecucaoId = ? GROUP BY Codigo, Tratamento")
    rows = await run_in_threadpool(lambda: executa(request, user, "resumo", f"exec={execucao_id}", lambda: db.fetch(sql, [execucao_id])))
    por_cod, por_trat = {k: 0 for k in C.DIVERGENCIAS}, {k: 0 for k in C.TRATAMENTOS}
    for r in rows:
        por_cod[r["Codigo"]] += r["n"]; por_trat[r["Tratamento"]] += r["n"]
    return {"total": sum(por_cod.values()), "por_codigo": por_cod, "por_tratamento": por_trat}


@app.get("/api/exportar.csv")
async def exportar(request: Request, execucao_id: int, user: str = Depends(auth)):
    sql = (f"SELECT d.Cnpj, d.CodigoContribuinte, d.Codigo, d.VrDeclarado, d.VrEscriturado, d.Tratamento, d.Justificativa "
           f"FROM {db.T('ConfrontoDivergencia')} d WHERE d.ExecucaoId = ? ORDER BY d.Cnpj, d.Codigo")
    rows = await run_in_threadpool(lambda: executa(request, user, "exportar", f"exec={execucao_id}", lambda: db.fetch(sql, [execucao_id])))

    def gera():
        buf = io.StringIO(); w = csv.writer(buf, delimiter=";")
        buf.write("﻿")
        w.writerow(["cnpj", "codigo_contribuinte", "codigo", "divergencia", "vr_declarado", "vr_escriturado", "diferenca", "tratamento", "observacao"])
        yield buf.getvalue(); buf.seek(0); buf.truncate()
        fmt = lambda v: "" if v is None else f"{float(v):.2f}".replace(".", ",")
        for r in rows:
            dif = None if r["VrDeclarado"] is None and r["VrEscriturado"] is None else float(r["VrDeclarado"] or 0) - float(r["VrEscriturado"] or 0)
            w.writerow([r["Cnpj"], r["CodigoContribuinte"] or "", r["Codigo"], C.DIVERGENCIAS[r["Codigo"]]["nome"], fmt(r["VrDeclarado"]),
                        fmt(r["VrEscriturado"]), fmt(dif), C.TRATAMENTOS.get(r["Tratamento"]), r["Justificativa"] or ""])
            yield buf.getvalue(); buf.seek(0); buf.truncate()

    return StreamingResponse(gera(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename=divergencias_simples_exec{execucao_id}.csv"})


# ---- análise do contribuinte (as 3 grades) ---------------------------------------------------
@app.get("/api/analise")
async def analise(request: Request, cnpj: str, pa: int, user: str = Depends(auth)):
    pa = pa_ok(pa)
    dig = "".join(ch for ch in cnpj if ch.isdigit())
    if len(dig) < 8:
        raise HTTPException(400, "Informe o CNPJ (14 dígitos).")
    k = dig.zfill(14)

    def run():
        g1 = db.fetch(Q.sql_grade1(), [k, pa])
        g2 = db.fetch(Q.sql_grade2(), [k, str(pa)])
        g3 = db.fetch(Q.sql_grade3(), [k, pa])
        return g1, g2, g3

    g1, g2, g3 = await run_in_threadpool(lambda: executa(request, user, "analise", f"cnpj={k} pa={pa}", run))
    f = lambda rows: [{kk: (str(v)[:19] if kk.startswith("dt_") and v is not None else v) for kk, v in r.items()} for r in rows]
    tot = lambda rows, c: round(sum(float(r[c] or 0) for r in rows), 2)
    return {"cnpj": k, "pa": pa,
            "grade1_arrecadacao": f(g1), "grade2_escrituracao": f(g2), "grade3_rateio": f(g3),
            "totais": {"das_total": tot(g1, "total"), "escriturado_receita": tot(g2, "receita"), "escriturado_iss": tot(g2, "iss"),
                       "rateio_principal": tot(g3, "principal"),
                       "rateio_municipio": round(sum(float(r["principal"] or 0) for r in g3 if r["codmunic"] == S.COD_MUNIC_01100), 2)}}


# ---- baixa / estorno ---------------------------------------------------------------------------
@app.get("/api/baixa/simular")
async def baixa_simular(request: Request, pa: int, user: str = Depends(auth)):
    pa = pa_ok(pa)
    return await run_in_threadpool(lambda: executa(request, user, "baixa_simular", f"pa={pa}", lambda: confronto.plano_baixa(pa)))


@app.post("/api/baixa/executar")
async def baixa_executar(request: Request, pa: int, sobrescrever: bool = False, user: str = Depends(auth)):
    """Grava Parcelas.VrAutenticadoSuperSimples. Por padrão só onde ainda está vazio; 'sobrescrever' também troca valor diferente."""
    pa = pa_ok(pa)
    return await run_in_threadpool(lambda: executa(request, user, "baixa", f"pa={pa} sobrescrever={sobrescrever}",
                                                   lambda: confronto.baixar(pa, user, sobrescrever)))


@app.post("/api/baixa/estornar")
async def baixa_estornar(request: Request, pa: int, user: str = Depends(auth)):
    pa = pa_ok(pa)
    return await run_in_threadpool(lambda: executa(request, user, "estorno", f"pa={pa}", lambda: confronto.estornar(pa, user)))


# ---- carga do arquivo -----------------------------------------------------------------------------
@app.post("/api/carga")
async def carga_arquivo(request: Request, nome: str = "arquivo.txt", so_validar: bool = False, user: str = Depends(auth)):
    """Corpo da requisição = texto do arquivo (UTF-8). Layout hipotético: ver app/carga.py e exemplos/."""
    corpo = await request.body()
    if len(corpo) > S.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Arquivo maior que {S.MAX_UPLOAD_MB} MB.")
    try:
        texto = corpo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = corpo.decode("latin-1")
    return await run_in_threadpool(lambda: executa(request, user, "carga", f"nome={nome[:60]} validar={so_validar}",
                                                   lambda: carga.importa(texto, nome[:200], user, so_validar)))


@app.get("/api/carga/arquivos")
async def carga_lista(request: Request, user: str = Depends(auth)):
    sql = (f"SELECT a.Id, a.NomeArquivo, a.DataEnvio, a.QTD_LIN, "
           f"(SELECT COUNT(*) FROM {db.T('PGDASD00000')} d WHERE d.idPGDASDAAAAA = a.Id) AS declaracoes, "
           f"(SELECT COUNT(*) FROM {db.T('ArquivoSimplesErro')} e WHERE e.ArquivoId = a.Id) AS erros "
           f"FROM {db.T('PGDASDAAAAA')} a ORDER BY a.Id DESC")
    rows = await run_in_threadpool(lambda: executa(request, user, "carga_lista", "", lambda: db.fetch(sql)))
    for r in rows:
        r["DataEnvio"] = str(r["DataEnvio"])[:19]
    return {"itens": rows}


@app.get("/api/carga/erros")
async def carga_erros(request: Request, arquivo_id: int, user: str = Depends(auth)):
    sql = f"SELECT NumeroLinha, LinhaBruta, Erro FROM {db.T('ArquivoSimplesErro')} WHERE ArquivoId = ? ORDER BY NumeroLinha"
    rows = await run_in_threadpool(lambda: executa(request, user, "carga_erros", f"arq={arquivo_id}", lambda: db.fetch(sql, [arquivo_id])))
    return {"itens": rows}


# ---- conferência do esquema -------------------------------------------------------------------------
@app.get("/api/verificar-colunas")
async def verificar(request: Request, user: str = Depends(auth)):
    """Compara o esquema esperado (app/colunas.py) com o banco: aponta tabelas/colunas faltantes."""
    def run():
        faltam, ok = {}, 0
        for tab, cols in C.ESPERADO.items():
            if db.dialect() == "mssql":
                rows = db.fetch("SELECT COLUMN_NAME AS c FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", [tab])
                existentes = {r["c"].lower() for r in rows}
            else:
                c = db.connect()
                try:
                    existentes = {r[1].lower() for r in c.execute(f"PRAGMA table_info({tab})")}
                finally:
                    c.close()
            if not existentes:
                faltam[tab] = "TABELA NÃO ENCONTRADA"
                continue
            f = [x for x in cols if x.lower() not in existentes]
            if f:
                faltam[tab] = f
            else:
                ok += 1
        return {"tabelas_ok": ok, "tabelas_com_problema": len(faltam), "problemas": faltam}
    return await run_in_threadpool(lambda: executa(request, user, "verificar", "", run))


# ================================================================================ contribuintes
@app.get("/api/contribuintes")
async def contribuintes(request: Request, q: str = "", pagina: int = Query(1, ge=1), tamanho: int = Query(25, ge=1, le=100), user: str = Depends(auth)):
    itens, prox = await run_in_threadpool(lambda: executa(request, user, "contribuintes", q[:40], lambda: cadastros.lista_contribuintes(q, pagina, tamanho)))
    return {"itens": itens, "pagina": pagina, "tem_proxima": prox}


@app.post("/api/contribuintes")
async def contribuinte_novo(request: Request, dados: dict = Body(...), user: str = Depends(auth)):
    tipo = dados.get("tipo")
    cod = await run_in_threadpool(lambda: executa(request, user, "contribuinte_novo", so_dig(dados.get("cnpj")),
                                                  lambda: cadastros.cria_contribuinte(dados, "5" if tipo == "eventual" else None)))
    return {"codigo": cod}


@app.put("/api/contribuintes/{codigo}")
async def contribuinte_edita(request: Request, codigo: str, dados: dict = Body(...), user: str = Depends(auth)):
    await run_in_threadpool(lambda: executa(request, user, "contribuinte_edita", codigo, lambda: cadastros.atualiza_contribuinte(codigo, dados)))
    return {"ok": True}


def so_dig(v):
    return cadastros.so_digitos(v)


# ================================================================================ usuários (somente supervisor)
@app.get("/api/usuarios")
async def usuarios(request: Request, q: str = "", user: str = Depends(admin)):
    return {"itens": await run_in_threadpool(lambda: executa(request, user, "usuarios", q[:30], lambda: cadastros.lista_usuarios(q)))}


@app.post("/api/usuarios")
async def usuario_novo(request: Request, dados: dict = Body(...), user: str = Depends(admin)):
    uid = await run_in_threadpool(lambda: executa(request, user, "usuario_novo", str(dados.get("nome"))[:30], lambda: cadastros.cria_usuario(dados)))
    return {"id": uid}


@app.put("/api/usuarios/{uid}")
async def usuario_edita(request: Request, uid: int, dados: dict = Body(...), user: str = Depends(admin)):
    await run_in_threadpool(lambda: executa(request, user, "usuario_edita", str(uid), lambda: cadastros.atualiza_usuario(uid, dados, user)))
    return {"ok": True}


# ================================================================================ configuração (somente supervisor)
@app.get("/api/configuracao")
def configuracao(_: str = Depends(admin)):
    return ST.para_tela()


def _int(v, nome, mn=0, mx=2_000_000_000):
    try:
        n = int(str(v).strip() or 0)
    except ValueError:
        raise HTTPException(400, f"{nome}: informe um número inteiro.")
    if not mn <= n <= mx:
        raise HTTPException(400, f"{nome}: valor fora do intervalo permitido ({mn} a {mx}).")
    return n


def _aaaamm(v, nome):
    v = str(v or "").strip()
    if not v:
        return None
    try:
        return confronto.valida_pa(v)
    except ValueError:
        raise HTTPException(400, f"{nome}: use AAAAMM (ex.: 202501).")


@app.put("/api/configuracao")
async def configuracao_salva(request: Request, dados: dict = Body(...), user: str = Depends(admin)):
    atual = ST.le()
    n = dict(atual)
    for k in ("cliente", "municipio", "db_driver", "db_servidor", "db_banco", "db_usuario", "db_usuario_escrita", "smtp_host", "smtp_usuario", "smtp_remetente"):
        if k in dados:
            n[k] = str(dados[k] or "").strip()[:120]
    if not n["cliente"]:
        raise HTTPException(400, "Informe o nome do cliente.")
    for k in ST.SENHAS:                     # senha em branco = mantém a atual
        if dados.get(k):
            n[k] = str(dados[k])[:120]
    n["cod_tom"] = _int(dados.get("cod_tom", n["cod_tom"]), "Código TOM", 1, 99999999)
    n["cod_munic_01100"] = _int(dados.get("cod_munic_01100") or n["cod_tom"], "Código do município (01100)", 1, 99999999)
    n["periodo_ini"], n["periodo_fim"] = _aaaamm(dados.get("periodo_ini"), "Início do período"), _aaaamm(dados.get("periodo_fim"), "Fim do período")
    if n["periodo_ini"] and n["periodo_fim"] and n["periodo_ini"] > n["periodo_fim"]:
        raise HTTPException(400, "O início do período ativo não pode ser maior que o fim.")
    n["modulo_calculo"] = _int(dados.get("modulo_calculo"), "Módulo")
    n["grupo_calculo"] = _int(dados.get("grupo_calculo"), "Grupo")
    n["dias_vencimento"] = _int(dados.get("dias_vencimento", 30), "Dias para vencimento", 0, 365)
    n["dias_prazo_notificacao"] = _int(dados.get("dias_prazo_notificacao", 15), "Prazo da notificação", 1, 365)
    n["smtp_porta"] = _int(dados.get("smtp_porta", 587), "Porta SMTP", 1, 65535)
    n["calculo_habilitado"] = bool(dados.get("calculo_habilitado"))
    if n["calculo_habilitado"] and (n["modulo_calculo"] <= 0 or n["grupo_calculo"] <= 0):
        raise HTTPException(400, "Para habilitar a geração de cálculo informe Módulo e Grupo (inteiros maiores que zero).")
    ST.grava(n)
    ST.aplica(n)
    log_uso(request.client.host if request.client else "", user, "configuracao", "salva", 0, 0, "ok")
    return ST.para_tela(n)


@app.post("/api/configuracao/testar-conexao")
async def testar_conexao(dados: dict = Body(...), _: str = Depends(admin)):
    cfg = ST.le()
    cfg.update({k: str(dados.get(k) or cfg.get(k) or "") for k in ("db_driver", "db_servidor", "db_banco", "db_usuario")})
    cfg["db_senha"] = dados.get("db_senha") or cfg.get("db_senha", "")
    if not cfg["db_servidor"]:
        if S.DB_MODE == "demo":
            return {"ok": True, "mensagem": "Banco local de exemplo (SQLite) disponível."}
        raise HTTPException(400, "Informe o servidor.")

    def run():
        import pyodbc
        ST.le_cache = cfg
        cs = ST._conn(cfg["db_usuario"], cfg["db_senha"], False)
        c = pyodbc.connect(cs, timeout=8)
        try:
            return c.cursor().execute("SELECT DB_NAME()").fetchone()[0]
        finally:
            c.close()
    try:
        banco = await run_in_threadpool(run)
    except Exception as e:
        raise HTTPException(400, "Falha na conexão: " + str(e)[:200].replace(cfg["db_senha"] or "\0", "***"))
    finally:
        ST.le_cache = ST.le()
    return {"ok": True, "mensagem": f"Conectado ao banco {banco}."}


@app.put("/api/configuracao/brasao")
async def brasao_envia(request: Request, user: str = Depends(admin)):
    corpo = await request.body()
    if not corpo or len(corpo) > 1_048_576:
        raise HTTPException(400, "Envie uma imagem de até 1 MB.")
    if corpo[:8] == b"\x89PNG\r\n\x1a\n":
        tipo = "image/png"
    elif corpo[:3] == b"\xff\xd8\xff":
        tipo = "image/jpeg"
    elif corpo[:4] == b"RIFF" and corpo[8:12] == b"WEBP":
        tipo = "image/webp"
    else:
        raise HTTPException(400, "Formato não aceito. Use PNG, JPEG ou WEBP.")
    ST.BRASAO.parent.mkdir(parents=True, exist_ok=True)
    ST.BRASAO.write_bytes(corpo)
    ST.BRASAO_TIPO.write_text(tipo)
    return {"ok": True}


@app.delete("/api/configuracao/brasao")
def brasao_remove(_: str = Depends(admin)):
    ST.BRASAO.unlink(missing_ok=True)
    ST.BRASAO_TIPO.unlink(missing_ok=True)
    return {"ok": True}


# ================================================================================ ações sobre divergências
@app.post("/api/divergencias/{div_id}/eventual")
async def acao_eventual(request: Request, div_id: int, dados: dict = Body(...), user: str = Depends(auth)):
    return await run_in_threadpool(lambda: executa(request, user, "acao_eventual", f"div={div_id}", lambda: acoes.cadastrar_eventual(
        div_id, (dados.get("nome") or "").strip(), user, {k: dados.get(k) for k in ("fantasia", "email", "telefone") if dados.get(k)})))


@app.get("/api/divergencias/{div_id}/notificacao")
async def acao_notif_previa(request: Request, div_id: int, user: str = Depends(auth)):
    return await run_in_threadpool(lambda: executa(request, user, "notif_previa", f"div={div_id}", lambda: acoes.previa_notificacao(div_id)))


@app.post("/api/divergencias/{div_id}/notificacao")
async def acao_notif_envia(request: Request, div_id: int, dados: dict = Body(...), user: str = Depends(auth)):
    return await run_in_threadpool(lambda: executa(request, user, "notif_envia", f"div={div_id}", lambda: acoes.enviar_notificacao(
        div_id, dados.get("assunto"), dados.get("texto"), user)))


@app.get("/api/divergencias/{div_id}/calculo")
async def acao_calc_previa(request: Request, div_id: int, user: str = Depends(auth)):
    return await run_in_threadpool(lambda: executa(request, user, "calc_previa", f"div={div_id}", lambda: acoes.previa_calculo(div_id)))


@app.post("/api/divergencias/{div_id}/calculo")
async def acao_calc_gera(request: Request, div_id: int, user: str = Depends(auth)):
    return await run_in_threadpool(lambda: executa(request, user, "calc_gera", f"div={div_id}", lambda: acoes.gerar_calculo(div_id, user)))


@app.get("/api/notificacoes")
async def notificacoes(request: Request, user: str = Depends(auth)):
    return {"itens": await run_in_threadpool(lambda: executa(request, user, "notificacoes", "", lambda: acoes.lista_notificacoes()))}


@app.get("/api/notificacoes/{nid}")
async def notificacao_detalhe(request: Request, nid: int, user: str = Depends(auth)):
    return await run_in_threadpool(lambda: executa(request, user, "notificacao", str(nid), lambda: acoes.notificacao(nid)))
