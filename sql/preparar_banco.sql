-- Logins do protótipo. Rode como administrador. Troque as senhas.
-- 1) LEITURA (confronto em simulação, análise, consultas): só SELECT.
CREATE LOGIN usr_simples_leitura WITH PASSWORD = 'TROCAR_Leitura#2026', CHECK_POLICY = ON;
USE SL_ISS;
CREATE USER usr_simples_leitura FOR LOGIN usr_simples_leitura;
GRANT SELECT ON dbo.PGDASDAAAAA TO usr_simples_leitura;
GRANT SELECT ON dbo.PGDASD00000 TO usr_simples_leitura;
GRANT SELECT ON dbo.PGDASD01000 TO usr_simples_leitura;
GRANT SELECT ON dbo.PGDASD01100 TO usr_simples_leitura;
GRANT SELECT ON dbo.PGDASD02000 TO usr_simples_leitura;
GRANT SELECT ON dbo.PGDASD03000 TO usr_simples_leitura;
GRANT SELECT ON dbo.PGDASD03110 TO usr_simples_leitura;
GRANT SELECT ON dbo.vw_PgdasDeclaracaoVigente TO usr_simples_leitura;
GRANT SELECT ON dbo.Contribu TO usr_simples_leitura;
GRANT SELECT ON dbo.Bia TO usr_simples_leitura;
GRANT SELECT ON dbo.Parcelas TO usr_simples_leitura;
GRANT SELECT ON dbo.SuperSimples TO usr_simples_leitura;
GRANT SELECT ON dbo.ConfrontoExecucao TO usr_simples_leitura;
GRANT SELECT ON dbo.ConfrontoDivergencia TO usr_simples_leitura;
GRANT SELECT ON dbo.ConfrontoBaixa TO usr_simples_leitura;
GRANT SELECT ON dbo.ArquivoSimplesErro TO usr_simples_leitura;
GO
-- 2) ESCRITA (só se ESCRITA_PERMITIDA=true): restrita às tabelas do módulo + a ÚNICA coluna que o confronto grava no legado.
CREATE LOGIN usr_simples_escrita WITH PASSWORD = 'TROCAR_Escrita#2026', CHECK_POLICY = ON;
USE SL_ISS;
CREATE USER usr_simples_escrita FOR LOGIN usr_simples_escrita;
GRANT SELECT ON SCHEMA::dbo TO usr_simples_escrita;                       -- ou lista de tabelas, como acima
GRANT INSERT, UPDATE ON dbo.ConfrontoExecucao TO usr_simples_escrita;
GRANT INSERT, UPDATE ON dbo.ConfrontoDivergencia TO usr_simples_escrita;
GRANT INSERT, UPDATE ON dbo.ConfrontoBaixa TO usr_simples_escrita;
GRANT INSERT ON dbo.ArquivoSimplesErro TO usr_simples_escrita;
GRANT INSERT ON dbo.PGDASDAAAAA TO usr_simples_escrita;
GRANT INSERT ON dbo.PGDASD00000 TO usr_simples_escrita;
GRANT INSERT ON dbo.PGDASD01000 TO usr_simples_escrita;
GRANT INSERT ON dbo.PGDASD01100 TO usr_simples_escrita;
GRANT INSERT ON dbo.PGDASD02000 TO usr_simples_escrita;
GRANT INSERT ON dbo.PGDASD03000 TO usr_simples_escrita;
GRANT INSERT ON dbo.PGDASD03110 TO usr_simples_escrita;
GRANT UPDATE ON dbo.Parcelas (VrAutenticadoSuperSimples) TO usr_simples_escrita;   -- regra de ouro: só esta coluna
GO
