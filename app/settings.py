"""Parâmetros editáveis na tela de Configuração (arquivo data/config.json). O que está no arquivo vale mais que o .env."""
import json
import os
from pathlib import Path

from .config import BASE, S

ARQ = Path(os.environ.get("CONFIG_JSON") or BASE / "data" / "config.json")
BRASAO = ARQ.parent / "brasao.bin"
BRASAO_TIPO = ARQ.parent / "brasao.tipo"
SENHAS = ("db_senha", "db_senha_escrita", "smtp_senha")

PADRAO = dict(
    cliente="Prefeitura Municipal", municipio=None, cod_tom=None, cod_munic_01100=None,
    periodo_ini=None, periodo_fim=None,                       # período ativo do cliente (AAAAMM)
    modulo_calculo=0, grupo_calculo=0,                        # inteiros usados ao gerar cálculo
    dias_vencimento=30, dias_prazo_notificacao=15, tam_codigo=6, privilegios_admin=None,
    db_modo=None, db_driver="ODBC Driver 17 for SQL Server", db_servidor="", db_banco="SL_ISS", db_usuario="", db_senha="",
    db_usuario_escrita="", db_senha_escrita="", escrita_permitida=None, calculo_habilitado=None,
    smtp_host="", smtp_porta=587, smtp_usuario="", smtp_senha="", smtp_remetente="",
)


def _odbc(v: str) -> str:
    return "{" + str(v).replace("}", "}}") + "}"


def le() -> dict:
    cfg = dict(PADRAO)
    cfg.update(municipio=S._ENV["MUNICIPIO_NOME"], cod_tom=S._ENV["COD_TOM"], cod_munic_01100=S._ENV["COD_MUNIC_01100"],
               db_modo=S._ENV["DB_MODE"], escrita_permitida=S._ENV["ESCRITA_PERMITIDA"],
               calculo_habilitado=(S._ENV["DB_MODE"] == "demo"), privilegios_admin="S")
    if ARQ.exists():
        try:
            cfg.update(json.loads(ARQ.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def grava(cfg: dict):
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(ARQ, 0o600)
    except OSError:
        pass


def _conn(usuario, senha, escrita):
    c = le_cache
    if not c["db_servidor"]:
        return ""
    base = (f"DRIVER={_odbc(c['db_driver'])};SERVER={_odbc(c['db_servidor'])};DATABASE={_odbc(c['db_banco'])};"
            f"UID={_odbc(usuario)};PWD={_odbc(senha)};ApplicationName=FiscalSimples")
    return base if escrita else base + ";ApplicationIntent=ReadOnly"


le_cache: dict = {}


def aplica(cfg: dict | None = None):
    """Copia a configuração para S (objeto lido pelo resto do sistema)."""
    global le_cache
    cfg = cfg or le()
    le_cache = cfg
    S.CLIENTE = cfg["cliente"]
    S.MUNICIPIO_NOME = cfg["municipio"] or S._ENV["MUNICIPIO_NOME"]
    S.COD_TOM = int(cfg["cod_tom"])
    S.COD_MUNIC_01100 = int(cfg["cod_munic_01100"] or cfg["cod_tom"])
    S.PERIODO_INI = cfg["periodo_ini"]
    S.PERIODO_FIM = cfg["periodo_fim"]
    S.MODULO_CALCULO = int(cfg["modulo_calculo"] or 0)
    S.GRUPO_CALCULO = int(cfg["grupo_calculo"] or 0)
    S.DIAS_VENCIMENTO = int(cfg["dias_vencimento"])
    S.DIAS_PRAZO_NOTIF = int(cfg["dias_prazo_notificacao"])
    S.TAM_CODIGO = int(cfg["tam_codigo"])
    S.PRIV_ADMIN = [p.strip().upper() for p in str(cfg["privilegios_admin"] or "S").split(",") if p.strip()]
    S.DB_MODE = cfg["db_modo"]
    S.ESCRITA_PERMITIDA = bool(cfg["escrita_permitida"])
    S.CALCULO_HABILITADO = bool(cfg["calculo_habilitado"])
    if cfg["db_servidor"]:
        S.SQLSERVER_CONN = _conn(cfg["db_usuario"], cfg["db_senha"], False)
        S.SQLSERVER_CONN_ESCRITA = _conn(cfg["db_usuario_escrita"] or cfg["db_usuario"], cfg["db_senha_escrita"] or cfg["db_senha"], True)
    else:
        S.SQLSERVER_CONN = S._ENV["SQLSERVER_CONN"]
        S.SQLSERVER_CONN_ESCRITA = S._ENV["SQLSERVER_CONN_ESCRITA"]
    S.SMTP = dict(host=cfg["smtp_host"], porta=int(cfg["smtp_porta"] or 587), usuario=cfg["smtp_usuario"],
                  senha=cfg["smtp_senha"], remetente=cfg["smtp_remetente"])


def para_tela(cfg: dict | None = None) -> dict:
    """Configuração para a tela: NUNCA devolve senha."""
    cfg = dict(cfg or le())
    for k in SENHAS:
        cfg[k + "_definida"] = bool(cfg.get(k))
        cfg[k] = ""
    return cfg


def publico() -> dict:
    c = le_cache or le()
    return {"cliente": c["cliente"], "municipio": c["municipio"] or S.MUNICIPIO_NOME, "brasao_personalizado": BRASAO.exists()}
