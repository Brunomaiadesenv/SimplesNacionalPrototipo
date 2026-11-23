import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")


def _b(k, d):
    return os.getenv(k, str(d)).strip().lower() in ("1", "true", "sim", "yes")


class S:
    _ENV = {}
    DB_MODE = os.getenv("DB_MODE", "demo").strip().lower()
    SQLSERVER_CONN = os.getenv("SQLSERVER_CONN", "")
    SQLSERVER_CONN_ESCRITA = os.getenv("SQLSERVER_CONN_ESCRITA", "")
    DEMO_DB = os.getenv("DEMO_DB", str(BASE / "demo.db"))
    USO_DB = os.getenv("USO_DB", str(BASE / "uso.db"))
    COD_TOM = int(os.getenv("COD_TOM", "9999"))
    COD_MUNIC_01100 = int(os.getenv("COD_MUNIC_01100") or os.getenv("COD_TOM", "9999"))
    MUNICIPIO_NOME = os.getenv("MUNICIPIO_NOME", "Município Demo")
    TOLERANCIA_ABS = float(os.getenv("TOLERANCIA_ABS", "0.05"))
    TOLERANCIA_ALIQ = float(os.getenv("TOLERANCIA_ALIQ", "0.01"))
    MAX_ERRO_CARGA_PCT = float(os.getenv("MAX_ERRO_CARGA_PCT", "5"))
    # escrita: no demo é livre; no banco real só com ESCRITA_PERMITIDA=true
    ESCRITA_PERMITIDA = _b("ESCRITA_PERMITIDA", DB_MODE == "demo") if os.getenv("ESCRITA_PERMITIDA") else DB_MODE == "demo"
    TIMEOUT_CONSULTA = int(os.getenv("TIMEOUT_CONSULTA", "30"))
    MAX_SIMULTANEAS = int(os.getenv("MAX_SIMULTANEAS", "2"))
    TAM_PAGINA_MAX = int(os.getenv("TAM_PAGINA_MAX", "200"))
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
    USAR_NOLOCK = _b("USAR_NOLOCK", True)
    READ_UNCOMMITTED = _b("ISOLAMENTO_READ_UNCOMMITTED", True)
    APP_USER = os.getenv("APP_USER", "")
    APP_PASS = os.getenv("APP_PASS", "")


# valores do .env preservados (a tela de Configuração pode sobrepor os campos em S)
S._ENV = dict(MUNICIPIO_NOME=S.MUNICIPIO_NOME, COD_TOM=S.COD_TOM, COD_MUNIC_01100=S.COD_MUNIC_01100, DB_MODE=S.DB_MODE,
              ESCRITA_PERMITIDA=S.ESCRITA_PERMITIDA, SQLSERVER_CONN=S.SQLSERVER_CONN, SQLSERVER_CONN_ESCRITA=S.SQLSERVER_CONN_ESCRITA)
S.SECRET_KEY = os.getenv("SECRET_KEY", "")
S.SESSAO_HORAS = int(os.getenv("SESSAO_HORAS", "8"))
S.COOKIE_SEGURO = _b("COOKIE_SEGURO", False)
