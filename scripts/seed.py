import argparse
from pathlib import Path

import numpy as np
import polars as pl

from tabular_manner.engine.application.storage.resource_storage import ResourceStorage
from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import LocalResourceStorageRepository

def _find_repo_root(marker: str = "pyproject.toml") -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / marker).exists():
            return p
    raise FileNotFoundError(marker)

project_root = _find_repo_root()

BYTES_PER_ROW_ESTIMATE = 40  # rough estimate: customer (str) + amount (f64) + quantity (i64)

def generate_dataframe(n_rows: int, null_ratio: float = 0.1, seed: int = 42) -> pl.DataFrame:
    rng = np.random.default_rng(seed)

    customers = [f"customer_{i % 500}" for i in range(n_rows)]
    amounts = rng.normal(loc=100.0, scale=30.0, size=n_rows)
    quantities = rng.integers(1, 50, size=n_rows).astype(float)

    null_mask_amount = rng.random(n_rows) < null_ratio
    null_mask_quantity = rng.random(n_rows) < null_ratio
    amounts[null_mask_amount] = np.nan
    quantities[null_mask_quantity] = np.nan

    return pl.DataFrame({
        "customer": customers,
        "amount": amounts,
        "quantity": quantities,
    }).with_columns([
        pl.when(pl.col("amount").is_nan()).then(None).otherwise(pl.col("amount")).alias("amount"),
        pl.when(pl.col("quantity").is_nan()).then(None).otherwise(pl.col("quantity")).alias("quantity"),
    ])

def rows_for_size_mb(size_mb: float) -> int:
    target_bytes = size_mb * 1024 * 1024
    return max(1, int(target_bytes / BYTES_PER_ROW_ESTIMATE))


def parse_args():
    parser = argparse.ArgumentParser(description="Seed mock data into resource storage.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--n", type=int, help="Number of rows to generate.")
    group.add_argument("--size-mb", type=float, help="Approximate target size in MB.")

    parser.add_argument("--key", type=str, default="raw", help="Resource storage key (default: 'raw').")
    parser.add_argument("--bucket", type=str, default=None, help="Optional bucket name.")
    parser.add_argument("--null-ratio", type=float, default=0.1, help="Fraction of nulls per numeric column (default: 0.1).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    parser.add_argument("--root", type=str, default=str(project_root / ".tm" / "resource_storage"), help="Local resource storage root dir.")

    return parser.parse_args()

def main():
    args = parse_args()

    if args.n is not None:
        n_rows = args.n
    else:
        n_rows = rows_for_size_mb(args.size_mb)

    print(f"Generating {n_rows:,} rows (null_ratio={args.null_ratio}, seed={args.seed})...")
    df = generate_dataframe(n_rows=n_rows, null_ratio=args.null_ratio, seed=args.seed)

    actual_size_mb = df.estimated_size("mb")
    print(f"Generated DataFrame shape={df.shape}, estimated size={actual_size_mb:.2f} MB")

    repository = LocalResourceStorageRepository(root=args.root)
    resource_storage = ResourceStorage(repository=repository)
    resource_storage.save(args.key, df.lazy(), bucket=args.bucket)

    print(f"Saved to resource storage: key='{args.key}', bucket='{args.bucket or 'default'}', root='{args.root}'")


if __name__ == "__main__":
    main()