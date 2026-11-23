-- Colunas NOT NULL sem default (precisam entrar em app/mapeamento.py: *_PADRAO) e todas as colunas das tabelas que o módulo grava.
SELECT t.name AS tabela, c.column_id, c.name AS coluna, ty.name AS tipo, c.max_length, c.is_nullable, c.is_identity,
       CASE WHEN dc.object_id IS NULL THEN 0 ELSE 1 END AS tem_default
FROM sys.columns c
JOIN sys.tables t ON t.object_id = c.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.default_constraints dc ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
WHERE t.name IN ('Contribu','Calc1','Parcelam','Parcelas') AND SCHEMA_NAME(t.schema_id) = 'dbo'
ORDER BY CASE WHEN c.is_nullable = 0 AND dc.object_id IS NULL AND c.is_identity = 0 THEN 0 ELSE 1 END, t.name, c.column_id;
-- As linhas do topo (is_nullable = 0, tem_default = 0, is_identity = 0) são as obrigatórias.
