#!/usr/bin/env python3
"""Launch the independent local consultation interface for OpenWordnet-PT."""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from consult.server import consult_url_if_running, port_is_free, serve
from consult.store import OwnptStore, build_index, default_paths, index_is_current


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Interface independente para consultar o repositório OpenWordnet-PT."
    )
    parser.add_argument("--port", type=int, default=8765, help="Porta HTTP local (predefinição: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Endereço de escuta")
    parser.add_argument("--rebuild", action="store_true", help="Reconstrói o índice a partir dos ficheiros RDF")
    parser.add_argument("--no-browser", action="store_true", help="Não abrir o navegador")
    parser.add_argument("--query", metavar="TERMO", help="Pesquisa rápida no terminal e sai")
    args = parser.parse_args()

    data_dir, db_path = default_paths(ROOT)
    if not os.path.isdir(data_dir):
        print(f"Pasta de dados não encontrada: {data_dir}", file=sys.stderr)
        return 1

    if args.rebuild or not index_is_current(db_path, data_dir):
        print("A construir o índice local a partir dos RDF (só na primeira vez ou após alterações)...")
        build_index(data_dir, db_path, progress=print)
    else:
        print(f"A usar o índice existente: {db_path}")

    store = OwnptStore(db_path)
    if args.query:
        hits = store.search(args.query, lang="all", mode="prefix")
        if not hits:
            print("Sem resultados.")
            store.close()
            return 0
        for hit in hits:
            lemmas = ", ".join(hit["lemmas"][:6]) or hit["matched_lemma"]
            other = f" | {', '.join(hit['other_lemmas'][:4])}" if hit["other_lemmas"] else ""
            gloss = f" — {hit['gloss']}" if hit["gloss"] else ""
            line = f"{hit['id']}  [{hit['pos']}]  {lemmas}{other}{gloss}"
            try:
                print(line)
            except UnicodeEncodeError:
                print(line.encode("utf-8", "replace").decode("ascii", "replace"))
        store.close()
        return 0

    existing = consult_url_if_running(args.host, args.port)
    if existing:
        print(f"A interface já está a correr: {existing}", flush=True)
        store.close()
        if not args.no_browser:
            webbrowser.open(existing)
        return 0

    port = args.port
    if not port_is_free(args.host, port):
        for candidate in range(args.port + 1, args.port + 20):
            if port_is_free(args.host, candidate):
                port = candidate
                print(f"Porta {args.port} ocupada; a usar {port}.", flush=True)
                break
        else:
            print(
                f"Porta {args.port} ocupada e não há alternativa livre. "
                "Feche a outra instância ou use --port.",
                file=sys.stderr,
            )
            store.close()
            return 1

    httpd = serve(store, host=args.host, port=port)
    url = f"http://{args.host}:{port}/"
    print(f"Interface de consulta: {url}", flush=True)
    print("Ctrl+C para terminar.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nA encerrar.")
    finally:
        httpd.server_close()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
