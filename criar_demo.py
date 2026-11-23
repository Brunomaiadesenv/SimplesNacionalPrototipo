"""Cria demo.db com DADOS FICTÍCIOS (nenhum dado do cliente) para rodar o protótipo sem SQL Server.

As tabelas têm o MESMO nome e as MESMAS colunas usadas pelo confronto no SL_ISS (versão reduzida). Cada contribuinte
foi montado para exercitar um cenário (normal ou divergência) — a lista abaixo é o "gabarito" dos testes.
"""
import os
import random
import sqlite3
from datetime import date
from pathlib import Path

random.seed(11)
TOM, OUTRO_TOM = 9999, 1234
db = Path(os.environ.get("DEMO_DB") or Path(__file__).parent / "demo.db")
db.unlink(missing_ok=True)
c = sqlite3.connect(db)

DDL = """
CREATE TABLE Contribu(CodigoContribuinte TEXT PRIMARY KEY, Cnpj TEXT, RazaoSocial TEXT, SuperSimples TEXT, NomeFantasia TEXT, Email TEXT, Telefone TEXT);
CREATE TABLE SuperSimples(Id INTEGER PRIMARY KEY, CodigoContribuinte TEXT, DtAdesao TEXT, DtCancelamento TEXT);
CREATE TABLE Bia(Id INTEGER PRIMARY KEY, CodigoContribuinte TEXT, AnoMes TEXT, PT TEXT, SuperSimples TEXT, NotaFiscal TEXT,
                 VrBruto REAL, VrImposto REAL, PercentualSS REAL, PercentualOriginal REAL);
CREATE TABLE Parcelas(Id INTEGER PRIMARY KEY, CodigoContribuinte TEXT, AnoMes TEXT, VrParcela REAL, VrAutenticadoSuperSimples REAL,
                      NumeroParcelamento TEXT, NumeroParcela TEXT, DtVencimento TEXT, DtEmissao TEXT, QtdEmitido INT);
CREATE TABLE Calc1(NumeroCalculo INTEGER PRIMARY KEY, CodigoContribuinte TEXT NOT NULL, AnoMes TEXT, CodigoModulo INT, CodigoGrupo INT,
                   VrBase REAL, VrCalculado REAL, DtCalculo TEXT, Usuario TEXT, Origem TEXT);
CREATE TABLE Parcelam(NumeroParcelamento TEXT PRIMARY KEY, NumeroCalculo INT, CodigoContribuinte TEXT, NumeroParcela TEXT, VrParcela REAL, DtVencimento TEXT);
CREATE TABLE Usuario(NomeUsuario TEXT, CodigoUsuario TEXT, Privilegio TEXT, Senha TEXT, Ativo INT NOT NULL, DtInicio TEXT, DtExpiracao TEXT,
  DtAcesso TEXT, HoraEntrada TEXT, HoraSaida TEXT, Lotado TEXT, QtdConexoes INT NOT NULL, QtdConectado INT NOT NULL, TempoOcioso INT NOT NULL,
  SenhaProximoLogon INT NOT NULL, Senha30Dias INT NOT NULL, NomeCompleto TEXT, LerMensagens TEXT, FraseSecreta TEXT, Matricula TEXT, Cpf TEXT,
  TelefoneFixo TEXT, TelefoneCelular TEXT, Email TEXT, TpContribuNormal TEXT NOT NULL, TpContribuAmbulante TEXT NOT NULL, TpContribuEventual TEXT NOT NULL,
  TpContribuAvulso TEXT NOT NULL, TpContribuIrregular TEXT NOT NULL, TpContribuOutros TEXT NOT NULL, TpContribuMEI TEXT NOT NULL,
  TpContribuCondResidencial TEXT NOT NULL, Id INT NOT NULL, visualizarImpostoContribuinte TEXT NOT NULL, visualizarDividaContribuinte TEXT NOT NULL,
  AcessoVisualizacaoLog INT, ConCurrencyId TEXT NOT NULL, TipoDivida TEXT NOT NULL, IssAlterarIntimacaoFiscal TEXT NOT NULL);
CREATE TABLE ConfrontoAcao(Id INTEGER PRIMARY KEY, DivergenciaId INT NOT NULL, ExecucaoId INT NOT NULL, Tipo TEXT NOT NULL, Referencia TEXT,
                           Usuario TEXT, DtAcao TEXT, Detalhe TEXT);
CREATE TABLE SimplesNotificacao(Id INTEGER PRIMARY KEY, Numero TEXT NOT NULL, Ano INT NOT NULL, DivergenciaId INT, ExecucaoId INT, CodigoContribuinte TEXT,
                                Cnpj TEXT NOT NULL, Pa INT NOT NULL, Codigo TEXT NOT NULL, Assunto TEXT, Texto TEXT, Canal TEXT, Situacao TEXT,
                                DtEmissao TEXT, DtPrazo TEXT, Usuario TEXT, Erro TEXT);

CREATE TABLE PGDASDAAAAA(Id INTEGER PRIMARY KEY, Hash TEXT, NomeArquivo TEXT, DataEnvio TEXT, QTD_LIN INT, Usuario TEXT);
CREATE UNIQUE INDEX UX_PGDASDAAAAA_Hash ON PGDASDAAAAA(Hash);
CREATE TABLE PGDASD00000(Id INTEGER PRIMARY KEY, idPGDASDAAAAA INT, NumeroLinha INT, Pgdasd_Num_Recibo TEXT, Cnpjmatriz INT, CodTOM INT,
                         Optante INT, Pa INT, Rpa REAL, Operacao INT, Pgdasd_Dt_Transmissao TEXT);
CREATE TABLE PGDASD01000(Id INTEGER PRIMARY KEY, idPGDASDAAAAA INT, idPGDASD00000 INT, NumeroLinha INT, Nrpagto TEXT, Princ REAL, Multa REAL,
                         Juros REAL, Tdevido REAL, Dtvalcalc TEXT, Dtvenc TEXT, Vdas REAL);
CREATE TABLE PGDASD01100(Id INTEGER PRIMARY KEY, idPGDASDAAAAA INT, idPGDASD00000 INT, NumeroLinha INT, codmunic INT, valorprinc REAL, valorm REAL, valorj REAL);
CREATE TABLE PGDASD02000(Id INTEGER PRIMARY KEY, idPGDASDAAAAA INT, idPGDASD00000 INT, NumeroLinha INT, rbt12 REAL, Rba REAL, ICMS REAL, ISS REAL);
CREATE TABLE PGDASD03000(Id INTEGER PRIMARY KEY, idPGDASDAAAAA INT, idPGDASD00000 INT, NumeroLinha INT, CNPJ INT, CodTOM INT, Vltotal REAL);
CREATE TABLE PGDASD03110(Id INTEGER PRIMARY KEY, idPGDASDAAAAA INT, idPGDASD00000 INT, NumeroLinha INT, CodTOM INT, Valor REAL, ISS REAL,
                         AliApuradaISS REAL, ValorApuradoISS REAL);
CREATE TABLE ArquivoSimplesErro(Id INTEGER PRIMARY KEY, Evento TEXT, ArquivoId INT, NumeroLinha INT, LinhaBruta TEXT, Erro TEXT);

CREATE VIEW vw_PgdasDeclaracaoVigente AS
SELECT * FROM (SELECT d.*, ROW_NUMBER() OVER (PARTITION BY d.Cnpjmatriz, d.Pa ORDER BY d.Pgdasd_Dt_Transmissao DESC, d.Id DESC) AS rn
               FROM PGDASD00000 d) x WHERE rn = 1;

CREATE TABLE ConfrontoExecucao(Id INTEGER PRIMARY KEY, Pa INT NOT NULL, DtExecucao TEXT NOT NULL, Usuario TEXT NOT NULL,
                               ToleranciaAbs REAL NOT NULL, Situacao TEXT NOT NULL DEFAULT 'A');
CREATE TABLE ConfrontoDivergencia(Id INTEGER PRIMARY KEY, ExecucaoId INT NOT NULL REFERENCES ConfrontoExecucao(Id), DeclaracaoId INT,
                                  Cnpj TEXT NOT NULL, CodigoContribuinte TEXT, Codigo TEXT NOT NULL, VrDeclarado REAL, VrEscriturado REAL,
                                  Tratamento TEXT NOT NULL DEFAULT 'P', Justificativa TEXT);
CREATE INDEX IX_Div_Exec ON ConfrontoDivergencia(ExecucaoId, Codigo);
CREATE TABLE ConfrontoBaixa(Id INTEGER PRIMARY KEY, ExecucaoId INT NOT NULL REFERENCES ConfrontoExecucao(Id), ParcelaId INT NOT NULL,
                            ValorAnterior REAL, ValorGravado REAL NOT NULL, Usuario TEXT, DtBaixa TEXT, DtEstorno TEXT);
"""
c.executescript(DDL)

NOMES = ["Padaria", "Oficina", "Clínica", "Mercearia", "Contabilidade", "Transportes", "Informática", "Studio", "Engenharia",
         "Escola", "Farmácia", "Estética", "Construtora", "Lavanderia", "Restaurante"]
SOBRE = ["Aurora", "Horizonte", "Vitória", "Central", "Nova Era", "Boa Vista", "Alvorada", "Prata", "Delta", "Pioneira"]


def cnpj_de(i):
    return 11000000000000 + i * 7919 * 13 + 1     # fictício; entra como INTEGER nas tabelas PGDASD (perde zeros) e texto 14 dígitos em Contribu


# gabarito: (cenário, quantidade)
CEN = [("normal", 30), ("baixa_pendente", 6), ("tolerancia", 1), ("retificadora", 1),
       ("D00", 1), ("D01", 2), ("D02", 3), ("D03", 3), ("D04D05", 3), ("D06", 2), ("D07", 2), ("D08", 1)]
GABARITO = {}
seq = {"i": 0, "decl": 0, "bia": 0, "parc": 0}


def nova_decl(pa, cnpj, receita, iss, aliq, dt, operacao=1, iss_total_extra=0.0, rateio_ok=True):
    seq["decl"] += 1
    did = seq["decl"]
    c.execute("INSERT INTO PGDASD00000 VALUES (?,?,?,?,?,?,?,?,?,?,?)",
              (did, None, 1, f"{pa}{did:07d}", cnpj, TOM, 1, pa, receita, operacao, dt))
    c.execute("INSERT INTO PGDASD01000 VALUES (NULL,NULL,?,2,?,?,?,?,?,?,?,?)",
              (did, f"DAS{pa}{did:05d}", round(iss * 4, 2), 0, 0, round(iss * 4, 2), f"{pa // 100}-{pa % 100:02d}-20", f"{pa // 100}-{pa % 100:02d}-20", round(iss * 4, 2)))
    c.execute("INSERT INTO PGDASD01100 VALUES (NULL,NULL,?,3,?,?,0,0)", (did, TOM, iss))
    c.execute("INSERT INTO PGDASD01100 VALUES (NULL,NULL,?,4,?,?,0,0)", (did, OUTRO_TOM, round(iss * 1.5, 2)))   # outro município (não entra)
    c.execute("INSERT INTO PGDASD02000 VALUES (NULL,NULL,?,5,?,?,0,?)", (did, receita * 12, receita, round(iss + iss * 1.5 + iss_total_extra, 2)))
    c.execute("INSERT INTO PGDASD03000 VALUES (NULL,NULL,?,6,?,?,?)", (did, cnpj, TOM, receita))
    c.execute("INSERT INTO PGDASD03000 VALUES (NULL,NULL,?,7,?,?,?)", (did, cnpj, OUTRO_TOM, round(receita * 1.5, 2)))
    c.execute("INSERT INTO PGDASD03110 VALUES (NULL,NULL,?,8,?,?,?,?,?)", (did, TOM, receita, iss, aliq, iss))
    c.execute("INSERT INTO PGDASD03110 VALUES (NULL,NULL,?,9,?,?,?,?,?)", (did, OUTRO_TOM, round(receita * 1.5, 2), round(iss * 1.5, 2), aliq, round(iss * 1.5, 2)))
    return did


def nova_bia(cod, pa, receita, iss, aliq_ss, aliq_orig=5.0, partes=3):
    resto_r, resto_i = receita, iss
    for k in range(partes):
        r = round(receita / partes, 2) if k < partes - 1 else round(resto_r, 2)
        i = round(iss / partes, 2) if k < partes - 1 else round(resto_i, 2)
        resto_r -= r; resto_i -= i
        seq["bia"] += 1
        c.execute("INSERT INTO Bia VALUES (?,?,?,?,?,?,?,?,?,?)", (seq["bia"], cod, str(pa), "P", "S", f"NF{seq['bia']:06d}", r, i, aliq_ss, aliq_orig))


def nova_parcela(cod, pa, valor_parcela, aut):
    seq["parc"] += 1
    c.execute("INSERT INTO Parcelas(Id,CodigoContribuinte,AnoMes,VrParcela,VrAutenticadoSuperSimples) VALUES (?,?,?,?,?)", (seq["parc"], cod, str(pa), valor_parcela, aut))
    return seq["parc"]


def contribuinte(i, cnpj, com_cadastro=True, adesao=("2020-01-01", None), historico=True):
    cod = f"{1000 + i}"
    if com_cadastro:
        nome = f"{random.choice(NOMES)} {random.choice(SOBRE)} {i:03d} LTDA"
        c.execute("INSERT INTO Contribu(CodigoContribuinte,Cnpj,RazaoSocial,SuperSimples,Email) VALUES (?,?,?,?,?)", (cod, str(cnpj).zfill(14), nome, "S", f"contato{i:03d}@exemplo.invalid"))
        if historico:
            c.execute("INSERT INTO SuperSimples VALUES (NULL,?,?,?)", (cod, adesao[0], adesao[1]))
    return cod


def monta(pa, cenarios, dt_base):
    for nome, qtd in cenarios:
        for _ in range(qtd):
            seq["i"] += 1
            i = seq["i"]
            cnpj = cnpj_de(i)
            receita = round(random.uniform(8000, 90000), 2)
            aliq = round(random.uniform(2.0, 5.0), 2)
            iss = round(receita * aliq / 100, 2)
            dt = f"{dt_base} 10:{i % 60:02d}:00"
            GABARITO.setdefault(pa, {}).setdefault(nome, []).append(str(cnpj).zfill(14))

            if nome in ("normal", "baixa_pendente", "tolerancia", "retificadora", "D04D05", "D06", "D07", "D08", "D00"):
                adesao = ("2020-01-01", "2025-08-31") if nome == "D08" else ("2020-01-01", None)
                cod = contribuinte(i, cnpj, adesao=adesao, historico=(i % 5 != 0))   # 1 em 5 sem histórico (regra de transição)
            elif nome == "D02":
                cod = contribuinte(i, cnpj)
            elif nome == "D03":
                cod = contribuinte(i, cnpj)
            else:   # D01: nem cadastro
                cod = None

            if nome == "retificadora":
                # original (errada) transmitida antes; a vigente é a retificadora, que bate com a Bia
                nova_decl(pa, cnpj, round(receita * 0.8, 2), round(iss * 0.8, 2), aliq, f"{dt_base} 08:00:00", operacao=1)
                did = nova_decl(pa, cnpj, receita, iss, aliq, f"{dt_base} 15:00:00", operacao=2)
                nova_bia(cod, pa, receita, iss, aliq)
                nova_parcela(cod, pa, iss, iss)
                continue
            if nome == "D00":
                nova_decl(pa, cnpj, receita, iss, aliq, dt, iss_total_extra=50.0)   # 02000.ISS não fecha com a soma do 03110
                nova_bia(cod, pa, receita, iss, aliq)
                nova_parcela(cod, pa, iss, None)
                continue
            if nome == "D01":
                nova_decl(pa, cnpj, receita, iss, aliq, dt)
                continue
            if nome == "D02":
                nova_decl(pa, cnpj, receita, iss, aliq, dt)
                nova_parcela(cod, pa, iss, None)
                continue
            if nome == "D03":
                nova_bia(cod, pa, receita, iss, aliq)
                continue

            nova_decl(pa, cnpj, receita, iss, aliq, dt)
            if nome == "D04D05":
                nova_bia(cod, pa, round(receita * 0.9, 2), round(iss * 0.9, 2), aliq)
            elif nome == "D06":
                nova_bia(cod, pa, receita, iss, round(aliq + 0.5, 2))      # alíquota errada, valores iguais
            elif nome == "tolerancia":
                nova_bia(cod, pa, receita, round(iss + 0.03, 2), aliq)      # R$ 0,03 < tolerância de R$ 0,05
            else:
                nova_bia(cod, pa, receita, iss, aliq)
            aut = iss
            if nome == "baixa_pendente":
                aut = None
            elif nome == "D07":
                aut = round(iss - 12.34, 2)
            nova_parcela(cod, pa, iss, aut)


import uuid
def _u(i, nome, cod, senha, priv, completo):
    c.execute("INSERT INTO Usuario(NomeUsuario,CodigoUsuario,Privilegio,Senha,Ativo,QtdConexoes,QtdConectado,TempoOcioso,SenhaProximoLogon,Senha30Dias,NomeCompleto,"
              "TpContribuNormal,TpContribuAmbulante,TpContribuEventual,TpContribuAvulso,TpContribuIrregular,TpContribuOutros,TpContribuMEI,TpContribuCondResidencial,"
              "Id,visualizarImpostoContribuinte,visualizarDividaContribuinte,ConCurrencyId,TipoDivida,IssAlterarIntimacaoFiscal) "
              "VALUES (?,?,?,?,1,0,0,0,0,0,?,'N','N','N','N','N','N','N','N',?,'N','N',?,'N','N')", (nome, cod, priv, senha, completo, i, str(uuid.uuid4())))
_u(1, "supervisor", "SUP", "167421es", "S", "Supervisor (usuário de teste)")     # pedido: usuário de teste do protótipo
_u(2, "fiscal", "FIS", "fiscal123", "F", "Auditor Fiscal de Teste")
monta(202509, [("normal", 8), ("baixa_pendente", 2), ("D03", 1)], "2025-10-08")
monta(202510, CEN, "2025-11-10")
c.commit()
c.execute("PRAGMA foreign_keys=ON")
c.close()
import json
(Path(__file__).parent / "exemplos").mkdir(exist_ok=True)
(Path(__file__).parent / "exemplos" / "gabarito_demo.json").write_text(json.dumps(GABARITO, indent=1, ensure_ascii=False), encoding="utf-8")
print("demo.db criado em", db)
