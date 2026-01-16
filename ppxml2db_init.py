import sys
import argparse
import logging

from version import __version__
import dbhelper


SCHEMA = [
    "account",
    "account_attr",
    "security",
    "security_attr",
    "security_event",
    "security_prop",
    "latest_price",
    "price",
    "watchlist",
    "watchlist_security",
    "xact",
    "xact_unit",
    "xact_cross_entry",
    "taxonomy",
    "taxonomy_category",
    "taxonomy_data",
    "taxonomy_assignment",
    "taxonomy_assignment_data",
    "dashboard",
    "property",
    "bookmark",
    "attribute_type",
    "config_set",
    "config_entry",
]


_log = logging.getLogger(__name__)


def drop_table(table):
    sql = "DROP TABLE IF EXISTS %s" % table
    if args.dbtype == "pgsql":
        sql += " CASCADE"
    dbhelper.execute_dml(sql)


def main(args):
    for table in SCHEMA:
        with open(table + ".sql") as f:
            sql = f.read()
        if args.recreate:
            drop_table(table)

        if args.dbtype == "pgsql":
            sql = sql.replace(
                "INTEGER NOT NULL PRIMARY KEY",
                "SERIAL NOT NULL PRIMARY KEY"
            )

        dbhelper.executescript(sql)


if __name__ == "__main__":
    argp = argparse.ArgumentParser(description="Initialize database for ppxml2db")
    argp.add_argument("db", help="output DB (filename/connect string)")
    argp.add_argument("--dbtype", choices=("sqlite", "pgsql"), default="sqlite", help="select database type")
    argp.add_argument("--recreate", action="store_true", help="delete existing tables")
    argp.add_argument("--debug", action="store_true", help="enable debug logging")
    argp.add_argument("--dry-run", action="store_true", help="don't commit changes to DB")
    argp.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = argp.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    dbhelper.init(args.dbtype, args.db)

    main(args)

    if not args.dry_run:
        dbhelper.commit()
