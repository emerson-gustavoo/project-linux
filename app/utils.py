# app/utils.py
import os, time

def write_lines(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln.rstrip() + "\n")

def read_netscape_cookies(path, domain_filter="4linux.com.br"):
    now = int(time.time())
    cookies = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line or line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) < 7:
                continue

            domain, include_sub, pathc, secure, expires, name, value = parts[:7]

            # filtra pelo domínio desejado (se configurado)
            if domain_filter and domain_filter not in domain:
                continue

            # normaliza domínio (Playwright prefere sem ponto inicial)
            ndomain = domain.lstrip(".")

            # expiração (0 ou vazio => cookie de sessão => NÃO enviar "expires")
            try:
                expi = int(expires)
            except Exception:
                expi = 0

            if expi > 0 and expi < now:
                # expirado; ignora
                continue

            c = {
                "name": name,
                "value": value,
                "domain": ndomain,
                "path": pathc if pathc else "/",
                "httpOnly": False,
                "secure": (secure.upper() == "TRUE"),
                # Playwright aceita "Lax", "Strict" ou "None". Se não soubermos, omitimos.
                "sameSite": "Lax",
            }

            # só adiciona "expires" se realmente existir
            if expi > 0:
                c["expires"] = expi

            cookies.append(c)

    if not cookies:
        raise RuntimeError(f"Nenhum cookie válido encontrado em {path} para *{domain_filter}")
    return cookies