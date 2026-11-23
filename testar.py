"""Testes de aceite do protótipo (modo demo, banco temporário). Uso:  python testar.py
Cobrem os cenários do Guia do programador: vigência, tolerância, D00–D08, baixa idempotente, estorno, carga."""
import json, os, shutil, sys, tempfile
from pathlib import Path

AQUI = Path(__file__).parent
tmp = tempfile.mkdtemp()
os.environ.update(DB_MODE="demo", DEMO_DB=os.path.join(tmp, "t.db"), USO_DB=os.path.join(tmp, "uso.db"), CONFIG_JSON=os.path.join(tmp, "config.json"), SECRET_KEY="chave-de-teste", MAX_ERRO_CARGA_PCT="5")
sys.path.insert(0, str(AQUI))
import subprocess
subprocess.run([sys.executable, str(AQUI / "criar_demo.py")], check=True, capture_output=True, env=os.environ.copy())

from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
assert c.post("/api/login", json={"usuario": "supervisor", "senha": "167421es"}).status_code == 200      # sessão do supervisor de teste
G = json.load(open(AQUI / "exemplos" / "gabarito_demo.json"))["202510"]
ok = falhas = 0


def t(nome, cond, extra=""):
    global ok, falhas
    ok += bool(cond); falhas += (not cond)
    print(("  ok  " if cond else " FALHA"), nome, extra if not cond else "")


r = c.post("/api/confronto/executar?pa=202510").json()
por = {}
for d in r["divergencias"]:
    por.setdefault(d["cnpj"], set()).add(d["codigo"])
cod_de = lambda cn: por.get(cn, set())
t("1  simulação não grava nada", r["persistido"] is False and c.get("/api/execucoes").json()["itens"] == [])
t("2  contagem por código bate com o gabarito", r["por_codigo"] == dict(D00=1, D01=2, D02=3, D03=3, D04=3, D05=3, D06=2, D07=2, D08=1), r["por_codigo"])
t("3  contribuintes normais sem divergência", all(not cod_de(x) for x in G["normal"]))
t("4  diferença de R$ 0,03 fica dentro da tolerância", all(not cod_de(x) for x in G["tolerancia"]))
t("5  retificadora: vale só a vigente, sem divergência", all(not cod_de(x) for x in G["retificadora"]))
t("6  D00 bloqueia o confronto da declaração (sem D03 falso)", all(cod_de(x) == {"D00"} for x in G["D00"]))
t("7  D01 só em CNPJ sem cadastro", all(cod_de(x) == {"D01"} for x in G["D01"]))
t("8  D02 declarou e não escriturou", all(cod_de(x) == {"D02"} for x in G["D02"]))
t("9  D03 escriturou sem declarar", all(cod_de(x) == {"D03"} for x in G["D03"]))
t("10 D04+D05 juntos; alíquota igual não gera D06", all(cod_de(x) == {"D04", "D05"} for x in G["D04D05"]))
t("11 D06 isolado (valores iguais)", all(cod_de(x) == {"D06"} for x in G["D06"]))
t("12 D07 só onde há valor baixado diferente; baixa pendente (NULL) não é D07", all(cod_de(x) == {"D07"} for x in G["D07"]) and all(not cod_de(x) for x in G["baixa_pendente"]))
t("13 D08 fora da adesão; sem histórico não gera D08", all(cod_de(x) == {"D08"} for x in G["D08"]))
t("14 PA inválida é recusada", c.post("/api/confronto/executar?pa=202513").status_code == 400)

eid = c.post("/api/confronto/executar?pa=202510&gravar=true").json()["execucao_id"]
t("15 execução gravada e reexecução cria nova", c.post("/api/confronto/executar?pa=202510&gravar=true").json()["execucao_id"] == eid + 1)
eid += 1
dv = c.get(f"/api/divergencias?execucao_id={eid}&codigo=D07").json()["itens"]
t("16 tratamento exige justificativa", c.patch(f"/api/divergencias/{dv[0]['id']}/tratamento", json={"tratamento": "J", "justificativa": "x"}).status_code == 400)
t("17 tratamento justificado grava", c.patch(f"/api/divergencias/{dv[0]['id']}/tratamento", json={"tratamento": "J", "justificativa": "DAS retificador apresentado"}).status_code == 200
  and c.get(f"/api/resumo?execucao_id={eid}").json()["por_tratamento"]["J"] == 1)

pl = c.get("/api/baixa/simular?pa=202510").json()["resumo"]
b1 = c.post("/api/baixa/executar?pa=202510").json()
t("18 baixa grava só onde estava vazio", b1["parcelas_gravadas"] == pl["gravar"] and pl.get("sobrescrever", 0) == 2, (pl, b1))
t("19 baixa repetida é recusada (idempotente)", c.post("/api/baixa/executar?pa=202510").status_code == 400)
t("20 após a baixa o plano não tem mais 'gravar'", c.get("/api/baixa/simular?pa=202510").json()["resumo"].get("gravar", 0) == 0)
e1 = c.post("/api/baixa/estornar?pa=202510").json()
t("21 estorno restaura exatamente as parcelas baixadas", e1["parcelas_estornadas"] == b1["parcelas_gravadas"] and c.get("/api/baixa/simular?pa=202510").json()["resumo"]["gravar"] == pl["gravar"])

ex = (AQUI / "exemplos" / "pgdasd_exemplo.txt").read_text(encoding="utf-8")
t("22 carga: só validar não grava", c.post("/api/carga?so_validar=true&nome=x.txt", content=ex).json()["status"] == "validado" and c.get("/api/carga/arquivos").json()["itens"] == [])
t("23 carga: importa e registra erro da linha inválida", c.post("/api/carga?nome=x.txt", content=ex).json()["status"] == "importado" and c.get("/api/carga/erros?arquivo_id=1").json()["itens"][0]["NumeroLinha"] == 10)
t("24 carga: mesmo arquivo é recusado pelo hash", c.post("/api/carga?nome=x.txt", content=ex).json()["status"] == "recusado")
ruim = "ARQ|4\n" + "\n".join(["00000|R1|11000000000009|202511|9999|1|1.00|1|2025-12-01 10:00:00", "01100|A|1|0|0", "01100|B|1|0|0", "01100|C|1|0|0"]) + "\n"
t("25 carga: >5% de linhas inválidas reverte tudo", c.post("/api/carga?nome=ruim.txt", content=ruim).json()["status"] == "revertido" and len(c.get("/api/carga/arquivos").json()["itens"]) == 1)
t("26 verificar-colunas sem problema no demo", c.get("/api/verificar-colunas").json()["tabelas_com_problema"] == 0)

# ============================================================ login, perfis, cadastros, configuração, ações
import sqlite3
anon = TestClient(app)
t("27 sem sessão: API 401 e página inicial redireciona ao login", anon.get("/api/config").status_code == 401
  and anon.get("/", follow_redirects=False).status_code == 302 and anon.get("/login").status_code == 200)
t("28 senha errada / usuário inexistente: 401 com mensagem única", anon.post("/api/login", json={"usuario": "supervisor", "senha": "x"}).status_code == 401
  and anon.post("/api/login", json={"usuario": "naoexiste", "senha": "x"}).json()["detail"] == "Usuário ou senha inválidos.")
t("29 login por código do usuário (SUP) e sem diferenciar maiúsculas", TestClient(app).post("/api/login", json={"usuario": "sup", "senha": "167421es"}).status_code == 200)
fis = TestClient(app)
t("30 usuário comum entra, mas não acessa Usuários/Configuração", fis.post("/api/login", json={"usuario": "fiscal", "senha": "fiscal123"}).status_code == 200
  and fis.get("/api/config").status_code == 200 and fis.get("/api/usuarios").status_code == 403 and fis.get("/api/configuracao").status_code == 403
  and fis.get("/api/sessao").json()["adm"] is False)
cookie = c.cookies.get("sf_sess")
t("31 cookie adulterado é rejeitado", TestClient(app, cookies={"sf_sess": cookie[:-3] + "abc"}).get("/api/config").status_code == 401)
for _ in range(5):
    anon.post("/api/login", json={"usuario": "fiscal", "senha": "errada"})
t("32 bloqueio após 5 tentativas erradas (429), mesmo com a senha certa", anon.post("/api/login", json={"usuario": "fiscal", "senha": "fiscal123"}).status_code == 429)
r = c.post("/api/usuarios", json={"nome": "Inativo1", "codigo": "IN1", "senha": "abc12345", "priv": "F", "ativo": False})
r2 = c.post("/api/usuarios", json={"nome": "Vencido1", "codigo": "VE1", "senha": "abc12345", "priv": "F", "ativo": True, "exp": "2020-01-01"})
t("33 usuário inativo ou vencido: 403", r.status_code == 200 and r2.status_code == 200
  and TestClient(app).post("/api/login", json={"usuario": "inativo1", "senha": "abc12345"}).status_code == 403
  and TestClient(app).post("/api/login", json={"usuario": "vencido1", "senha": "abc12345"}).status_code == 403)
t("34 cadastro de usuário: duplicado, senha curta e Id sequencial", c.post("/api/usuarios", json={"nome": "FISCAL", "codigo": "ZZ", "senha": "abc12345"}).status_code == 400
  and c.post("/api/usuarios", json={"nome": "Novo2", "codigo": "NV2", "senha": "123"}).status_code == 400 and r.json()["id"] == 3)
lst = c.get("/api/usuarios").json()["itens"]
t("35 listagem de usuários nunca devolve a senha", lst and all("senha" not in u and "Senha" not in u for u in lst) and "167421es" not in c.get("/api/usuarios").text)
sup = next(u for u in lst if u["nome"] == "supervisor")
t("36 supervisor não pode desativar o próprio usuário", c.put(f"/api/usuarios/{sup['id']}", json={"nome": "supervisor", "codigo": "SUP", "priv": "S", "ativo": False}).status_code == 400)
t("37 edição mantém a senha quando em branco", c.put(f"/api/usuarios/{sup['id']}", json={"nome": "supervisor", "codigo": "SUP", "priv": "S", "ativo": True, "completo": "Supervisor T"}).status_code == 200
  and TestClient(app).post("/api/login", json={"usuario": "supervisor", "senha": "167421es"}).status_code == 200)

# contribuintes
n = c.post("/api/contribuintes", json={"cnpj": "11.222.333/0001-81", "nome": "Empresa Teste Eventual", "tipo": "eventual", "email": "x@exemplo.invalid"})
cod5 = n.json().get("codigo", "")
t("38 contribuinte Eventual recebe código com prefixo 5", n.status_code == 200 and cod5.startswith("5") and len(cod5) == 6, n.text)
t("39 CNPJ duplicado e CNPJ inválido são recusados", c.post("/api/contribuintes", json={"cnpj": "11222333000181", "nome": "Dup", "tipo": "eventual"}).status_code == 400
  and c.post("/api/contribuintes", json={"cnpj": "11222333000182", "nome": "Ruim", "tipo": "eventual"}).status_code == 400)
bu = c.get("/api/contribuintes?q=11222333").json()["itens"]
t("40 busca por CNPJ parcial encontra e classifica como Eventual", len(bu) == 1 and bu[0]["tipo"] == "Eventual" and bu[0]["cnpj"] == "11222333000181")
t("41 edição do contribuinte", c.put(f"/api/contribuintes/{cod5}", json={"nome": "Empresa Teste Alterada", "simples": "S"}).status_code == 200
  and c.get("/api/contribuintes?q=Alterada").json()["itens"][0]["nome"] == "Empresa Teste Alterada")
t("42 busca com caracteres curinga não quebra", c.get("/api/contribuintes?q=%25_%27").status_code == 200)

# configuração
cf = c.get("/api/configuracao").json()
t("43 configuração não devolve senhas", all(cf[k] == "" for k in ("db_senha", "db_senha_escrita", "smtp_senha")))
r = c.put("/api/configuracao", json={**cf, "cliente": "Prefeitura de Teste", "modulo_calculo": "7", "grupo_calculo": "3", "db_senha": "segredo123", "periodo_ini": "202509", "periodo_fim": "202510", "calculo_habilitado": True})
t("44 salvar configuração mascara a senha e reflete no sistema", r.status_code == 200 and r.json()["db_senha_definida"] is True and r.json()["db_senha"] == ""
  and "segredo123" not in r.text and c.get("/api/config").json()["modulo_calculo"] == 7 and c.get("/api/publico").json()["cliente"] == "Prefeitura de Teste")
t("45 módulo/grupo só aceitam inteiro", c.put("/api/configuracao", json={**cf, "modulo_calculo": "1.5"}).status_code == 400
  and c.put("/api/configuracao", json={**cf, "modulo_calculo": "abc"}).status_code == 400)
t("46 período inválido ou invertido é recusado", c.put("/api/configuracao", json={**cf, "periodo_ini": "202610", "periodo_fim": "202501"}).status_code == 400
  and c.put("/api/configuracao", json={**cf, "periodo_ini": "2025"}).status_code == 400)
t("47 período ativo filtra competências e bloqueia o confronto fora dele", set(c.get("/api/competencias").json()["competencias"]) <= {202509, 202510}
  and c.post("/api/confronto/executar?pa=202401").status_code == 400)
png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
t("48 brasão: aceita PNG, recusa outros formatos e arquivo grande, restaura padrão", c.put("/api/configuracao/brasao", content=png).status_code == 200
  and c.get("/api/brasao").headers["content-type"] == "image/png" and c.put("/api/configuracao/brasao", content=b"<svg onload=alert(1)>").status_code == 400
  and c.put("/api/configuracao/brasao", content=png + b"0" * 1_100_000).status_code == 400 and fis.put("/api/configuracao/brasao", content=png).status_code == 403
  and c.delete("/api/configuracao/brasao").status_code == 200 and "svg" in c.get("/api/brasao").headers["content-type"])
t("49 teste de conexão no demo", c.post("/api/configuracao/testar-conexao", json={}).json()["ok"] is True)

# ações por divergência (execução gravada eid)
dv = lambda cod: c.get(f"/api/divergencias?execucao_id={eid}&codigo={cod}&tamanho=100").json()["itens"]
d01, d00, d02, d03, d04, d05 = dv("D01"), dv("D00"), dv("D02"), dv("D03"), dv("D04"), dv("D05")
t("50 D00 é somente alerta: nenhuma ação é aceita", all(c.post(f"/api/divergencias/{d00[0]['id']}/{a}", json={"nome": "x"}).status_code == 400 for a in ("eventual", "notificacao", "calculo")))
t("51 D01 não aceita notificação nem cálculo", c.post(f"/api/divergencias/{d01[0]['id']}/notificacao", json={"assunto": "a", "texto": "x" * 30}).status_code == 400
  and c.post(f"/api/divergencias/{d01[0]['id']}/calculo").status_code == 400)
t("52 D01: razão social é obrigatória", c.post(f"/api/divergencias/{d01[0]['id']}/eventual", json={"nome": ""}).status_code == 400)
cn1 = d01[0]["cnpj"]
cad0 = len(c.get("/api/contribuintes?q=" + cn1).json()["itens"])
r = c.post(f"/api/divergencias/{d01[0]['id']}/eventual", json={"nome": "Cadastro via D01 LTDA", "email": "d01@exemplo.invalid"})
novo = c.get("/api/contribuintes?q=" + cn1).json()["itens"]
t("53 D01 cadastra o CNPJ como Eventual (prefixo 5) e marca como Regularizada", cad0 == 0 and r.status_code == 200 and r.json()["codigo"].startswith("5") and len(novo) == 1
  and novo[0]["tipo"] == "Eventual" and dv("D01")[0]["tratamento"] == "R", r.text)
t("54 D01 repetido é recusado (CNPJ já cadastrado)", c.post(f"/api/divergencias/{d01[0]['id']}/eventual", json={"nome": "Outra"}).status_code == 400)
t("55 próximo confronto não acusa mais D01 para esse CNPJ", cn1 not in {d["cnpj"] for d in c.post("/api/confronto/executar?pa=202510").json()["divergencias"] if d["codigo"] == "D01"})
t("56 tratamento manual não aceita L/R", c.patch(f"/api/divergencias/{d02[0]['id']}/tratamento", json={"tratamento": "L"}).status_code == 400)

pv = c.get(f"/api/divergencias/{d02[0]['id']}/notificacao").json()
t("57 notificação vem preenchida com os dados do confronto", d02[0]["cnpj"] in pv["texto"] and "202510"[4:] + "/2025" in pv["texto"] and pv["assunto"] and "R$" in pv["texto"], pv["texto"][:200])
env = c.post(f"/api/divergencias/{d02[0]['id']}/notificacao", json={"assunto": pv["assunto"], "texto": pv["texto"] + "\nObs: editada pelo fiscal."})
t("58 enviar notificação: número, registro e tratamento Notificada", env.status_code == 200 and env.json()["numero"].startswith("00001/") and dv("D02")[0]["tratamento"] == "N"
  and c.get("/api/notificacoes").json()["itens"][0]["Codigo"] == "D02" and "editada pelo fiscal" in c.get(f"/api/notificacoes/{c.get('/api/notificacoes').json()['itens'][0]['Id']}").json()["Texto"])
t("59 notificação duplicada e texto vazio são recusados", c.post(f"/api/divergencias/{d02[0]['id']}/notificacao", json={"assunto": "a", "texto": pv["texto"]}).status_code == 400
  and c.post(f"/api/divergencias/{d03[0]['id']}/notificacao", json={"assunto": "a", "texto": "curto"}).status_code == 400)
okn = all(c.get(f"/api/divergencias/{x['id']}/notificacao").status_code == 200 for cod in ("D03", "D06", "D07", "D08") for x in dv(cod)[:1])
t("60 D03, D06, D07 e D08 também geram a prévia da notificação", okn)

baixa_antes = c.get("/api/baixa/simular?pa=202510").json()["resumo"]
pc = c.get(f"/api/divergencias/{d05[0]['id']}/calculo").json()
t("61 prévia do cálculo: valor, módulo/grupo e vencimento", pc["valor"] > 0 and pc["modulo"] == 7 and pc["grupo"] == 3 and pc["vencimento"] and not pc.get("bloqueio"), pc)
g = c.post(f"/api/divergencias/{d05[0]['id']}/calculo")
bd = sqlite3.connect(os.environ["DEMO_DB"])
cod_c = pc["contribuinte"]["codigo"]
c1 = bd.execute("select NumeroCalculo,VrCalculado,CodigoModulo,CodigoGrupo,Origem from Calc1 where CodigoContribuinte=?", (cod_c,)).fetchall()
pm = bd.execute("select NumeroParcelamento,NumeroParcela,VrParcela,NumeroCalculo from Parcelam where CodigoContribuinte=?", (cod_c,)).fetchall()
ps = bd.execute("select NumeroParcelamento,NumeroParcela,VrParcela,QtdEmitido,DtEmissao from Parcelas where NumeroParcelamento is not null").fetchall()
t("62 gerar cálculo grava Calc1 + Parcelam (parcela 01) + Parcelas (controle de emissão)", g.status_code == 200 and len(c1) == 1 and len(pm) == 1 and len(ps) == 1
  and c1[0][1] == pc["valor"] == pm[0][2] == ps[0][2] and c1[0][2:4] == (7, 3) and pm[0][1] == "01" and pm[0][3] == c1[0][0] and ps[0][0] == pm[0][0] and ps[0][3] == 0 and ps[0][4] is None, (g.text, c1, pm, ps))
t("63 D04/D05 do mesmo contribuinte ficam como 'Cálculo lançado'", all(x["tratamento"] == "L" for x in dv("D05") + dv("D04") if x["cnpj"] == d05[0]["cnpj"]))
t("64 cálculo não é gerado duas vezes (D04 e D05 do mesmo contribuinte)", c.post(f"/api/divergencias/{d05[0]['id']}/calculo").status_code == 400
  and all(c.post(f"/api/divergencias/{x['id']}/calculo").status_code == 400 for x in d04 if x["cnpj"] == d05[0]["cnpj"]))
t("65 a baixa não enxerga as parcelas do cálculo gerado", c.get("/api/baixa/simular?pa=202510").json()["resumo"] == baixa_antes)
cf2 = c.get("/api/configuracao").json()
c.put("/api/configuracao", json={**cf2, "calculo_habilitado": False})
outro = next((x for x in d05 if x["cnpj"] != d05[0]["cnpj"]), None)
t("66 cálculo desabilitado em Configuração é recusado", outro is not None and c.post(f"/api/divergencias/{outro['id']}/calculo").status_code == 400)
c.put("/api/configuracao", json={**cf2, "calculo_habilitado": True})
t("67 ações exigem login", anon.post(f"/api/divergencias/{d05[0]['id']}/calculo").status_code == 401 and anon.get("/api/notificacoes").status_code == 401)
t("68 verificar-colunas inclui as novas tabelas", c.get("/api/verificar-colunas").json()["tabelas_com_problema"] == 0)
bd.close()
print(f"\n{ok} ok, {falhas} falha(s)")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if falhas else 0)
