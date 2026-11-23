-- Rode no SL_ISS e envie o resultado: fecha as pendências de colunas (Contribu, Bia, Parcelas, SuperSimples, Calc1).
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN ('Contribu','Bia','Parcelas','Calc1','SuperSimples','SuperSimplesEvento','SuperSimplesExclusao','SuperSimplesRejeicao',
                     'DadosSuperSimples','ReceitaFederalSS','tabela_tom')
ORDER BY TABLE_NAME, ORDINAL_POSITION;

-- Formato de Bia.AnoMes e CNPJ em Contribu (amostra)
SELECT TOP 5 AnoMes FROM dbo.Bia WITH (NOLOCK) WHERE SuperSimples = 'S' ORDER BY Id DESC;
SELECT TOP 5 Cnpj FROM dbo.Contribu WITH (NOLOCK) WHERE Cnpj IS NOT NULL;
-- CodTOM do município
SELECT * FROM dbo.tabela_tom WHERE UPPER(CONVERT(VARCHAR(100), nome)) LIKE '%SANTA LUZIA%';   -- ajuste o nome da coluna
