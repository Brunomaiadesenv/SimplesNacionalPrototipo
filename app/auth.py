"""Login contra dbo.Usuario, sessão em cookie assinado (HMAC) e perfis.

Observações de segurança:
 * dbo.Usuario guarda a senha em texto (varchar(10)); o sistema legado exige esse formato, então a comparação é direta
   (com compare_digest) e a senha nunca é devolvida por nenhuma rota nem gravada em log. Recomenda-se migrar para hash.
 * Bloqueio por tentativas (5 erros em 10 min por usuário+IP), mensagem de erro única, cookie HttpOnly + SameSite=Lax.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import date, datetime

from fastapi import Depends, HTTPException, Request

from . import db, mapeamento as M
from .config import BASE, S

COOKIE = "sf_sess"
_falhas: dict = {}
MAX_FALHAS, JANELA = 5, 600


def _chave() -> bytes:
    if S.SECRET_KEY:
        return S.SECRET_KEY.encode()
    arq = BASE / "data" / "secret.key"
    arq.parent.mkdir(exist_ok=True)
    if not arq.exists():
        arq.write_text(secrets.token_hex(32))
        try:
            arq.chmod(0o600)
        except OSError:
            pass
    return arq.read_text().strip().encode()


def _assina(payload: str) -> str:
    return hmac.new(_chave(), payload.encode(), hashlib.sha256).hexdigest()


def emite_token(u: dict) -> str:
    corpo = base64.urlsafe_b64encode(json.dumps(dict(
        id=u["id"], nome=u["nome"], completo=u["completo"], adm=u["adm"], exp=int(time.time()) + S.SESSAO_HORAS * 3600)).encode()).decode()
    return corpo + "." + _assina(corpo)


def le_token(tok: str | None) -> dict | None:
    if not tok or "." not in tok:
        return None
    corpo, ass = tok.rsplit(".", 1)
    if not hmac.compare_digest(ass, _assina(corpo)):
        return None
    try:
        d = json.loads(base64.urlsafe_b64decode(corpo.encode()))
    except Exception:
        return None
    return d if d.get("exp", 0) > time.time() else None


def _data(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.fromisoformat(str(v)[:10]).date()


def _verifica_bloqueio(chave):
    n, t0 = _falhas.get(chave, (0, 0))
    if n >= MAX_FALHAS and time.time() - t0 < JANELA:
        raise HTTPException(429, f"Muitas tentativas. Aguarde {int((JANELA - (time.time() - t0)) // 60) + 1} min e tente novamente.")
    if time.time() - t0 >= JANELA:
        _falhas.pop(chave, None)


def autentica(login: str, senha: str, ip: str) -> dict:
    login = (login or "").strip()
    chave = (login.lower(), ip)
    _verifica_bloqueio(chave)
    m = M.USUARIO
    rows = db.fetch(
        f"SELECT {m['id']} AS id, {m['nome']} AS nome, {m['codigo']} AS codigo, {m['senha']} AS senha, {m['priv']} AS priv, "
        f"{m['ativo']} AS ativo, {m['ini']} AS ini, {m['exp']} AS exp, {m['completo']} AS completo "
        f"FROM {db.tb('Usuario', 'u')} WHERE UPPER({m['nome']}) = UPPER(?) OR UPPER({m['codigo']}) = UPPER(?)", [login, login]) if login else []
    u = next((r for r in rows if secrets.compare_digest(str(r["senha"] or "").encode(), (senha or "").encode()) and (senha or "")), None)
    if not u:
        n, t0 = _falhas.get(chave, (0, time.time()))
        _falhas[chave] = (n + 1, t0 if n else time.time())
        raise HTTPException(401, "Usuário ou senha inválidos.")
    hoje = date.today()
    if not u["ativo"] or (_data(u["ini"]) and _data(u["ini"]) > hoje) or (_data(u["exp"]) and _data(u["exp"]) < hoje):
        raise HTTPException(403, "Usuário inativo ou fora do período de validade. Procure o administrador.")
    _falhas.pop(chave, None)
    adm = str(u["priv"] or "").strip().upper() in S.PRIV_ADMIN
    return dict(id=u["id"], nome=(u["nome"] or "").strip(), completo=(u["completo"] or u["nome"] or "").strip(), adm=adm)


# ---- dependências do FastAPI --------------------------------------------------------------------------------
def sessao(request: Request) -> dict:
    d = le_token(request.cookies.get(COOKIE))
    if not d:
        raise HTTPException(401, "Sessão expirada. Faça login novamente.")
    return d


def auth(s: dict = Depends(sessao)) -> str:
    return s["nome"]


def admin(s: dict = Depends(sessao)) -> str:
    if not s["adm"]:
        raise HTTPException(403, "Acesso restrito a usuários com privilégio de supervisor.")
    return s["nome"]
