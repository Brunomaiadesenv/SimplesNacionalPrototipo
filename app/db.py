import sqlite3
import threading
from contextlib import contextmanager
from .config import S

_sem = threading.BoundedSemaphore(S.MAX_SIMULTANEAS)


class Ocupado(Exception):
    """Limite de consultas simultâneas atingido (protege o servidor)."""


class EscritaBloqueada(Exception):
    """Gravação não liberada (ESCRITA_PERMITIDA=false)."""


@contextmanager
def slot():
    if not _sem.acquire(timeout=5):
        raise Ocupado()
    try:
        yield
    finally:
        _sem.release()


def dialect() -> str:
    return "mssql" if S.DB_MODE == "sqlserver" else "sqlite"


def T(nome: str) -> str:
    """Nome da tabela conforme o banco (schema dbo no SQL Server)."""
    return f"dbo.{nome}" if dialect() == "mssql" else nome


def tb(nome: str, alias: str) -> str:
    """'dbo.Tabela alias WITH (NOLOCK)' (a dica vem DEPOIS do alias no T-SQL)."""
    h = " WITH (NOLOCK)" if dialect() == "mssql" and S.USAR_NOLOCK else ""
    return f"{T(nome)} {alias}{h}"


def cnpj14(expr: str) -> str:
    """Normaliza CNPJ para 14 dígitos com zeros à esquerda (bigint perde os zeros)."""
    if dialect() == "mssql":
        return f"RIGHT('00000000000000' + CAST({expr} AS VARCHAR(14)), 14)"
    return f"substr('00000000000000' || {expr}, -14)"


def connect(escrita: bool = False):
    if dialect() == "mssql":
        import pyodbc
        if escrita:
            if not S.ESCRITA_PERMITIDA:
                raise EscritaBloqueada()
            conn = S.SQLSERVER_CONN_ESCRITA or S.SQLSERVER_CONN
            c = pyodbc.connect(conn, autocommit=False, timeout=10)
        else:
            if not S.SQLSERVER_CONN:
                raise RuntimeError("SQLSERVER_CONN não configurada no .env")
            c = pyodbc.connect(S.SQLSERVER_CONN, autocommit=True, timeout=10)
        c.timeout = S.TIMEOUT_CONSULTA
        cur = c.cursor()
        cur.execute("SET LOCK_TIMEOUT 5000")
        cur.execute("SET DEADLOCK_PRIORITY LOW")
        if S.READ_UNCOMMITTED and not escrita:
            cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur.close()
        return c
    if escrita and not S.ESCRITA_PERMITIDA:
        raise EscritaBloqueada()
    return sqlite3.connect(S.DEMO_DB)


def fetch(sql: str, params: list | tuple = ()):
    """Executa e devolve lista de dicts. Uma conexão por chamada, sempre fechada."""
    c = connect()
    try:
        cur = c.cursor()
        cur.execute(sql, list(params))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        c.close()


def pagina(sql_base: str, params: list, order: str, off: int, n: int):
    """Paginação portável: OFFSET/FETCH (SQL Server) ou LIMIT/OFFSET (SQLite)."""
    if dialect() == "mssql":
        return f"{sql_base} ORDER BY {order} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY", params + [off, n]
    return f"{sql_base} ORDER BY {order} LIMIT ? OFFSET ?", params + [n, off]


@contextmanager
def tx():
    """Transação de escrita (commit no fim, rollback em erro). Só com escrita liberada."""
    c = connect(escrita=True)
    if dialect() == "sqlite":
        c.execute("PRAGMA foreign_keys=ON")
    cur = c.cursor()
    try:
        yield cur
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def insert_id(cur, tabela: str, dados: dict) -> int:
    cols = ", ".join(dados)
    qs = ", ".join("?" for _ in dados)
    if dialect() == "mssql":
        cur.execute(f"INSERT INTO {T(tabela)} ({cols}) OUTPUT INSERTED.Id VALUES ({qs})", list(dados.values()))
        return int(cur.fetchone()[0])
    cur.execute(f"INSERT INTO {tabela} ({cols}) VALUES ({qs})", list(dados.values()))
    return int(cur.lastrowid)


def ins(cur, tabela: str, dados: dict):
    """INSERT genérico (sem devolver chave). Colunas vêm do mapeamento, valores sempre como parâmetro."""
    dados = {k: v for k, v in dados.items() if k}
    cur.execute(f"INSERT INTO {T(tabela)} ({', '.join(dados)}) VALUES ({', '.join('?' for _ in dados)})", list(dados.values()))


def lock_hint() -> str:
    return " WITH (UPDLOCK, HOLDLOCK)" if dialect() == "mssql" else ""
