import logging
import sqlite3


log = logging.getLogger(__name__)

db = None


def init(dbname):
    global db
    db = sqlite3.connect(dbname)
    db.row_factory = sqlite3.Row


def execute_insert(sql, values = ()):
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
    cursor.execute("SELECT * FROM %s%s%s" % (table, where, order))
    return cursor.fetchall()


def commit():
    log.debug("COMMIT")
    db.commit()
