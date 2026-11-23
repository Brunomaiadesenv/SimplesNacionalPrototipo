-- Usuário de TESTE (supervisor / 167421es) em dbo.Usuario do SL_ISS.  >>> TROQUE A SENHA ou REMOVA após os testes. <<<
-- Ajuste os valores 'N' dos flags se o domínio real for outro. Id não é identity: usa MAX+1.
BEGIN TRAN;
IF EXISTS (SELECT 1 FROM dbo.Usuario WHERE UPPER(NomeUsuario) = 'SUPERVISOR') RAISERROR('Usuário supervisor já existe.', 16, 1);
ELSE INSERT INTO dbo.Usuario
 (NomeUsuario, CodigoUsuario, Privilegio, Senha, Ativo, QtdConexoes, QtdConectado, TempoOcioso, SenhaProximoLogon, Senha30Dias,
  NomeCompleto, TpContribuNormal, TpContribuAmbulante, TpContribuEventual, TpContribuAvulso, TpContribuIrregular, TpContribuOutros,
  TpContribuMEI, TpContribuCondResidencial, Id, visualizarImpostoContribuinte, visualizarDividaContribuinte, ConCurrencyId,
  TipoDivida, IssAlterarIntimacaoFiscal)
 SELECT 'supervisor', 'SUP', 'S', '167421es', 1, 0, 0, 0, 0, 0,
  'Supervisor (usuário de teste)', 'N','N','N','N','N','N','N','N', ISNULL(MAX(Id), 0) + 1, 'N','N', CONVERT(VARCHAR(50), NEWID()),
  'N','N' FROM dbo.Usuario WITH (UPDLOCK, HOLDLOCK);
COMMIT;
