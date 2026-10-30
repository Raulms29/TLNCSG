"""
Builds the autoresearch pool from the sources in the config (pool.sources) and splits each source
into train and val. The pool file is written to paths.pool and stays fixed for a run.

Usage: python autoresearch/tools/build_pool.py [--config autoresearch_config.json]
"""

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

sys.path.append(str(Path(__file__).resolve().parents[2]))

from autoresearch.core.constants import PROJECT_ROOT
from autoresearch.core.query import derive_features
from pipeline.datasets import GrailQADataset, Text2CypherDataset
from pipeline.datasets.text2cypher import cypher_features
from pipeline.evaluation.ground_truth import GroundTruthStore

Pool = Dict[str, Dict[str, Any]]


def resolve(path: str) -> Path:
    return (PROJECT_ROOT / path).resolve()


def load_handwritten(cfg: Dict[str, Any], seed: int) -> Pool:
    """Every hand-written query, with its SemGIR solution."""
    data = json.loads(resolve(cfg["path"]).read_text(encoding="utf-8"))
    return {
        qid: {
            "query": entry["query"],
            "solution": entry["solution"],
            "features": derive_features(entry["solution"]),
            "rubric_features": entry.get("rubric_features", []),
        }
        for qid, entry in data.items()
    }


def load_grailqa(cfg: Dict[str, Any], seed: int) -> Pool:
    """A stratified sample, as the pipeline draws it, leaving out the templates of exclude_templates_from."""
    exclude = cfg.get("exclude_templates_from")
    path = resolve(cfg["path"])
    queries = GrailQADataset(path, resolve(exclude) if exclude else None).sample(
        cfg["n"], seed
    )
    raw = {
        str(entry["qid"]): entry
        for entry in json.loads(path.read_text(encoding="utf-8"))
    }
    return {
        q.id: {
            "query": q.text,
            "ground_truth": {
                "dataset": "grailqa",
                "s_expression_friendly": GroundTruthStore.grailqa_ground_truth(
                    raw[q.id]
                ).s_expression_friendly,
            },
            "features": [
                f"function:{q.metadata['function']}",
                f"edges:{q.metadata['num_edge']}",
            ],
        }
        for q in queries
    }


def load_text2cypher(cfg: Dict[str, Any], seed: int) -> Pool:
    """A stratified sample, as the pipeline draws it, leaving out the questions of exclude_questions_from."""
    exclude = cfg.get("exclude_questions_from")
    queries = Text2CypherDataset(
        resolve(cfg["path"]), resolve(exclude) if exclude else None
    ).sample(cfg["n"], seed)
    return {
        q.id: {
            "query": q.text,
            "ground_truth": {"dataset": "text2cypher", "cypher": q.metadata["cypher"]},
            "features": [
                *cypher_features(q.metadata["cypher"]),
                f"data_source:{q.metadata['data_source']}",
            ],
        }
        for q in queries
    }


LOADERS = {
    "handwritten": load_handwritten,
    "grailqa": load_grailqa,
    "text2cypher": load_text2cypher,
}


def pick_val(entries: Pool, fraction: float, seed: int) -> List[str]:
    """
    Picks the val queries of one source, stratified by each query's rarest feature tag
    so that rare features are spread across train and val.
    """
    tag_counts = Counter(tag for entry in entries.values() for tag in entry["features"])
    groups = defaultdict(list)
    for qid, entry in entries.items():
        rarest = min(entry["features"], key=lambda tag: tag_counts[tag])
        groups[rarest].append(qid)

    rng = random.Random(seed)
    val = []
    for tag in sorted(groups):
        ids = sorted(groups[tag])
        rng.shuffle(ids)
        val += ids[: round(len(ids) * fraction)]

    # Groups of one or two queries round to no val query: fill up to the fraction from the rest
    rest = sorted(set(entries) - set(val))
    rng.shuffle(rest)
    return val + rest[: max(0, round(len(entries) * fraction) - len(val))]


def main():
    parser = argparse.ArgumentParser(description="Builds the autoresearch pool file.")
    parser.add_argument(
        "--config", default=str(PROJECT_ROOT / "autoresearch_config.json")
    )
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    pool_cfg = config["pool"]

    pool: Pool = {}
    for source, cfg in pool_cfg["sources"].items():
        if source not in LOADERS:
            sys.exit(f"Unknown source '{source}': expected one of {', '.join(LOADERS)}")
        entries = LOADERS[source](cfg, pool_cfg["seed"])
        val = set(pick_val(entries, pool_cfg["val_fraction"], pool_cfg["seed"]))
        for qid, entry in entries.items():
            pool[qid] = {
                "source": source,
                "split": "val" if qid in val else "train",
                **entry,
            }
        print(
            f"{source}: {len(entries)} queries, {len(entries) - len(val)} train / {len(val)} val"
        )

    out_path = resolve(config["paths"]["pool"])
    out_path.write_text(
        json.dumps(pool, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(pool)} queries to {out_path}")


if __name__ == "__main__":
    main()
