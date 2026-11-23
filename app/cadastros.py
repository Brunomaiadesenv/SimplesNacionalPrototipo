"""CRUD de dbo.Contribu e dbo.Usuario, com validação e sem expor senha."""
import re
import uuid
from datetime import date, datetime

from . import db, mapeamento as M
from .config import S


def so_digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def valida_cpf_cnpj(d: str) -> bool:
    if len(d) == 11 and d != d[0] * 11:
        for n in (9, 10):
            s = sum(int(d[i]) * (n + 1 - i) for i in range(n))
            if int(d[n]) != (s * 10 % 11) % 10:
                return False
        return True
    if len(d) == 14 and d != d[0] * 14:
        for n, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
            s = sum(int(d[i]) * pesos[i] for i in range(n))
            r = s % 11
            if int(d[n]) != (0 if r < 2 else 11 - r):
                return False
        return True
    return False


def _pad(padrao: dict) -> dict:
    return {k: (str(uuid.uuid4()) if v == "{guid}" else v) for k, v in padrao.items()}


def _like(s: str) -> str:
    return "%" + s.replace("%", "").replace("_", "") + "%"


# =========================================================================================== contribuintes
def lista_contribuintes(q: str, pagina: int, tamanho: int):
    m = M.CONTRIBU
    cols = [f"c.{m['codigo']} AS codigo", f"c.{m['cnpj']} AS cnpj", f"c.{m['nome']} AS nome"]
    for k in ("fantasia", "email", "telefone", "simples"):
        cols.append(f"c.{m[k]} AS {k}" if m.get(k) else f"NULL AS {k}")
    where, p = "", []
    q = (q or "").strip()
    if q:
        dig = so_digitos(q)
        conds = [f"UPPER(c.{m['nome']}) LIKE UPPER(?)", f"c.{m['codigo']} LIKE ?"]
        p += [_like(q), q.replace("%", "") + "%"]
        if dig:
            conds.append(f"{db.cnpj14('c.' + m['cnpj'])} LIKE ?")
            p.append("%" + dig + "%")
        where = " WHERE " + " OR ".join(conds)
    base = f"SELECT {', '.join(cols)} FROM {db.tb(m['tabela'], 'c')}{where}"
    sql, params = db.pagina(base, p, f"c.{m['nome']}, c.{m['codigo']}", (pagina - 1) * tamanho, tamanho + 1)
    rows = db.fetch(sql, params)
    itens = []
    for r in rows[:tamanho]:
        r["cnpj"] = so_digitos(r["cnpj"]).zfill(14) if so_digitos(r["cnpj"]) and len(so_digitos(r["cnpj"])) > 11 else so_digitos(r["cnpj"]).zfill(11) if r["cnpj"] else ""
        r["tipo"] = M.TIPOS_PREFIXO.get(str(r["codigo"] or "")[:1], "—")
        itens.append(r)
    return itens, len(rows) > tamanho


def proximo_codigo(cur, prefixo: str) -> str:
    m = M.CONTRIBU
    n = S.TAM_CODIGO
    cur.execute(f"SELECT MAX({m['codigo']}) FROM {db.T(m['tabela'])}{db.lock_hint()} WHERE {m['codigo']} LIKE ? AND LENGTH({m['codigo']}) = ?"
                if db.dialect() == "sqlite" else
                f"SELECT MAX({m['codigo']}) FROM {db.T(m['tabela'])}{db.lock_hint()} WHERE {m['codigo']} LIKE ? AND LEN({m['codigo']}) = ?",
                [prefixo + "%", n])
    mx = cur.fetchone()[0]
    seq = int(str(mx)[len(prefixo):]) + 1 if mx else 1
    if len(str(seq)) > n - len(prefixo):
        raise ValueError("Faixa de códigos esgotada para este tipo; aumente o tamanho do código em Configuração.")
    return prefixo + str(seq).zfill(n - len(prefixo))


def _existe_documento(cur, dig: str) -> bool:
    m = M.CONTRIBU
    cur.execute(f"SELECT 1 FROM {db.T(m['tabela'])} c WHERE {db.cnpj14('c.' + m['cnpj'])} = ?" if len(dig) == 14 else
                f"SELECT 1 FROM {db.T(m['tabela'])} c WHERE c.{m['cnpj']} = ?", [dig.zfill(14) if len(dig) == 14 else dig])
    return cur.fetchone() is not None


def cria_contribuinte(dados: dict, prefixo: str | None, validar_dv: bool = True, cur=None) -> str:
    """Cria o contribuinte. prefixo='5' gera código sequencial do tipo Eventual. Devolve o código."""
    m = M.CONTRIBU
    dig = so_digitos(dados.get("cnpj"))
    nome = (dados.get("nome") or "").strip()
    if not nome or len(nome) > 100:
        raise ValueError("Informe a razão social / nome (até 100 caracteres).")
    if len(dig) not in (11, 14) or (validar_dv and not valida_cpf_cnpj(dig)):
        raise ValueError("CPF/CNPJ inválido.")

    def corpo(c):
        if _existe_documento(c, dig):
            raise ValueError("Já existe contribuinte cadastrado com este CPF/CNPJ.")
        cod = proximo_codigo(c, prefixo) if prefixo else str(dados.get("codigo") or "").strip()
        if not cod:
            raise ValueError("Informe o código do contribuinte.")
        c.execute(f"SELECT 1 FROM {db.T(m['tabela'])} WHERE {m['codigo']} = ?", [cod])
        if c.fetchone():
            raise ValueError(f"Código {cod} já existe.")
        valores = {m["codigo"]: cod, m["cnpj"]: dig, m["nome"]: nome}
        for k in ("fantasia", "email", "telefone"):
            if m.get(k) and dados.get(k):
                valores[m[k]] = str(dados[k]).strip()[:100]
        if m.get("simples"):
            valores[m["simples"]] = "S" if dados.get("simples", "S") == "S" else "N"
        valores.update(_pad(M.CONTRIBU_PADRAO))
        db.ins(c, m["tabela"], valores)
        return cod

    if cur is not None:
        return corpo(cur)
    with db.tx() as c:
        return corpo(c)


def atualiza_contribuinte(codigo: str, dados: dict):
    m = M.CONTRIBU
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise ValueError("Informe a razão social / nome.")
    sets, p = [f"{m['nome']} = ?"], [nome[:100]]
    for k in ("fantasia", "email", "telefone"):
        if m.get(k):
            sets.append(f"{m[k]} = ?"); p.append((dados.get(k) or "").strip()[:100] or None)
    if m.get("simples") and dados.get("simples") in ("S", "N"):
        sets.append(f"{m['simples']} = ?"); p.append(dados["simples"])
    with db.tx() as c:
        c.execute(f"UPDATE {db.T(m['tabela'])} SET {', '.join(sets)} WHERE {m['codigo']} = ?", p + [codigo])
        if c.rowcount == 0:
            raise ValueError("Contribuinte não encontrado.")


def busca_por_documento(dig: str):
    m = M.CONTRIBU
    r = db.fetch(f"SELECT c.{m['codigo']} AS codigo, c.{m['nome']} AS nome, " + (f"c.{m['email']} AS email" if m.get("email") else "NULL AS email") +
                 f" FROM {db.tb(m['tabela'], 'c')} WHERE {db.cnpj14('c.' + m['cnpj'])} = ?", [dig.zfill(14)])
    return r[0] if r else None


# =========================================================================================== usuários
def lista_usuarios(q: str):
    m = M.USUARIO
    cols = ", ".join(f"u.{m[k]} AS {k}" for k in ("id", "nome", "codigo", "priv", "ativo", "ini", "exp", "completo", "email", "cpf", "matricula"))
    where, p = "", []
    if (q or "").strip():
        where = f" WHERE UPPER(u.{m['nome']}) LIKE UPPER(?) OR UPPER(u.{m['codigo']}) LIKE UPPER(?) OR UPPER(u.{m['completo']}) LIKE UPPER(?)"
        p = [_like(q.strip())] * 3
    rows = db.fetch(f"SELECT {cols} FROM {db.tb(m['tabela'], 'u')}{where} ORDER BY u.{m['nome']}", p)
    for r in rows:
        r["ativo"] = bool(r["ativo"])
        r["admin"] = str(r["priv"] or "").strip().upper() in S.PRIV_ADMIN
        for k in ("ini", "exp"):
            r[k] = str(r[k])[:10] if r[k] else None
    return rows[:500]


def _valida_usuario(d: dict, criando: bool) -> dict:
    nome = (d.get("nome") or "").strip().upper()
    cod = (d.get("codigo") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9._-]{1,30}", nome):
        raise ValueError("Nome de usuário: até 30 caracteres, só letras, números, ponto, hífen e sublinhado.")
    if not re.fullmatch(r"[A-Z0-9]{1,5}", cod):
        raise ValueError("Código do usuário: até 5 letras/números.")
    senha = d.get("senha") or ""
    if criando and not senha:
        raise ValueError("Informe a senha.")
    if senha and not (6 <= len(senha) <= 10):
        raise ValueError("A senha deve ter de 6 a 10 caracteres (limite da tabela dbo.Usuario).")
    priv = (d.get("priv") or "").strip().upper()[:1]
    for k in ("ini", "exp"):
        if d.get(k):
            try:
                datetime.strptime(str(d[k])[:10], "%Y-%m-%d")
            except ValueError:
                raise ValueError("Datas no formato AAAA-MM-DD.")
    cpf = so_digitos(d.get("cpf"))
    if cpf and not valida_cpf_cnpj(cpf) or (cpf and len(cpf) != 11):
        raise ValueError("CPF inválido.")
    return dict(nome=nome, codigo=cod, senha=senha, priv=priv, ativo=bool(d.get("ativo", True)),
                ini=(d.get("ini") or None), exp=(d.get("exp") or None), completo=(d.get("completo") or "").strip()[:100] or None,
                email=(d.get("email") or "").strip()[:100] or None, cpf=cpf or None, matricula=(d.get("matricula") or "").strip()[:20] or None)


def _duplicado(c, v: dict, ignorar_id=None):
    m = M.USUARIO
    c.execute(f"SELECT {m['id']} FROM {db.T(m['tabela'])} WHERE (UPPER({m['nome']}) = ? OR UPPER({m['codigo']}) = ?)"
              + (f" AND {m['id']} <> ?" if ignorar_id is not None else ""), [v["nome"], v["codigo"]] + ([ignorar_id] if ignorar_id is not None else []))
    if c.fetchone():
        raise ValueError("Já existe usuário com este nome ou código.")


def cria_usuario(d: dict) -> int:
    v = _valida_usuario(d, True)
    m = M.USUARIO
    with db.tx() as c:
        _duplicado(c, v)
        c.execute(f"SELECT MAX({m['id']}) FROM {db.T(m['tabela'])}{db.lock_hint()}")
        novo = int(c.fetchone()[0] or 0) + 1       # Id não é identity na tabela real
        valores = {m["id"]: novo}
        for k in ("nome", "codigo", "senha", "priv", "ativo", "ini", "exp", "completo", "email", "cpf", "matricula"):
            valores[m[k]] = v[k] if k != "ativo" else (1 if v[k] else 0)
        valores.update(_pad(M.USUARIO_PADRAO))
        db.ins(c, m["tabela"], valores)
    return novo


def atualiza_usuario(uid: int, d: dict, quem: str):
    v = _valida_usuario(d, False)
    m = M.USUARIO
    with db.tx() as c:
        _duplicado(c, v, uid)
        c.execute(f"SELECT {m['nome']} FROM {db.T(m['tabela'])} WHERE {m['id']} = ?", [uid])
        r = c.fetchone()
        if not r:
            raise ValueError("Usuário não encontrado.")
        if str(r[0]).strip().upper() == quem.upper() and (not v["ativo"] or v["priv"] not in S.PRIV_ADMIN):
            raise ValueError("Você não pode desativar nem rebaixar o seu próprio usuário.")
        campos = ("nome", "codigo", "priv", "ativo", "ini", "exp", "completo", "email", "cpf", "matricula")
        sets = [f"{m[k]} = ?" for k in campos]
        p = [v[k] if k != "ativo" else (1 if v[k] else 0) for k in campos]
        if v["senha"]:
            sets.append(f"{m['senha']} = ?"); p.append(v["senha"])
        c.execute(f"UPDATE {db.T(m['tabela'])} SET {', '.join(sets)} WHERE {m['id']} = ?", p + [uid])
