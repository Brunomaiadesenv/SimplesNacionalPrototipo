"""
MAPEAMENTO DAS TABELAS DO LEGADO ESCRITAS PELO MÓDULO  (>>> ARQUIVO PARA AJUSTAR <<<)

dbo.Usuario: colunas CONFIRMADAS pelo dicionário enviado. As demais (Contribu, Calc1, Parcelam, Parcelas) NÃO tiveram as
colunas confirmadas: os nomes abaixo são hipóteses [PENDENTE]. Rode sql/colunas_obrigatorias.sql no SL_ISS, ajuste os
nomes e preencha os *_PADRAO com as colunas NOT NULL sem default. Valor None em um campo = a coluna não existe, não grava.
Em {'...'} use "{guid}" para gerar um GUID novo a cada gravação.
"""

# ---- dbo.Usuario (confirmado) -------------------------------------------------------------------------------
USUARIO = dict(tabela="Usuario", id="Id", nome="NomeUsuario", codigo="CodigoUsuario", senha="Senha", priv="Privilegio",
               ativo="Ativo", ini="DtInicio", exp="DtExpiracao", completo="NomeCompleto", email="Email", cpf="Cpf",
               matricula="Matricula")
# colunas NOT NULL da tabela real que a tela não preenche. Domínio dos flags 'S'/'N' é hipótese [PENDENTE].
USUARIO_PADRAO = {
    "QtdConexoes": 0, "QtdConectado": 0, "TempoOcioso": 0, "SenhaProximoLogon": 0, "Senha30Dias": 0,
    "TpContribuNormal": "N", "TpContribuAmbulante": "N", "TpContribuEventual": "N", "TpContribuAvulso": "N",
    "TpContribuIrregular": "N", "TpContribuOutros": "N", "TpContribuMEI": "N", "TpContribuCondResidencial": "N",
    "visualizarImpostoContribuinte": "N", "visualizarDividaContribuinte": "N", "TipoDivida": "N",
    "IssAlterarIntimacaoFiscal": "N", "ConCurrencyId": "{guid}",
}
# Privilégios (Usuario.Privilegio) que acessam Configuração e Usuário. Valor 'S' = supervisor (hipótese). Também em Configuração.
PRIVILEGIOS_ADMIN = ["S"]

# ---- dbo.Contribu [PENDENTE: confirmar colunas; a tabela real tem 276] ----------------------------------------------
CONTRIBU = dict(tabela="Contribu", codigo="CodigoContribuinte", cnpj="Cnpj", nome="RazaoSocial", fantasia="NomeFantasia",
                email="Email", telefone="Telefone", simples="SuperSimples")
CONTRIBU_PADRAO = {}          # colunas NOT NULL sem default (descobrir com sql/colunas_obrigatorias.sql)
TIPOS_PREFIXO = {"5": "Eventual"}   # primeiro dígito do CodigoContribuinte -> tipo. Regra informada: 5 = Eventual.

# ---- dbo.Calc1 / dbo.Parcelam / dbo.Parcelas (geração de cálculo) [PENDENTE] -------------------------------------
CALC1 = dict(tabela="Calc1", numero="NumeroCalculo", contribuinte="CodigoContribuinte", competencia="AnoMes",
             modulo="CodigoModulo", grupo="CodigoGrupo", base="VrBase", valor="VrCalculado", data="DtCalculo",
             usuario="Usuario", origem="Origem")
CALC1_PADRAO = {}
PARCELAM = dict(tabela="Parcelam", numero="NumeroParcelamento", calculo="NumeroCalculo", contribuinte="CodigoContribuinte",
                parcela="NumeroParcela", valor="VrParcela", vencimento="DtVencimento")
PARCELAM_PADRAO = {}
PARCELAS = dict(tabela="Parcelas", contribuinte="CodigoContribuinte", competencia="AnoMes", parcelamento="NumeroParcelamento",
                parcela="NumeroParcela", valor="VrParcela", vencimento="DtVencimento", emissao="DtEmissao", qtd="QtdEmitido")
PARCELAS_PADRAO = {}
ORIGEM_CALCULO = "SIMPLES-CONFRONTO"
