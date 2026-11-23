"""
MAPEAMENTO DE COLUNAS E REGRAS  (>>> ARQUIVO PARA AJUSTAR <<<)

Nomes das colunas do PGDASD* vêm do dicionário real do SL_ISS (enviado em 13/11/2026).
Os campos marcados [PENDENTE] ainda não foram confirmados no banco real: ajuste aqui e confira
com /api/verificar-colunas (com o sistema no ar).
"""

# Colunas que o confronto usa em cada tabela. /api/verificar-colunas compara com o banco.
ESPERADO = {
    "PGDASDAAAAA": ["Id", "Hash", "NomeArquivo", "DataEnvio", "QTD_LIN"],
    "PGDASD00000": ["Id", "idPGDASDAAAAA", "Pgdasd_Num_Recibo", "Cnpjmatriz", "CodTOM", "Optante", "Pa", "Rpa",
                    "Operacao", "Pgdasd_Dt_Transmissao"],
    "PGDASD01000": ["Id", "idPGDASD00000", "Nrpagto", "Princ", "Multa", "Juros", "Tdevido", "Dtvalcalc", "Dtvenc", "Vdas"],
    "PGDASD01100": ["Id", "idPGDASD00000", "codmunic", "valorprinc", "valorm", "valorj"],
    "PGDASD02000": ["Id", "idPGDASD00000", "ISS"],
    "PGDASD03000": ["Id", "idPGDASD00000", "CNPJ", "CodTOM", "Vltotal"],
    "PGDASD03110": ["Id", "idPGDASD00000", "CodTOM", "Valor", "ISS", "AliApuradaISS", "ValorApuradoISS"],
    "Contribu": ["CodigoContribuinte", "Cnpj"],                                      # [PENDENTE] nome da coluna de CNPJ
    "Bia": ["Id", "CodigoContribuinte", "AnoMes", "PT", "SuperSimples", "VrBruto", "VrImposto",
            "PercentualSS", "PercentualOriginal"],                                    # [PENDENTE] formato de AnoMes
    "Parcelas": ["Id", "CodigoContribuinte", "AnoMes", "VrAutenticadoSuperSimples"],  # [PENDENTE] elo Parcelas -> Calc1 -> Bia
    "SuperSimples": ["CodigoContribuinte", "DtAdesao", "DtCancelamento"],             # [PENDENTE] colunas reais
    "ConfrontoExecucao": ["Id", "Pa", "DtExecucao", "Usuario", "ToleranciaAbs", "Situacao"],
    "ConfrontoDivergencia": ["Id", "ExecucaoId", "DeclaracaoId", "Cnpj", "CodigoContribuinte", "Codigo",
                             "VrDeclarado", "VrEscriturado", "Tratamento", "Justificativa"],
    "ConfrontoBaixa": ["Id", "ExecucaoId", "ParcelaId", "ValorAnterior", "ValorGravado", "Usuario", "DtBaixa", "DtEstorno"],
    "ConfrontoAcao": ["Id", "DivergenciaId", "ExecucaoId", "Tipo", "Referencia", "Usuario", "DtAcao", "Detalhe"],
    "SimplesNotificacao": ["Id", "Numero", "Ano", "DivergenciaId", "ExecucaoId", "CodigoContribuinte", "Cnpj", "Pa", "Codigo",
                           "Assunto", "Texto", "Canal", "Situacao", "DtEmissao", "DtPrazo", "Usuario", "Erro"],
    "Usuario": ["Id", "NomeUsuario", "CodigoUsuario", "Senha", "Privilegio", "Ativo", "DtInicio", "DtExpiracao", "NomeCompleto"],
    "ArquivoSimplesErro": ["Id", "Evento", "ArquivoId", "NumeroLinha", "LinhaBruta", "Erro"],
}

# [PENDENTE 7] Em Parcelas, a competência não é uma coluna direta no que foi mapeado; no protótipo assumimos
# Parcelas.AnoMes (AAAAMM, texto). Se o elo real for Parcelas -> Calc1 -> Bia, ajuste app/queries.py:sql_parcelas().
FORMATO_ANOMES = "AAAAMM"

# Códigos de divergência (mesmos do Guia do programador)
DIVERGENCIAS = {
    "D00": dict(nome="Carga inconsistente", gravidade="Bloqueia",
                desc="Soma de PGDASD03110.ValorApuradoISS diferente de PGDASD02000.ISS (erro de carga/hierarquia). "
                     "A declaração fica fora do confronto."),
    "D01": dict(nome="CNPJ declarado sem cadastro", gravidade="Alta",
                desc="CNPJ de PGDASD03000 não existe em Contribu."),
    "D02": dict(nome="Declarou, não escriturou como Simples", gravidade="Alta",
                desc="Há declaração vigente com receita no município e nenhuma linha de Simples em Bia."),
    "D03": dict(nome="Escriturou como Simples, sem declaração", gravidade="Alta",
                desc="Há linha de Simples em Bia e nenhuma declaração vigente na PA."),
    "D04": dict(nome="Receita diferente", gravidade="Média",
                desc="|Σ PGDASD03110.Valor − Σ Bia.VrBruto| acima da tolerância."),
    "D05": dict(nome="ISS diferente", gravidade="Alta",
                desc="|Σ PGDASD03110.ValorApuradoISS − Σ Bia.VrImposto| acima da tolerância."),
    "D06": dict(nome="Alíquota diferente", gravidade="Média",
                desc="Alíquota ISS apurada (ponderada) diferente de Bia.PercentualSS (ponderado) acima de 0,01 p.p."),
    "D07": dict(nome="Pagamento diferente", gravidade="Alta",
                desc="Σ PGDASD01100.valorprinc do município diferente de Parcelas.VrAutenticadoSuperSimples já baixado."),
    "D08": dict(nome="Optante sem adesão vigente", gravidade="Média",
                desc="PA fora de DtAdesao–DtCancelamento em SuperSimples (contribuintes sem histórico seguem o flag do cadastro)."),
}

TRATAMENTOS = {"P": "Pendente", "J": "Justificada", "N": "Notificada", "L": "Cálculo lançado", "R": "Regularizada"}
