"""SQLite index and query layer for the local OWN-PT repository."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import unicodedata
from collections import defaultdict
from typing import Callable

from .turtle import (
    iter_triples,
    local_name,
    resource_lang,
    sense_id_from,
    synset_id_from,
    word_id_from,
)

SCHEMA_VERSION = "1"
POS_LABELS = {
    "n": {"pt": "substantivo", "en": "noun"},
    "v": {"pt": "verbo", "en": "verb"},
    "a": {"pt": "adjetivo", "en": "adjective"},
    "s": {"pt": "adjetivo satélite", "en": "satellite adjective"},
    "r": {"pt": "advérbio", "en": "adverb"},
}

REL_META = {
    "hyponymOf": {"pt": "é um tipo de", "en": "hypernym", "inv_pt": "tem como tipos", "inv_en": "hyponyms"},
    "hypernymOf": {"pt": "tem como tipos", "en": "hyponyms", "inv_pt": "é um tipo de", "inv_en": "hypernym"},
    "instanceOf": {"pt": "é instância de", "en": "instance of", "inv_pt": "tem instâncias", "inv_en": "instances"},
    "hasInstance": {"pt": "tem instâncias", "en": "instances", "inv_pt": "é instância de", "inv_en": "instance of"},
    "antonymOf": {"pt": "antónimo", "en": "antonym", "inv_pt": "antónimo", "inv_en": "antonym"},
    "similarTo": {"pt": "similar a", "en": "similar to", "inv_pt": "similar a", "inv_en": "similar to"},
    "entails": {"pt": "implica", "en": "entails", "inv_pt": "é implicado por", "inv_en": "is entailed by"},
    "entailedBy": {"pt": "é implicado por", "en": "is entailed by", "inv_pt": "implica", "inv_en": "entails"},
    "causes": {"pt": "causa", "en": "causes", "inv_pt": "é causado por", "inv_en": "is caused by"},
    "causedBy": {"pt": "é causado por", "en": "is caused by", "inv_pt": "causa", "inv_en": "causes"},
    "seeAlso": {"pt": "ver também", "en": "see also", "inv_pt": "ver também", "inv_en": "see also"},
    "attribute": {"pt": "atributo", "en": "attribute", "inv_pt": "é atributo de", "inv_en": "attribute of"},
    "attributeOf": {"pt": "é atributo de", "en": "attribute of", "inv_pt": "atributo", "inv_en": "attribute"},
    "classifiedByTopic": {"pt": "domínio (tópico)", "en": "domain topic", "inv_pt": "membros do tópico", "inv_en": "topic members"},
    "classifiesByTopic": {"pt": "membros do tópico", "en": "topic members", "inv_pt": "domínio (tópico)", "inv_en": "domain topic"},
    "classifiedByRegion": {"pt": "domínio (região)", "en": "domain region", "inv_pt": "membros da região", "inv_en": "region members"},
    "classifiesByRegion": {"pt": "membros da região", "en": "region members", "inv_pt": "domínio (região)", "inv_en": "domain region"},
    "classifiedByUsage": {"pt": "domínio (uso)", "en": "domain usage", "inv_pt": "membros de uso", "inv_en": "usage members"},
    "classifiesByUsage": {"pt": "membros de uso", "en": "usage members", "inv_pt": "domínio (uso)", "inv_en": "domain usage"},
    "memberMeronymOf": {"pt": "membro de", "en": "member of", "inv_pt": "tem membros", "inv_en": "has members"},
    "memberHolonymOf": {"pt": "tem membros", "en": "has members", "inv_pt": "membro de", "inv_en": "member of"},
    "partMeronymOf": {"pt": "parte de", "en": "part of", "inv_pt": "tem partes", "inv_en": "has parts"},
    "partHolonymOf": {"pt": "tem partes", "en": "has parts", "inv_pt": "parte de", "inv_en": "part of"},
    "substanceMeronymOf": {"pt": "substância de", "en": "substance of", "inv_pt": "tem substância", "inv_en": "has substance"},
    "substanceHolonymOf": {"pt": "tem substância", "en": "has substance", "inv_pt": "substância de", "inv_en": "substance of"},
    "meronymOf": {"pt": "merónimo de", "en": "meronym of", "inv_pt": "holónimo de", "inv_en": "holonym of"},
    "holonymOf": {"pt": "holónimo de", "en": "holonym of", "inv_pt": "merónimo de", "inv_en": "meronym of"},
    "derivationallyRelated": {"pt": "derivação", "en": "derivation", "inv_pt": "derivação", "inv_en": "derivation"},
    "adjectivePertainsTo": {"pt": "pertence a", "en": "pertains to", "inv_pt": "tem adjetivo", "inv_en": "has pertainym"},
    "adverbPertainsTo": {"pt": "pertence a", "en": "pertains to", "inv_pt": "tem advérbio", "inv_en": "has adverb"},
    "participleOf": {"pt": "particípio de", "en": "participle of", "inv_pt": "tem particípio", "inv_en": "has participle"},
    "sameVerbGroupAs": {"pt": "mesmo grupo verbal", "en": "verb group", "inv_pt": "mesmo grupo verbal", "inv_en": "verb group"},
}

SKIP_PREDICATES = {
    "a",
    "rdf:type",
    "skos:inScheme",
    "owns:offset",
    "owns:synsetId",
    "owns:wordNumber",
    "owns:lemma",
    "owns:pos",
    "owns:gloss",
    "owns:example",
    "owns:frame",
    "owns:lexicographerFile",
    "owns:otherForm",
    "owns:containsWordSense",
    "owns:word",
    "owns:inSynset",
    "owns:sense",
    "rdfs:label",
    "owl:sameAs",
    "dc:provenance",
    "owns:noun",
    "owns:verb",
    "owns:plural",
}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", (text or "").strip().lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def default_paths(repo_root: str) -> tuple[str, str]:
    data_dir = os.path.join(repo_root, "data")
    db_path = os.path.join(repo_root, "consult", "ownpt.sqlite")
    return data_dir, db_path


def connect(db_path: str, *, threaded: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=not threaded)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def index_is_current(db_path: str, data_dir: str) -> bool:
    if not os.path.exists(db_path):
        return False
    try:
        conn = connect(db_path)
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            built = conn.execute("SELECT value FROM meta WHERE key='built_from'").fetchone()
            if not version or version[0] != SCHEMA_VERSION or not built:
                return False
            stamp = float(built[0])
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    newest = 0.0
    for name in os.listdir(data_dir):
        if name.endswith(".ttl"):
            newest = max(newest, os.path.getmtime(os.path.join(data_dir, name)))
    return stamp >= newest


def build_index(data_dir: str, db_path: str, progress: Callable[[str], None] | None = None) -> None:
    def log(message: str) -> None:
        if progress:
            progress(message)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-80000")
    _create_schema(conn)

    words: dict[tuple[str, str], dict] = {}
    senses: dict[tuple[str, str], dict] = {}
    synsets: dict[tuple[str, str], dict] = {}
    relations: list[tuple] = []
    nomlex_buf: dict[str, dict] = {}

    files = [
        ("own-pt-words.ttl", "words"),
        ("own-en-words.ttl", "words"),
        ("own-pt-wordsenses.ttl", "senses"),
        ("own-en-wordsenses.ttl", "senses"),
        ("own-pt-synsets.ttl", "synsets"),
        ("own-en-synsets.ttl", "synsets"),
        ("own-pt-relations.ttl", "relations"),
        ("own-en-relations.ttl", "relations"),
        ("own-pt-morphosemantic-links.ttl", "nomlex"),
        ("own-en-morphosemantic-links.ttl", "nomlex"),
    ]

    started = time.time()
    for filename, kind in files:
        path = os.path.join(data_dir, filename)
        if not os.path.exists(path):
            continue
        log(f"A indexar {filename}...")
        count = 0
        for subj, pred, obj in iter_triples(path):
            count += 1
            if kind == "words":
                _ingest_word(subj, pred, obj, words, senses)
            elif kind == "senses":
                _ingest_sense(subj, pred, obj, senses)
            elif kind == "synsets":
                _ingest_synset(subj, pred, obj, synsets)
            elif kind == "relations":
                _ingest_relation(subj, pred, obj, relations)
            else:
                _ingest_nomlex(subj, pred, obj, nomlex_buf)
        log(f"  {count:,} triplos em {filename}")

    log("A gravar o índice SQLite...")
    conn.executemany(
        """INSERT OR REPLACE INTO words(word_id, lang, lemma, lemma_norm, pos)
           VALUES (?, ?, ?, ?, ?)""",
        [
            (wid, lang, rec["lemma"], normalize(rec["lemma"]), rec["pos"])
            for (wid, lang), rec in words.items()
            if rec.get("lemma")
        ],
    )
    conn.executemany(
        """INSERT OR REPLACE INTO senses(sense_id, lang, synset_id, lemma, lemma_norm, word_id, word_number, pos)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                sid,
                lang,
                rec.get("synset_id") or synset_id_from(sid),
                rec.get("lemma") or "",
                normalize(rec.get("lemma") or ""),
                rec.get("word_id") or "",
                rec.get("word_number") or 0,
                rec.get("pos") or (rec.get("synset_id") or synset_id_from(sid))[-1:],
            )
            for (sid, lang), rec in senses.items()
        ],
    )
    conn.executemany(
        """INSERT OR REPLACE INTO synsets(synset_id, lang, pos, gloss, examples, flags, lexfile)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                syn_id,
                lang,
                rec.get("pos") or syn_id[-1:],
                "\n".join(rec.get("glosses") or []),
                "\n".join(rec.get("examples") or []),
                ",".join(rec.get("flags") or []),
                rec.get("lexfile") or "",
            )
            for (syn_id, lang), rec in synsets.items()
        ],
    )
    conn.executemany(
        """INSERT INTO relations(source_id, target_id, source_synset, target_synset, rel, lang, kind)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        relations,
    )
    nomlex_rows = [
        (name, rec.get("verb") or "", rec.get("noun") or "", rec.get("prov") or "", ",".join(rec.get("flags") or []))
        for name, rec in nomlex_buf.items()
        if rec.get("verb") or rec.get("noun")
    ]
    if nomlex_rows:
        conn.executemany(
            """INSERT OR REPLACE INTO nomlex(nomlex_id, verb_word, noun_word, provenance, flags)
               VALUES (?, ?, ?, ?, ?)""",
            nomlex_rows,
        )

    _fill_sense_lemmas_from_words(conn)
    _link_senses_to_words(conn)
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        ("schema", SCHEMA_VERSION),
    )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        ("built_from", str(time.time())),
    )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        ("stats", json.dumps(_compute_stats(conn))),
    )
    conn.commit()
    conn.close()
    log(f"Indice pronto em {time.time() - started:.1f}s -> {db_path}")


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE words (
            word_id TEXT NOT NULL,
            lang TEXT NOT NULL,
            lemma TEXT NOT NULL,
            lemma_norm TEXT NOT NULL,
            pos TEXT,
            PRIMARY KEY (word_id, lang)
        );
        CREATE TABLE senses (
            sense_id TEXT NOT NULL,
            lang TEXT NOT NULL,
            synset_id TEXT NOT NULL,
            lemma TEXT,
            lemma_norm TEXT,
            word_id TEXT,
            word_number INTEGER,
            pos TEXT,
            PRIMARY KEY (sense_id, lang)
        );
        CREATE TABLE synsets (
            synset_id TEXT NOT NULL,
            lang TEXT NOT NULL,
            pos TEXT,
            gloss TEXT,
            examples TEXT,
            flags TEXT,
            lexfile TEXT,
            PRIMARY KEY (synset_id, lang)
        );
        CREATE TABLE relations (
            source_id TEXT,
            target_id TEXT,
            source_synset TEXT,
            target_synset TEXT,
            rel TEXT,
            lang TEXT,
            kind TEXT
        );
        CREATE TABLE nomlex (
            nomlex_id TEXT PRIMARY KEY,
            verb_word TEXT,
            noun_word TEXT,
            provenance TEXT,
            flags TEXT
        );
        CREATE INDEX idx_words_lemma ON words(lang, lemma_norm);
        CREATE INDEX idx_senses_lemma ON senses(lang, lemma_norm);
        CREATE INDEX idx_senses_syn ON senses(lang, synset_id);
        CREATE INDEX idx_rel_src ON relations(lang, source_synset);
        CREATE INDEX idx_rel_tgt ON relations(lang, target_synset);
        CREATE INDEX idx_nomlex_verb ON nomlex(verb_word);
        CREATE INDEX idx_nomlex_noun ON nomlex(noun_word);
        """
    )


def _word_rec(store: dict, word_id: str, lang: str) -> dict:
    return store.setdefault((word_id, lang), {"lemma": "", "pos": ""})


def _sense_rec(store: dict, sense_id: str, lang: str) -> dict:
    return store.setdefault(
        (sense_id, lang),
        {"synset_id": synset_id_from(sense_id), "lemma": "", "word_id": "", "word_number": 0, "pos": ""},
    )


def _syn_rec(store: dict, syn_id: str, lang: str) -> dict:
    return store.setdefault(
        (syn_id, lang),
        {"pos": syn_id[-1:] if syn_id else "", "glosses": [], "examples": [], "flags": [], "lexfile": ""},
    )


def _ingest_word(subj: str, pred: str, obj, words: dict, senses: dict) -> None:
    lang = resource_lang(subj)
    name = local_name(subj)
    if name.startswith("word-"):
        rec = _word_rec(words, name, lang)
        if pred in {"owns:lemma"} and isinstance(obj, tuple):
            rec["lemma"] = obj[0]
        elif pred in {"owns:pos"} and isinstance(obj, tuple):
            rec["pos"] = obj[0]
        elif pred == "a" and isinstance(obj, str) and obj.endswith("Word"):
            rec["pos"] = rec["pos"] or name.rsplit("-", 1)[-1]
    elif name.startswith("wordsense-") and pred == "owns:word" and isinstance(obj, str):
        rec = _sense_rec(senses, name, lang)
        rec["word_id"] = word_id_from(obj)


def _ingest_sense(subj: str, pred: str, obj, senses: dict) -> None:
    lang = resource_lang(subj)
    name = local_name(subj)
    if pred == "owns:containsWordSense" and isinstance(obj, str):
        sense_id = sense_id_from(obj)
        rec = _sense_rec(senses, sense_id, lang)
        rec["synset_id"] = synset_id_from(subj)
        rec["pos"] = rec["synset_id"][-1:]
        return
    if name.startswith("wordsense-"):
        rec = _sense_rec(senses, name, lang)
        if pred == "rdfs:label" and isinstance(obj, tuple):
            rec["lemma"] = obj[0]
        elif pred == "owns:wordNumber" and isinstance(obj, tuple):
            try:
                rec["word_number"] = int(obj[0])
            except ValueError:
                rec["word_number"] = 0
        elif pred == "owns:word" and isinstance(obj, str):
            rec["word_id"] = word_id_from(obj)


def _ingest_synset(subj: str, pred: str, obj, synsets: dict) -> None:
    if not local_name(subj).startswith("synset-"):
        return
    lang = resource_lang(subj)
    syn_id = synset_id_from(subj)
    rec = _syn_rec(synsets, syn_id, lang)
    if pred == "a" and isinstance(obj, str):
        flag = local_name(obj)
        if flag in {"BaseConcept", "CoreConcept"}:
            rec["flags"].append(flag)
        pos_map = {
            "NounSynset": "n",
            "VerbSynset": "v",
            "AdjectiveSynset": "a",
            "AdjectiveSatelliteSynset": "s",
            "AdverbSynset": "r",
        }
        if flag in pos_map:
            rec["pos"] = pos_map[flag]
    elif pred == "owns:gloss" and isinstance(obj, tuple):
        rec["glosses"].append(obj[0])
    elif pred == "owns:example" and isinstance(obj, tuple):
        rec["examples"].append(obj[0])
    elif pred == "owns:lexicographerFile" and isinstance(obj, tuple):
        rec["lexfile"] = obj[0]


def _ingest_relation(subj: str, pred: str, obj, relations: list) -> None:
    if not isinstance(obj, str) or pred in SKIP_PREDICATES:
        return
    rel = local_name(pred)
    if rel in {"lemma", "pos", "gloss", "example", "word", "containsWordSense", "wordNumber"}:
        return
    lang = resource_lang(subj)
    source = local_name(subj)
    target = local_name(obj)
    kind = "sense" if source.startswith("wordsense-") or target.startswith("wordsense-") else "synset"
    relations.append(
        (
            source,
            target,
            synset_id_from(subj),
            synset_id_from(obj),
            rel,
            lang,
            kind,
        )
    )


def _ingest_nomlex(subj: str, pred: str, obj, nomlex_buf: dict) -> None:
    name = local_name(subj)
    rec = nomlex_buf.setdefault(name, {"verb": "", "noun": "", "prov": "", "flags": []})
    if pred == "a" and isinstance(obj, str):
        flag = local_name(obj)
        if flag not in {"Nominalization"} and flag not in rec["flags"]:
            rec["flags"].append(flag)
    elif pred == "owns:verb" and isinstance(obj, str):
        rec["verb"] = word_id_from(obj)
    elif pred == "owns:noun" and isinstance(obj, str):
        rec["noun"] = word_id_from(obj)
    elif pred == "dc:provenance" and isinstance(obj, tuple):
        rec["prov"] = obj[0]


def _link_senses_to_words(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE senses
        SET word_id = (
            SELECT w.word_id FROM words w
            WHERE w.lang = senses.lang
              AND w.lemma = senses.lemma
              AND (w.pos = senses.pos OR w.pos = '' OR senses.pos = '')
            LIMIT 1
        )
        WHERE (word_id IS NULL OR word_id = '') AND lemma != ''
        """
    )


def _fill_sense_lemmas_from_words(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE senses
        SET lemma = (
            SELECT w.lemma FROM words w
            WHERE w.word_id = senses.word_id AND w.lang = senses.lang
        ),
        lemma_norm = (
            SELECT w.lemma_norm FROM words w
            WHERE w.word_id = senses.word_id AND w.lang = senses.lang
        )
        WHERE (lemma IS NULL OR lemma = '') AND word_id IS NOT NULL AND word_id != ''
        """
    )


def _compute_stats(conn: sqlite3.Connection) -> dict:
    def count(sql: str, args: tuple = ()) -> int:
        return conn.execute(sql, args).fetchone()[0]

    return {
        "pt_words": count("SELECT COUNT(*) FROM words WHERE lang='pt'"),
        "en_words": count("SELECT COUNT(*) FROM words WHERE lang='en'"),
        "pt_synsets": count("SELECT COUNT(*) FROM synsets WHERE lang='pt'"),
        "en_synsets": count("SELECT COUNT(*) FROM synsets WHERE lang='en'"),
        "pt_senses": count("SELECT COUNT(*) FROM senses WHERE lang='pt'"),
        "en_senses": count("SELECT COUNT(*) FROM senses WHERE lang='en'"),
        "relations": count("SELECT COUNT(*) FROM relations"),
        "nomlex": count("SELECT COUNT(*) FROM nomlex"),
    }


class OwnptStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = connect(db_path, threaded=True)
        self._lock = threading.Lock()

    def close(self) -> None:
        self.conn.close()

    def _execute(self, sql: str, args: tuple = ()):
        with self._lock:
            return self.conn.execute(sql, args).fetchall()

    def _execute_one(self, sql: str, args: tuple = ()):
        with self._lock:
            return self.conn.execute(sql, args).fetchone()

    def stats(self) -> dict:
        row = self._execute_one("SELECT value FROM meta WHERE key='stats'")
        if row:
            return json.loads(row[0])
        return _compute_stats(self.conn)

    def suggest(self, query: str, lang: str = "pt", limit: int = 18) -> list[str]:
        needle = normalize(query)
        if len(needle) < 2:
            return []
        rows = self.conn.execute(
            """
            SELECT DISTINCT lemma FROM senses
            WHERE lang = ? AND lemma_norm LIKE ? AND lemma != ''
            ORDER BY length(lemma), lemma
            LIMIT ?
            """,
            (lang, f"{needle}%", limit),
        ).fetchall()
        return [row["lemma"] for row in rows]

    def search(self, query: str, lang: str = "all", pos: str = "", mode: str = "prefix", limit: int = 80) -> list[dict]:
        raw = (query or "").strip()
        if not raw:
            return []
        if _looks_like_synset(raw):
            syn = self.synset(raw.lower())
            return [self._search_hit_from_synset(syn)] if syn else []

        needle = normalize(raw)
        langs = ["pt", "en"] if lang == "all" else [lang]
        if mode == "exact":
            clause = "s.lemma_norm = ?"
            arg = needle
        elif mode == "contains":
            clause = "s.lemma_norm LIKE ?"
            arg = f"%{needle}%"
        else:
            clause = "s.lemma_norm LIKE ?"
            arg = f"{needle}%"

        pos_clause = "AND s.pos = ?" if pos else ""
        params: list = []
        hits: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for lg in langs:
            sql = f"""
                SELECT s.synset_id, s.lang, s.pos, s.lemma, s.word_number, syn.gloss
                FROM senses s
                LEFT JOIN synsets syn ON syn.synset_id = s.synset_id AND syn.lang = s.lang
                WHERE s.lang = ? AND {clause} AND s.lemma != '' {pos_clause}
                ORDER BY s.pos, s.lemma
                LIMIT ?
            """
            params = [lg, arg]
            if pos:
                params.append(pos)
            params.append(limit)
            for row in self.conn.execute(sql, params):
                key = (row["synset_id"], row["lang"])
                if key in seen:
                    continue
                seen.add(key)
                hits.append(self._hit_dict(row, raw))
        needle_len = len(needle)
        hits.sort(
            key=lambda item: (
                0 if normalize(item["matched_lemma"]) == needle else 1,
                0 if item.get("has_gloss") else 1,
                0 if item["lang"] == "pt" else 1,
                item.get("word_number") or 99,
                abs(len(normalize(item["matched_lemma"])) - needle_len),
                item["pos"],
                item["matched_lemma"].lower(),
            )
        )
        return hits[:limit]

    def synset(self, synset_id: str) -> dict | None:
        synset_id = synset_id.strip()
        rows = self.conn.execute(
            "SELECT * FROM synsets WHERE synset_id = ?",
            (synset_id,),
        ).fetchall()
        if not rows:
            sense_rows = self.conn.execute(
                "SELECT DISTINCT synset_id FROM senses WHERE synset_id = ?",
                (synset_id,),
            ).fetchall()
            if not sense_rows:
                return None
        by_lang = {row["lang"]: dict(row) for row in rows}
        pt = by_lang.get("pt", {})
        en = by_lang.get("en", {})
        pos = pt.get("pos") or en.get("pos") or synset_id[-1:]
        payload = {
            "id": synset_id,
            "pos": pos,
            "pos_label": POS_LABELS.get(pos, {"pt": pos, "en": pos}),
            "flags": [flag for flag in (pt.get("flags") or en.get("flags") or "").split(",") if flag],
            "lexfile": en.get("lexfile") or pt.get("lexfile") or "",
            "pt": self._lang_block("pt", synset_id, pt),
            "en": self._lang_block("en", synset_id, en),
            "relations": self._relations_for(synset_id),
            "hypernym_path": self._hypernym_path(synset_id),
            "nominalizations": self._nomlex_for(synset_id),
        }
        return payload

    def random_synset(self) -> dict | None:
        row = self.conn.execute(
            """
            SELECT synset_id FROM synsets
            WHERE lang='pt' AND gloss != ''
            ORDER BY RANDOM() LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        return self.synset(row["synset_id"])

    def _lang_block(self, lang: str, synset_id: str, row: dict) -> dict:
        lemmas = [
            item["lemma"]
            for item in self.conn.execute(
                """
                SELECT lemma, word_number FROM senses
                WHERE lang=? AND synset_id=? AND lemma != ''
                ORDER BY word_number, lemma
                """,
                (lang, synset_id),
            )
        ]
        seen = set()
        unique = []
        for lemma in lemmas:
            key = lemma.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(lemma)
        return {
            "lemmas": unique,
            "gloss": (row.get("gloss") or "").split("\n") if row else [],
            "examples": [ex for ex in (row.get("examples") or "").split("\n") if ex] if row else [],
        }

    def _relations_for(self, synset_id: str) -> list[dict]:
        outgoing = self.conn.execute(
            """
            SELECT rel, target_synset AS other, kind, 'out' AS direction
            FROM relations
            WHERE source_synset=? AND lang='pt'
            """,
            (synset_id,),
        ).fetchall()
        incoming = self.conn.execute(
            """
            SELECT rel, source_synset AS other, kind, 'in' AS direction
            FROM relations
            WHERE target_synset=? AND lang='pt'
            """,
            (synset_id,),
        ).fetchall()
        inverse = {
            "hyponymOf": "hypernymOf",
            "hypernymOf": "hyponymOf",
            "instanceOf": "hasInstance",
            "hasInstance": "instanceOf",
            "partMeronymOf": "partHolonymOf",
            "partHolonymOf": "partMeronymOf",
            "memberMeronymOf": "memberHolonymOf",
            "memberHolonymOf": "memberMeronymOf",
            "substanceMeronymOf": "substanceHolonymOf",
            "substanceHolonymOf": "substanceMeronymOf",
            "entails": "entailedBy",
            "entailedBy": "entails",
            "causes": "causedBy",
            "causedBy": "causes",
            "attribute": "attributeOf",
            "attributeOf": "attribute",
            "classifiedByTopic": "classifiesByTopic",
            "classifiesByTopic": "classifiedByTopic",
            "classifiedByRegion": "classifiesByRegion",
            "classifiesByRegion": "classifiedByRegion",
            "classifiedByUsage": "classifiesByUsage",
            "classifiesByUsage": "classifiedByUsage",
        }
        grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
        for row in list(outgoing) + list(incoming):
            other = row["other"]
            if not other or other == synset_id:
                continue
            rel = row["rel"]
            direction = row["direction"]
            if direction == "in" and rel in inverse:
                rel = inverse[rel]
                direction = "out"
            grouped[(rel, direction)].append(other)

        blocks = []
        for (rel, direction), others in grouped.items():
            meta = REL_META.get(rel, {})
            if direction == "out":
                label_pt = meta.get("pt", rel)
                label_en = meta.get("en", rel)
            else:
                label_pt = meta.get("inv_pt", f"{rel} (inverso)")
                label_en = meta.get("inv_en", f"{rel} (inverse)")
            unique_others = list(dict.fromkeys(others))
            blocks.append(
                {
                    "rel": rel,
                    "direction": direction,
                    "label_pt": label_pt,
                    "label_en": label_en,
                    "targets": [self._brief_synset(other_id) for other_id in unique_others[:80]],
                }
            )
        rank = {
            "hyponymOf": 0,
            "hypernymOf": 1,
            "instanceOf": 2,
            "hasInstance": 3,
            "partMeronymOf": 4,
            "partHolonymOf": 5,
            "memberMeronymOf": 6,
            "memberHolonymOf": 7,
            "antonymOf": 8,
            "similarTo": 9,
        }
        blocks.sort(key=lambda item: (rank.get(item["rel"], 50), item["direction"], item["label_pt"]))
        return blocks

    def _hypernym_path(self, synset_id: str) -> list[dict]:
        path = []
        current = synset_id
        seen = set()
        while current and current not in seen:
            seen.add(current)
            row = self.conn.execute(
                """
                SELECT target_synset FROM relations
                WHERE source_synset=? AND rel='hyponymOf' AND lang='pt'
                LIMIT 1
                """,
                (current,),
            ).fetchone()
            if not row:
                row = self.conn.execute(
                    """
                    SELECT source_synset AS target_synset FROM relations
                    WHERE target_synset=? AND rel='hypernymOf' AND lang='pt'
                    LIMIT 1
                    """,
                    (current,),
                ).fetchone()
            if not row:
                break
            current = row["target_synset"]
            path.append(self._brief_synset(current))
        return path

    def _nomlex_for(self, synset_id: str) -> list[dict]:
        word_ids = [
            row["word_id"]
            for row in self.conn.execute(
                "SELECT DISTINCT word_id FROM senses WHERE synset_id=? AND word_id != ''",
                (synset_id,),
            )
        ]
        if not word_ids:
            lemmas = [
                row["lemma"]
                for row in self.conn.execute(
                    "SELECT DISTINCT lemma FROM senses WHERE synset_id=? AND lemma != ''",
                    (synset_id,),
                )
            ]
            items = []
            for lemma in lemmas:
                rows = self.conn.execute(
                    """
                    SELECT * FROM nomlex
                    WHERE verb_word LIKE ? OR noun_word LIKE ?
                    """,
                    (f"%{lemma}%", f"%{lemma}%"),
                ).fetchall()
                items.extend(rows)
            return [self._nomlex_dict(row) for row in items[:20]]

        placeholders = ",".join("?" * len(word_ids))
        rows = self.conn.execute(
            f"""
            SELECT * FROM nomlex
            WHERE verb_word IN ({placeholders}) OR noun_word IN ({placeholders})
            """,
            word_ids + word_ids,
        ).fetchall()
        return [self._nomlex_dict(row) for row in rows[:30]]

    def _nomlex_dict(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["nomlex_id"],
            "verb": self._word_lemma(row["verb_word"]),
            "noun": self._word_lemma(row["noun_word"]),
            "provenance": row["provenance"],
            "flags": [flag for flag in (row["flags"] or "").split(",") if flag],
        }

    def _word_lemma(self, word_id: str) -> str:
        if not word_id:
            return ""
        row = self.conn.execute(
            "SELECT lemma FROM words WHERE word_id=? AND lang='pt'",
            (word_id,),
        ).fetchone()
        if row:
            return row["lemma"]
        return word_id.replace("word-", "").rsplit("-", 1)[0].replace("_", " ")

    def _brief_synset(self, synset_id: str) -> dict:
        pt_lemmas = [
            row["lemma"]
            for row in self.conn.execute(
                "SELECT lemma FROM senses WHERE synset_id=? AND lang='pt' AND lemma!='' ORDER BY word_number LIMIT 6",
                (synset_id,),
            )
        ]
        en_lemmas = [
            row["lemma"]
            for row in self.conn.execute(
                "SELECT lemma FROM senses WHERE synset_id=? AND lang='en' AND lemma!='' ORDER BY word_number LIMIT 6",
                (synset_id,),
            )
        ]
        gloss_row = self.conn.execute(
            "SELECT gloss, pos FROM synsets WHERE synset_id=? AND lang='pt'",
            (synset_id,),
        ).fetchone()
        if not gloss_row:
            gloss_row = self.conn.execute(
                "SELECT gloss, pos FROM synsets WHERE synset_id=? AND lang='en'",
                (synset_id,),
            ).fetchone()
        gloss = (gloss_row["gloss"] if gloss_row else "") or ""
        pos = (gloss_row["pos"] if gloss_row else synset_id[-1:])
        return {
            "id": synset_id,
            "pos": pos,
            "lemmas_pt": pt_lemmas,
            "lemmas_en": en_lemmas,
            "gloss": gloss.split("\n")[0] if gloss else "",
        }

    def _hit_dict(self, row: sqlite3.Row, query: str) -> dict:
        synset_id = row["synset_id"]
        lang = row["lang"]
        other_lang = "en" if lang == "pt" else "pt"
        other_lemmas = [
            item["lemma"]
            for item in self.conn.execute(
                "SELECT lemma FROM senses WHERE synset_id=? AND lang=? AND lemma!='' ORDER BY word_number LIMIT 6",
                (synset_id, other_lang),
            )
        ]
        same_lemmas = [
            item["lemma"]
            for item in self.conn.execute(
                "SELECT lemma FROM senses WHERE synset_id=? AND lang=? AND lemma!='' ORDER BY word_number LIMIT 8",
                (synset_id, lang),
            )
        ]
        return {
            "id": synset_id,
            "lang": lang,
            "pos": row["pos"],
            "matched_lemma": row["lemma"],
            "word_number": row["word_number"] if "word_number" in row.keys() else 0,
            "has_gloss": bool(row["gloss"]),
            "lemmas": same_lemmas,
            "other_lemmas": other_lemmas,
            "gloss": ((row["gloss"] or "").split("\n")[0] if row["gloss"] else ""),
        }

    def _search_hit_from_synset(self, syn: dict) -> dict:
        return {
            "id": syn["id"],
            "lang": "pt",
            "pos": syn["pos"],
            "matched_lemma": syn["id"],
            "lemmas": syn["pt"]["lemmas"],
            "other_lemmas": syn["en"]["lemmas"],
            "gloss": (syn["pt"]["gloss"] or syn["en"]["gloss"] or [""])[0],
        }


def _looks_like_synset(text: str) -> bool:
    value = text.strip().lower()
    if value.startswith("synset-"):
        value = value[7:]
    if len(value) < 10 or value[-2] != "-":
        return False
    return value[:-2].isdigit() and value[-1] in {"n", "v", "a", "s", "r"}
