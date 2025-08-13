# app/crawler.py
import re, time, random
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError
from .utils import read_netscape_cookies

COURSE_HOST = "aia.4linux.com.br"

def _abs_url(base, href):
    if not href: return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(base, href)

def _pull_module_links(html, base_url):
    out = set()
    for m in re.finditer(r"/mod/videotime/view\.php\?id=\d+", html):
        out.add(_abs_url(base_url, m.group(0)))
    return out

def _extract_vimeo_ids_from_html(html):
    ids = set()
    for m in re.finditer(r"player\.vimeo\.com/video/(\d+)", html):
        ids.add(m.group(1))
    for m in re.finditer(r'"video_id"\s*:\s*(\d+)', html):
        ids.add(m.group(1))
    return ids

def _course_id_from_url(url):
    m = re.search(r"/course/view\.php\?id=(\d+)", url)
    if m: return m.group(1)
    m = re.search(r"/mod/videotime/index\.php\?id=(\d+)", url)
    if m: return m.group(1)
    return None

def collect_vimeo_ids(course_url, cookies_path, max_sections=120, load_timeout_ms=20000, pause_between=(1200,2200), logger=print):
    def pause():
        time.sleep(random.uniform(pause_between[0]/1000.0, pause_between[1]/1000.0))

    cookies = read_netscape_cookies(cookies_path, domain_filter=COURSE_HOST)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def load(url):
            page.goto(url, wait_until="load", timeout=load_timeout_ms)
            page.wait_for_timeout(800)
            return page.content()

        logger("[1/3] Coletando links de módulos…")
        module_links = set()
        html = load(course_url); pause()
        module_links |= _pull_module_links(html, course_url)

        cid = _course_id_from_url(course_url)
        if cid:
            idx_url = f"https://{COURSE_HOST}/mod/videotime/index.php?id={cid}"
            try:
                html = load(idx_url); pause()
                module_links |= _pull_module_links(html, idx_url)
            except Exception as e:
                logger(f"  Aviso: índice do Videotime indisponível: {e}")
            logger("  Varredura por seções…")
            for s in range(0, max_sections+1):
                sec_url = f"https://{COURSE_HOST}/course/view.php?id={cid}&section={s}"
                try:
                    html = load(sec_url)
                    found = _pull_module_links(html, sec_url)
                    if found:
                        logger(f"   seção {s:03d}: +{len(found)} links")
                    module_links |= found
                except Exception:
                    pass
                pause()

        logger(f"  Total de módulos localizados: {len(module_links)}")
        if not module_links:
            raise RuntimeError("Nenhum módulo Videotime encontrado. Confirme URL/cookies.")

        logger("[2/3] Extraindo IDs…")
        ids = set()
        for i, url in enumerate(sorted(module_links), 1):
            try:
                page.goto(url, wait_until="load", timeout=load_timeout_ms)
                page.wait_for_timeout(1000)
                html = page.content()
                got = _extract_vimeo_ids_from_html(html)
                if not got:
                    # tenta disparar play algumas vezes
                    selectors = [
                        'button[aria-label*="Play"]','.vjs-big-play-button','.plyr__control',
                        '.videotime .play','.startbtn','.start-button','.big-play-button',
                        '.overlay','.click-to-play','.video-container','.plyr'
                    ]
                    for _ in range(12):
                        for sel in selectors:
                            try:
                                page.locator(sel).first.click(timeout=500)
                            except Exception:
                                pass
                        page.wait_for_timeout(600)
                        html = page.content()
                        got = _extract_vimeo_ids_from_html(html)
                        if got: break

                ids |= got
                logger(f"   ({i}/{len(module_links)}) +{len(got)}  total={len(ids)}")
            except TimeoutError:
                logger(f"   ({i}/{len(module_links)}) TIMEOUT")
            except Exception as e:
                logger(f"   ({i}/{len(module_links)}) ERRO: {e}")
            pause()

        ctx.close()
        browser.close()

    return sorted(ids), len(module_links)
