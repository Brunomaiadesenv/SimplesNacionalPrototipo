-- =====================================================================================================
-- DDL do módulo Simples Nacional (SQL Server, banco SL_ISS). Revise ANTES de executar em produção.
-- Só CRIA 4 tabelas novas e ADICIONA colunas/índices; não altera nenhum dado existente.
-- Segue o Guia do programador (seção "Modelo de dados"), com 3 acréscimos do protótipo:
--   * ConfrontoExecucao.Usuario (varchar) no lugar de IdUsuario (o protótipo não tem tabela de usuários);
--   * ConfrontoBaixa (nova): guarda o valor anterior de cada parcela baixada, para o estorno restaurar exatamente;
--   * PGDASDAAAAA.Usuario: quem importou o arquivo.
-- =====================================================================================================
SET XACT_ABORT ON;
BEGIN TRAN;

CREATE TABLE dbo.ConfrontoExecucao (
  Id INT IDENTITY PRIMARY KEY,
  Pa INT NOT NULL,                                   -- AAAAMM, mesmo tipo de PGDASD00000.Pa
  DtExecucao DATETIME NOT NULL DEFAULT GETDATE(),
  Usuario VARCHAR(60) NOT NULL,
  ToleranciaAbs DECIMAL(9,2) NOT NULL,               -- congelada na execução
  Situacao CHAR(1) NOT NULL DEFAULT 'A'              -- A aberta, B baixada, F fechada
);
CREATE TABLE dbo.ConfrontoDivergencia (
  Id BIGINT IDENTITY PRIMARY KEY,
  ExecucaoId INT NOT NULL REFERENCES dbo.ConfrontoExecucao(Id),
  DeclaracaoId BIGINT NULL,                          -- PGDASD00000.Id
  Cnpj CHAR(14) NOT NULL,
  CodigoContribuinte VARCHAR(20) NULL,
  Codigo CHAR(3) NOT NULL,                           -- D00..D08
  VrDeclarado DECIMAL(15,2) NULL,
  VrEscriturado DECIMAL(15,2) NULL,
  VrDiferenca AS (ISNULL(VrDeclarado,0) - ISNULL(VrEscriturado,0)),
  Tratamento CHAR(1) NOT NULL DEFAULT 'P',           -- P pendente, J justificada, N notificada
  Justificativa VARCHAR(500) NULL
);
CREATE INDEX IX_ConfrontoDivergencia_Exec ON dbo.ConfrontoDivergencia (ExecucaoId, Codigo) INCLUDE (Cnpj, Tratamento);
CREATE TABLE dbo.ConfrontoBaixa (
  Id BIGINT IDENTITY PRIMARY KEY,
  ExecucaoId INT NOT NULL REFERENCES dbo.ConfrontoExecucao(Id),
  ParcelaId INT NOT NULL,                            -- Parcelas.Id (confirmar o tipo real da chave)
  ValorAnterior DECIMAL(15,2) NULL,
  ValorGravado DECIMAL(15,2) NOT NULL,
  Usuario VARCHAR(60) NULL, DtBaixa DATETIME NULL, DtEstorno DATETIME NULL
);
CREATE TABLE dbo.ArquivoSimplesErro (
  Id BIGINT IDENTITY PRIMARY KEY,
  Evento VARCHAR(20) NOT NULL, ArquivoId BIGINT NOT NULL, NumeroLinha INT NOT NULL,
  LinhaBruta VARCHAR(2000) NOT NULL, Erro VARCHAR(300) NOT NULL
);

-- Colunas novas nas tabelas de entrada (estão vazias: ALTER não custa migração)
ALTER TABLE dbo.PGDASDAAAAA ADD Hash CHAR(64) NULL, Usuario VARCHAR(60) NULL;
CREATE UNIQUE INDEX UX_PGDASDAAAAA_Hash ON dbo.PGDASDAAAAA (Hash) WHERE Hash IS NOT NULL;
ALTER TABLE dbo.PGDASD00000 ADD NumeroLinha INT NULL;
ALTER TABLE dbo.PGDASD01000 ADD NumeroLinha INT NULL;
ALTER TABLE dbo.PGDASD01100 ADD NumeroLinha INT NULL;
ALTER TABLE dbo.PGDASD02000 ADD NumeroLinha INT NULL;
ALTER TABLE dbo.PGDASD03000 ADD NumeroLinha INT NULL;
ALTER TABLE dbo.PGDASD03110 ADD NumeroLinha INT NULL;   -- repetir para 03100, 03111..03132 quando o layout oficial for confirmado
COMMIT;
GO

-- Vigência: a declaração mais recente (retificadora) da PA substitui as anteriores
CREATE VIEW dbo.vw_PgdasDeclaracaoVigente AS
SELECT * FROM (
  SELECT d.*, ROW_NUMBER() OVER (PARTITION BY d.Cnpjmatriz, d.Pa ORDER BY d.Pgdasd_Dt_Transmissao DESC, d.Id DESC) AS rn
  FROM dbo.PGDASD00000 d) x
WHERE rn = 1;
GO

-- Índices de apoio (Bia tem ~11,8 milhões de linhas: criar FORA do horário de pico e conferir se já existe equivalente)
CREATE INDEX IX_PGDASD00000_Cnpj_Pa ON dbo.PGDASD00000 (Cnpjmatriz, Pa) INCLUDE (Pgdasd_Dt_Transmissao, Pgdasd_Num_Recibo);
CREATE INDEX IX_PGDASD03000_Decl ON dbo.PGDASD03000 (idPGDASD00000) INCLUDE (CodTOM, CNPJ);
CREATE INDEX IX_PGDASD03110_Decl ON dbo.PGDASD03110 (idPGDASD00000, CodTOM) INCLUDE (Valor, ValorApuradoISS, AliApuradaISS);
CREATE INDEX IX_PGDASD01100_Decl ON dbo.PGDASD01100 (idPGDASD00000, codmunic) INCLUDE (valorprinc, valorm, valorj);
CREATE INDEX IX_Bia_Confronto ON dbo.Bia (AnoMes, PT, SuperSimples) INCLUDE (CodigoContribuinte, VrBruto, VrImposto, PercentualSS);
-- [PENDENTE] Contribu: o confronto normaliza o CNPJ em 14 dígitos; para não varrer 600 mil linhas, criar coluna calculada indexada:
--   ALTER TABLE dbo.Contribu ADD Cnpj14 AS RIGHT('00000000000000' + CAST(Cnpj AS VARCHAR(14)), 14) PERSISTED;
--   CREATE INDEX IX_Contribu_Cnpj14 ON dbo.Contribu (Cnpj14);   -- e trocar cnpj14() em app/db.py por 'c.Cnpj14'

-- ===== Ações do fiscal sobre as divergências (login/menu/ações) =====
CREATE TABLE dbo.ConfrontoAcao(
  Id INT IDENTITY(1,1) PRIMARY KEY, DivergenciaId INT NOT NULL, ExecucaoId INT NOT NULL,
  Tipo VARCHAR(20) NOT NULL,            -- EVENTUAL | NOTIFICACAO | CALCULO
  Referencia VARCHAR(40) NULL,          -- código do contribuinte / nº da notificação / nº do cálculo
  Usuario VARCHAR(30) NULL, DtAcao DATETIME NOT NULL DEFAULT GETDATE(), Detalhe VARCHAR(500) NULL);
CREATE INDEX IX_ConfrontoAcao_Div ON dbo.ConfrontoAcao (DivergenciaId, Tipo);
GO
CREATE TABLE dbo.SimplesNotificacao(
  Id INT IDENTITY(1,1) PRIMARY KEY, Numero VARCHAR(12) NOT NULL, Ano INT NOT NULL, DivergenciaId INT NULL, ExecucaoId INT NULL,
  CodigoContribuinte VARCHAR(20) NULL, Cnpj VARCHAR(14) NOT NULL, Pa INT NOT NULL, Codigo CHAR(3) NOT NULL,
  Assunto VARCHAR(200) NULL, Texto VARCHAR(MAX) NULL, Canal VARCHAR(30) NULL,
  Situacao CHAR(1) NULL,                -- E emitida | V enviada | F falha no envio
  DtEmissao DATETIME NOT NULL DEFAULT GETDATE(), DtPrazo DATE NULL, Usuario VARCHAR(30) NULL, Erro VARCHAR(300) NULL,
  CONSTRAINT UX_SimplesNotificacao_Numero UNIQUE (Ano, Numero));
GO
