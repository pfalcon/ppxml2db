import logging
import sqlite3


LOG_SQL_TO_FILE = 0


log = logging.getLogger(__name__)

db = None

sqllog = None


def init(dbname):
    global db
    db = sqlite3.connect(dbname)
    db.row_factory = sqlite3.Row
    if LOG_SQL_TO_FILE:
        global sqllog
        sqllog = open(dbname + ".sql", "w")


def execute_dml(sql, values = (), returning=None):
    if returning:
        sql += " RETURNING " + returning
    if LOG_SQL_TO_FILE:
        sqllog.write("%s %s\n" % (sql, values))
        return
    cursor = db.cursor()
    log.debug(sql + " " + str(values))
    cursor.execute(sql, values)
    return cursor.lastrowid


def insert(table, fields=None, or_replace=False, returning=None, **kw):
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
    id = execute_dml(sql, field_vals, returning)
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
