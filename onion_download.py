#!/usr/bin/env python3
"""
Descarga recursiva de un listado tipo "Index of" alojado en un servicio .onion,
a través de Tor (SOCKS5), con descargas en paralelo.

Requisitos:
    pip install "requests[socks]"

Uso:
    python onion_download.py http://xxxxxxxx.onion/carpeta/
    python onion_download.py http://xxxxxxxx.onion/carpeta/ -o descargas -w 5
    python onion_download.py http://xxxxxxxx.onion/carpeta/ --ext 7z,txt,jpg
    python onion_download.py http://xxxxxxxx.onion/carpeta/ --port 9050

Puerto de Tor: 9150 si usas Tor Browser (por defecto), 9050 si usas el servicio Tor.
"""

import argparse
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

import requests

_print_lock = threading.Lock()
_local = threading.local()
_counter_lock = threading.Lock()
_counter = 0
_run_id = uuid.uuid4().hex[:8]


def log(msg="", end="\n"):
    with _print_lock:
        print(msg, end=end, flush=True)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for key, value in attrs:
                if key == "href" and value:
                    self.links.append(value)


def make_session(port, identity=None):
    """Sesión con proxy SOCKS5 de Tor.

    Si se da 'identity', se usa como usuario SOCKS: Tor asigna un circuito
    distinto a cada identidad (aislamiento por credenciales SOCKS), de modo
    que varias sesiones no comparten el mismo circuito.
    """
    s = requests.Session()
    auth = f"{identity}:x@" if identity else ""
    proxy = f"socks5h://{auth}127.0.0.1:{port}"  # socks5h: el DNS lo resuelve Tor
    s.proxies = {"http": proxy, "https": proxy}
    s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0"
    return s


def thread_session(port, parallel):
    """Una sesión (y por tanto un circuito de Tor) por hilo."""
    global _counter
    if not hasattr(_local, "session"):
        if parallel:
            with _counter_lock:
                _counter += 1
                n = _counter
            _local.session = make_session(port, f"{_run_id}-w{n}")
        else:
            _local.session = make_session(port)
    return _local.session


def with_retries(func, retries, what):
    for attempt in range(1, retries + 1):
        try:
            return func()
        except (requests.RequestException, OSError) as e:
            wait = min(5 * attempt, 30)
            log(f"  ! Error en {what} (intento {attempt}/{retries}): {e}")
            if attempt == retries:
                raise
            log(f"    Reintentando en {wait}s...")
            time.sleep(wait)


def list_directory(session, url, retries):
    """Devuelve (subcarpetas, archivos) de un listado Index of."""

    def fetch():
        r = session.get(url, timeout=(60, 120))
        r.raise_for_status()
        return r.text

    html = with_retries(fetch, retries, f"listar {url}")
    parser = LinkParser()
    parser.feed(html)

    base = urlparse(url)
    dirs, files = [], []
    seen = set()
    for href in parser.links:
        if href.startswith(("?", "#", "mailto:", "javascript:")):
            continue
        full = urljoin(url, href)
        p = urlparse(full)
        full = p._replace(query="", fragment="").geturl()
        # Solo enlaces dentro del directorio actual (descarta "../", ordenaciones, enlaces externos)
        if p.netloc != base.netloc:
            continue
        if not p.path.startswith(base.path) or len(p.path) <= len(base.path):
            continue
        if full in seen:
            continue
        seen.add(full)
        (dirs if p.path.endswith("/") else files).append(full)
    return dirs, files


def collect_files(session, url, exts, retries):
    """Recorre recursivamente los directorios y devuelve todas las URLs de archivos."""
    log(f"[DIR] {url}")
    try:
        dirs, files = list_directory(session, url, retries)
    except requests.RequestException:
        log(f"  ! No se pudo listar {url}, se continúa con el resto.")
        return []

    result = []
    for f in files:
        if exts and not f.lower().endswith(tuple("." + e for e in exts)):
            continue
        result.append(f)
    for d in dirs:
        result.extend(collect_files(session, d, exts, retries))
    return result


def local_path(out_dir, root_url, file_url):
    root_path = urlparse(root_url).path
    rel = unquote(urlparse(file_url).path[len(root_path):])
    dest = os.path.abspath(os.path.join(out_dir, rel))
    if not dest.startswith(os.path.abspath(out_dir) + os.sep):
        raise ValueError(f"Ruta sospechosa: {rel}")
    return dest


def download_file(session, url, dest, retries, show_progress):
    """Devuelve 'skipped' o 'ok'. Lanza excepción si falla definitivamente."""
    if os.path.exists(dest):
        return "skipped"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"

    def attempt():
        pos = os.path.getsize(part) if os.path.exists(part) else 0
        headers = {"Range": f"bytes={pos}-"} if pos else {}
        with session.get(url, headers=headers, stream=True, timeout=(60, 120)) as r:
            if r.status_code == 416:  # ya estaba completo
                os.replace(part, dest)
                return
            r.raise_for_status()
            if r.status_code == 200 and pos:  # el servidor no admite Range: empezar de nuevo
                pos = 0
            mode = "ab" if pos else "wb"
            total = r.headers.get("Content-Length")
            total = int(total) + pos if total else None
            done = pos
            with open(part, mode) as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if show_progress:
                        if total:
                            log(f"\r    {done / 1e6:8.1f} / {total / 1e6:.1f} MB ({done * 100 // total}%)", end="")
                        else:
                            log(f"\r    {done / 1e6:8.1f} MB", end="")
            if show_progress:
                log()
        os.replace(part, dest)

    with_retries(attempt, retries, f"descargar {url}")
    return "ok"


def worker(url, root_url, out_dir, port, retries, parallel):
    dest = local_path(out_dir, root_url, url)
    session = thread_session(port, parallel)
    if not parallel and not os.path.exists(dest):
        log(f"  -> {dest}")
    status = download_file(session, url, dest, retries, show_progress=not parallel)
    return url, dest, status


def main():
    ap = argparse.ArgumentParser(description="Descarga recursiva de un Index of .onion vía Tor")
    ap.add_argument("url", help="URL del directorio (acabada en /)")
    ap.add_argument("-o", "--output", default="descargas", help="carpeta de destino (por defecto: descargas)")
    ap.add_argument("-p", "--port", type=int, default=9150, help="puerto SOCKS de Tor (9150 Tor Browser, 9050 servicio)")
    ap.add_argument("-w", "--workers", type=int, default=4, help="descargas simultáneas (por defecto: 4)")
    ap.add_argument("--ext", help="solo estas extensiones, separadas por comas (ej. 7z,txt,jpg)")
    ap.add_argument("--retries", type=int, default=5, help="reintentos por operación (por defecto: 5)")
    ap.add_argument("--list-only", action="store_true", help="solo listar los archivos, sin descargar")
    args = ap.parse_args()

    url = args.url if args.url.endswith("/") else args.url + "/"
    exts = [e.strip().lower().lstrip(".") for e in args.ext.split(",")] if args.ext else None
    workers = max(1, args.workers)
    parallel = workers > 1

    try:
        session = make_session(args.port)
        files = collect_files(session, url, exts, args.retries)
        log(f"\nArchivos encontrados: {len(files)}")

        if args.list_only:
            for f in files:
                log(f"  {f}")
            return

        failed, downloaded, skipped = [], 0, 0
        total = len(files)
        finished = 0

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(worker, f, url, args.output, args.port, args.retries, parallel): f
                for f in files
            }
            for fut in as_completed(futures):
                f = futures[fut]
                finished += 1
                try:
                    _, dest, status = fut.result()
                    if status == "ok":
                        downloaded += 1
                        if parallel:
                            log(f"[{finished}/{total}] Descargado: {dest}")
                    else:
                        skipped += 1
                        if parallel:
                            log(f"[{finished}/{total}] Ya existe, se omite: {dest}")
                except (requests.RequestException, OSError, ValueError) as e:
                    failed.append(f)
                    log(f"[{finished}/{total}] ! Fallo definitivo con {f}: {e}")

        log(f"\nTerminado. Descargados: {downloaded} | Omitidos (ya existían): {skipped} | Fallidos: {len(failed)}")
        if failed:
            log("Vuelve a ejecutar el script para reintentar estos:")
            for f in failed:
                log(f"  {f}")

    except KeyboardInterrupt:
        log("\nInterrumpido. Vuelve a ejecutar el script para continuar donde lo dejaste.")
        os._exit(1)


if __name__ == "__main__":
    main()
