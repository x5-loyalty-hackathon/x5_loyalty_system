"""Build a Russia-filtered product catalog from the Open Food Facts bulk export.

Not on any runtime/test import path — same status as the other calibration
scripts. Needs `pip install -e '.[ml]'` (pandas).

Why this exists: our biggest confirmed data gap
(docs/research/recsys/x5-retail-hero-data-audit.md §4.1) is that X5 Retail
Hero's `product_id` is anonymized with no name and no barcode, so a recipe
ingredient like "томаты" cannot be resolved to a real sellable product from
X5 data alone. Open Food Facts is the open (ODbL) catalog layer that *does*
have barcode + name + brand + category + quantity + ingredients, so it can
serve as the `ingredient -> named product/GTIN` side of the bridge.

Important: this does NOT let us recover what a historical X5 `product_id`
was. OFF and X5 share no join key. This builds the catalog side only; the
two layers stay deliberately separate (X5 = who/when, OFF = what).

Memory/disk design: the OFF CSV export is ~1.2 GB gzipped and well over 10 GB
uncompressed with 211 columns. This script never decompresses it to disk and
never loads it whole — it streams the gzip, reads only the ~11 columns we
need, filters to Russian products chunk by chunk, and writes just the
filtered subset.

Run: ``python -m recsys.calibration.build_off_russian_catalog``
Input:  data/external/open_food_facts/raw/products.csv.gz
Output: data/external/open_food_facts/ru_products.csv (+ audit JSON)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# OFF's CSV export is tab-separated despite the .csv name.
SEP = "\t"
CHUNK_SIZE = 200_000

USECOLS = [
    "code",
    "product_name",
    "quantity",
    "brands",
    "categories",
    "categories_tags",
    "categories_en",
    "countries",
    "countries_tags",
    "countries_en",
    "ingredients_text",
]

# OFF tags countries as e.g. "en:russia"; the human-readable columns vary by
# contributor language, so match on several spellings.
RU_TAG_MARKERS = ("en:russia", "ru:россия", "en:russian-federation")
RU_TEXT_MARKERS = ("russia", "россия", "russian federation")


def _require_pandas():
    try:
        import pandas as pd  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised manually
        raise SystemExit("pandas is required: install with `pip install -e '.[ml]'`.") from exc


def _is_russian(chunk):
    import pandas as pd

    mask = pd.Series(False, index=chunk.index)
    for col, markers in (
        ("countries_tags", RU_TAG_MARKERS),
        ("countries_en", RU_TEXT_MARKERS),
        ("countries", RU_TEXT_MARKERS),
    ):
        if col not in chunk.columns:
            continue
        series = chunk[col].fillna("").str.lower()
        for marker in markers:
            mask |= series.str.contains(marker, regex=False, na=False)
    return mask


def build(raw_path: Path, out_path: Path, *, max_chunks: int | None = None) -> dict:
    import pandas as pd

    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    ru_rows = 0
    chunks_done = 0
    first_write = True
    ru_frames_written = 0

    reader = pd.read_csv(
        raw_path,
        sep=SEP,
        usecols=lambda c: c in USECOLS,
        chunksize=CHUNK_SIZE,
        dtype=str,
        on_bad_lines="skip",
        compression="gzip",
        encoding="utf-8",
        encoding_errors="replace",
    )

    for chunk in reader:
        total_rows += len(chunk)
        ru = chunk[_is_russian(chunk)]
        if len(ru):
            ru.to_csv(
                out_path,
                mode="w" if first_write else "a",
                header=first_write,
                index=False,
                encoding="utf-8",
            )
            first_write = False
            ru_rows += len(ru)
            ru_frames_written += 1
        chunks_done += 1
        if chunks_done % 10 == 0:
            print(f"  ...{total_rows:,} rows scanned, {ru_rows:,} Russian products kept", file=sys.stderr)
        if max_chunks is not None and chunks_done >= max_chunks:
            print(f"  [stopping early after {max_chunks} chunks — test mode]", file=sys.stderr)
            break

    return {
        "total_rows_scanned": total_rows,
        "russian_rows_kept": ru_rows,
        "chunks_processed": chunks_done,
        "output": str(out_path),
    }


def audit_russian_catalog(out_path: Path) -> dict:
    """Quality report on the filtered subset — the checks the research report
    asked for: coverage, missingness, duplicate GTINs."""
    import pandas as pd

    if not out_path.exists():
        return {"error": "no output file produced"}

    df = pd.read_csv(out_path, dtype=str)
    n = len(df)
    if n == 0:
        return {"n_rows": 0}

    def missing_rate(col: str) -> float | None:
        if col not in df.columns:
            return None
        return round(float(df[col].isna().mean()), 4)

    report = {
        "n_rows": n,
        "n_unique_barcodes": int(df["code"].nunique()) if "code" in df.columns else None,
        "duplicate_barcodes": int(n - df["code"].nunique()) if "code" in df.columns else None,
        "missing_rate": {
            col: missing_rate(col)
            for col in ("product_name", "brands", "categories", "quantity", "ingredients_text")
        },
        "usable_for_matching": None,
    }

    if {"product_name", "categories"}.issubset(df.columns):
        usable = df["product_name"].notna() & df["categories"].notna()
        report["usable_for_matching"] = {
            "n": int(usable.sum()),
            "share": round(float(usable.mean()), 4),
            "definition": "has both product_name and categories (minimum for lexical+category retrieval)",
        }

    if "product_name" in df.columns:
        names = df["product_name"].dropna()
        cyrillic = names.str.contains(r"[а-яА-Я]", regex=True, na=False)
        report["product_name_language"] = {
            "n_with_cyrillic": int(cyrillic.sum()),
            "share_cyrillic": round(float(cyrillic.mean()), 4) if len(names) else None,
            "note": "low Cyrillic share means most names are latin-script and need translation/normalization",
        }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw", type=Path,
        default=Path("data/external/open_food_facts/raw/products.csv.gz"),
    )
    parser.add_argument(
        "--out", type=Path,
        default=Path("data/external/open_food_facts/ru_products.csv"),
    )
    parser.add_argument(
        "--max-chunks", type=int, default=None,
        help="Stop after N chunks (smoke test without a full pass)",
    )
    args = parser.parse_args()

    _require_pandas()
    if not args.raw.exists():
        raise SystemExit(
            f"Missing {args.raw}. Download it first:\n"
            "  curl -L https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz "
            f"-o {args.raw}"
        )

    print(f"Streaming {args.raw} (gzip, tab-separated, filtering to Russian products)...", file=sys.stderr)
    build_stats = build(args.raw, args.out, max_chunks=args.max_chunks)
    print("\n=== extraction ===")
    print(json.dumps(build_stats, indent=2, ensure_ascii=False))

    quality = audit_russian_catalog(args.out)
    print("\n=== quality of the Russian subset ===")
    print(json.dumps(quality, indent=2, ensure_ascii=False))

    report_path = args.out.parent / "ru_catalog_audit.json"
    report_path.write_text(
        json.dumps({"extraction": build_stats, "quality": quality}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote {report_path}")


if __name__ == "__main__":
    sys.exit(main() or 0)
