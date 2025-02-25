import logging
import os
import sqlite3
from pathlib import Path


LOG_SQL_TO_FILE = 0


log = logging.getLogger(__name__)

db = None

sqllog = None


def init(dbname, new_db = False):
    global db
    if new_db:
        sql_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                "setup_scripts")
        sql_files = read_sql_files(sql_path)
        if os.path.exists(dbname):
            os.remove(dbname)
        db = sqlite3.connect(dbname)
        execute_sql_files(db, sql_files)
    else:
        db = sqlite3.connect(dbname)
    db.row_factory = sqlite3.Row
    if LOG_SQL_TO_FILE:
        global sqllog
        sqllog = open(dbname + ".sql", "w")


def read_sql_files(sql_path):
    sql_files = {}
    for filename in os.listdir(sql_path):
        if filename.endswith(".sql"):
            with open(os.path.join(sql_path, filename), "r") as file:
                sql_files[filename] = file.read()
    # [print(f"{key}: {value}") for key, value in sql_files.items()]
    return sql_files


def execute_sql_files(db, sql_files):
    # cursor = db.cursor()
    for filename, sql_content in sql_files.items():
        try:
            # cursor.executescript(sql_content)
            db.executescript(sql_content)
            # print(f"Executed {filename} successfully")
        except sqlite3.Error as e:
            print(f"Error executing {filename}: {e}")
    db.commit()
    # db.close()


def execute_insert(sql, values = ()):
    if LOG_SQL_TO_FILE:
        sqllog.write("%s %s\n" % (sql, values))
        return
    cursor = db.cursor()
    log.debug(sql + " " + str(values))
    cursor.execute(sql, values)
    return cursor.lastrowid


def insert(table, fields=None, or_replace=False, **kw):
    repl_clause = ""
    if or_replace:
        repl_clause = " OR REPLACE"
    if fields is None:
        fields = kw
    field_names = []
    field_vals = []
    qmarks = []
    for k, v in fields.items():
        field_names.append(k)
        field_vals.append(v)
        qmarks.append("?")
    sql = "INSERT%s INTO %s(%s) VALUES (%s)" % (repl_clause, table, ", ".join(field_names), ", ".join(qmarks))
    id = execute_insert(sql, field_vals)
    return id


def select(table, where=None, order=None):
    cursor = db.cursor()
    if where is None:
        where = ""
    else:
        where = " WHERE " + where
    if order is None:
        order = ""
    else:
        order = " ORDER BY " + order
    sql = "SELECT * FROM %s%s%s" % (table, where, order)
    if LOG_SQL_TO_FILE:
        sqllog.write("%s\n" % sql)
    cursor.execute(sql)
    log.debug(sql)
    return cursor.fetchall()


def commit():
    log.debug("COMMIT")
    db.commit()
