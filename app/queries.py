"""SQL parametrizado e portável (SQL Server / SQLite). Nunca concatena valor do usuário na string."""
from .db import T, tb, cnpj14

VIG = "vw_PgdasDeclaracaoVigente"


def sql_declaracoes():
    """Declarações vigentes da PA com apuração do município. params: [tom, tom, pa]"""
    return f"""
SELECT d.Id AS decl_id, d.Cnpjmatriz AS cnpjmatriz, d.Operacao AS operacao, d.Pgdasd_Dt_Transmissao AS dt_transmissao,
       d.Pgdasd_Num_Recibo AS recibo, m.cnpj AS cnpj_est,
       i.receita AS receita, i.iss AS iss, i.aliq AS aliq,
       (SELECT SUM(x.ValorApuradoISS) FROM {tb('PGDASD03110','x')} WHERE x.idPGDASD00000 = d.Id) AS soma_03110,
       (SELECT SUM(y.ISS) FROM {tb('PGDASD02000','y')} WHERE y.idPGDASD00000 = d.Id) AS total_02000
FROM {T(VIG)} d
JOIN (SELECT idPGDASD00000 AS id, MIN(CNPJ) AS cnpj
        FROM {tb('PGDASD03000','a')} WHERE a.CodTOM = ? GROUP BY idPGDASD00000) m ON m.id = d.Id
LEFT JOIN (SELECT idPGDASD00000 AS id, SUM(Valor) AS receita, SUM(ValorApuradoISS) AS iss,
                  SUM(Valor * AliApuradaISS) / NULLIF(SUM(Valor), 0) AS aliq
             FROM {tb('PGDASD03110','b')} WHERE b.CodTOM = ? AND b.ValorApuradoISS > 0
            GROUP BY idPGDASD00000) i ON i.id = d.Id
WHERE d.Pa = ?"""


def sql_escrituracao():
    """Bia de Simples (PT='P', SuperSimples='S') agregada por CNPJ. params: [anomes]"""
    k = cnpj14("c.Cnpj")
    return f"""
SELECT {k} AS cnpj, MIN(c.CodigoContribuinte) AS cod,
       SUM(b.VrBruto) AS receita, SUM(b.VrImposto) AS iss,
       SUM(b.VrBruto * b.PercentualSS) / NULLIF(SUM(b.VrBruto), 0) AS aliq
FROM {tb('Bia','b')}
JOIN {tb('Contribu','c')} ON c.CodigoContribuinte = b.CodigoContribuinte
WHERE b.AnoMes = ? AND b.PT = 'P' AND b.SuperSimples = 'S'
GROUP BY {k}"""


def sql_cadastro(n: int):
    """Cadastro por CNPJ (lote de n). Obs.: expressão não-sargável; no real, indexar coluna calculada (README)."""
    k = cnpj14("c.Cnpj")
    qs = ",".join("?" * n)
    return f"SELECT {k} AS cnpj, MIN(c.CodigoContribuinte) AS cod FROM {tb('Contribu','c')} WHERE {k} IN ({qs}) GROUP BY {k}"


def sql_pagamento_declarado():
    """Rateio (01100) do município por declaração vigente. params: [codmunic, pa]"""
    return f"""
SELECT p.idPGDASD00000 AS decl_id, SUM(p.valorprinc) AS princ, SUM(p.valorm) AS multa, SUM(p.valorj) AS juros
FROM {T(VIG)} d
JOIN {tb('PGDASD01100','p')} ON p.idPGDASD00000 = d.Id
WHERE p.codmunic = ? AND d.Pa = ?
GROUP BY p.idPGDASD00000"""


def sql_parcelas():
    """Parcelas da competência por CNPJ. params: [anomes]. [PENDENTE 7] elo real Parcelas->Calc1->Bia."""
    k = cnpj14("c.Cnpj")
    return f"""
SELECT pa.Id AS parcela_id, {k} AS cnpj, pa.CodigoContribuinte AS cod, pa.VrAutenticadoSuperSimples AS vr_aut
FROM {tb('Parcelas','pa')}
JOIN {tb('Contribu','c')} ON c.CodigoContribuinte = pa.CodigoContribuinte
WHERE pa.AnoMes = ? AND pa.NumeroParcelamento IS NULL      -- ignora parcelas de cálculos gerados pelo módulo"""


def sql_adesao(n: int):
    qs = ",".join("?" * n)
    return (f"SELECT s.CodigoContribuinte AS cod, s.DtAdesao AS dt_adesao, s.DtCancelamento AS dt_cancel "
            f"FROM {tb('SuperSimples','s')} WHERE s.CodigoContribuinte IN ({qs})")


def sql_competencias():
    return f"SELECT DISTINCT d.Pa AS pa FROM {T(VIG)} d ORDER BY d.Pa DESC"


# ---- análise do contribuinte: as três grades -------------------------------------------------
def sql_grade1():
    """Grade 1 — arrecadação (DAS). params: [cnpj14, pa]"""
    k = cnpj14("d.Cnpjmatriz")
    return f"""
SELECT d.Id AS decl_id, d.Pgdasd_Num_Recibo AS recibo, d.Operacao AS operacao, d.Pgdasd_Dt_Transmissao AS dt_transmissao,
       p.Nrpagto AS num_pagamento, p.Princ AS principal, p.Multa AS multa, p.Juros AS juros, p.Tdevido AS total,
       p.Dtvalcalc AS dt_calculo, p.Dtvenc AS dt_vencimento
FROM {T('vw_PgdasDeclaracaoVigente')} d
LEFT JOIN {tb('PGDASD01000','p')} ON p.idPGDASD00000 = d.Id
WHERE {k} = ? AND d.Pa = ?"""


def sql_grade2():
    """Grade 2 — escrituração (Bia). params: [cnpj14, anomes]"""
    k = cnpj14("c.Cnpj")
    return f"""
SELECT b.Id AS bia_id, b.CodigoContribuinte AS cod, b.PT AS pt, b.SuperSimples AS super_simples,
       b.VrBruto AS receita, b.VrImposto AS iss, b.PercentualSS AS aliquota_ss, b.PercentualOriginal AS aliquota_original
FROM {tb('Bia','b')}
JOIN {tb('Contribu','c')} ON c.CodigoContribuinte = b.CodigoContribuinte
WHERE {k} = ? AND b.AnoMes = ?
ORDER BY b.Id"""


def sql_grade3():
    """Grade 3 — rateio por município (01100). params: [cnpj14, pa]"""
    k = cnpj14("d.Cnpjmatriz")
    return f"""
SELECT d.Id AS decl_id, p.codmunic AS codmunic, p.valorprinc AS principal, p.valorm AS multa, p.valorj AS juros
FROM {T('vw_PgdasDeclaracaoVigente')} d
JOIN {tb('PGDASD01100','p')} ON p.idPGDASD00000 = d.Id
WHERE {k} = ? AND d.Pa = ?
ORDER BY p.codmunic"""
