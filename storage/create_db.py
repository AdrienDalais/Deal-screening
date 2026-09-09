"""Build the database from the models, then show what was built.

    python -m storage.create_db          # create if absent
    python -m storage.create_db --drop   # start again from empty

Deliberately prints the real schema read back out of SQLite rather than
echoing the Python. The point is to see what the database actually holds,
not what we intended it to hold.
"""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from storage.db import get_engine
from storage.models import Base


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drop", action="store_true",
        help="drop every table first. Destroys all data.",
    )
    args = parser.parse_args()

    engine = get_engine()
    print(f"Database: {engine.url}\n")

    if args.drop:
        Base.metadata.drop_all(engine)
        print("Dropped all tables.\n")

    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    print(f"{len(tables)} tables:\n")

    for table in tables:
        columns = inspector.get_columns(table)
        indexes = inspector.get_indexes(table)
        print(f"  {table}  ({len(columns)} columns)")
        for column in columns:
            null = "" if column["nullable"] else "  NOT NULL"
            print(f"      {column['name']:<28} {str(column['type']):<28}{null}")
        for index in indexes:
            unique = " UNIQUE" if index["unique"] else ""
            cols = ", ".join(index["column_names"])
            print(f"      index{unique}: {index['name']} ({cols})")
        print()

    with engine.connect() as connection:
        checks = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND sql LIKE '%CHECK%' ORDER BY name"
        )).scalars().all()
    print(f"Tables carrying CHECK constraints: {len(checks)}")
    for name in checks:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
