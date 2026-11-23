"""Validate OWL/RDF ontology, SQL DDL schema, and Knowledge Triples."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
import pandas as pd
from rdflib import Graph

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ont_dir = ROOT / "03_models" / "ontology_model"
    g = Graph()
    g.parse(str(ont_dir / "petro_pid_ontology.ttl"), format="turtle")
    g.serialize(str(ont_dir / "petro_pid_ontology.owl"), format="xml")
    print(f"[OK] OWL Ontology validated & serialized: {len(g)} triples")

    dm_dir = ROOT / "03_models" / "data_model"
    shutil.copy(dm_dir / "schema.sql", dm_dir / "migrations" / "001_init.sql")
    conn = sqlite3.connect(":memory:")
    conn.executescript((dm_dir / "schema.sql").read_text(encoding="utf-8"))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"[OK] SQL DDL validated: {len(tables)} tables -> {tables}")

    km_dir = ROOT / "03_models" / "knowledge_model"
    triples = json.loads((km_dir / "knowledge_triples.json").read_text(encoding="utf-8"))
    pd.DataFrame(triples).to_csv(km_dir / "knowledge_triples.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] Knowledge Model validated & exported CSV: {len(triples)} triples")


if __name__ == "__main__":
    main()
