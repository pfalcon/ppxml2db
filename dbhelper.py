import logging
import sqlite3


LOG_SQL_TO_FILE = 0


log = logging.getLogger(__name__)

dbtype = None
db = None
param_mark = None

sqllog = None


def init(_dbtype, dbname):
    global dbtype, param_mark
    dbtype = _dbtype

    if dbtype == "pgsql":
        param_mark = "%s"
        init_pgsql(dbname)
    else:
        param_mark = "?"
        init_sqlite(dbname)


def init_sqlite(dbname):
    global db
    db = sqlite3.connect(dbname)
    db.row_factory = sqlite3.Row
    if LOG_SQL_TO_FILE:
        global sqllog
        sqllog = open(dbname + ".sql", "w")


def init_pgsql(dbname):
    import psycopg
    global db
    db = psycopg.connect(dbname, row_factory=psycopg.rows.namedtuple_row)
    execute_dml("SET session_replication_role = 'replica'")
    execute_dml("BEGIN")


def execute_dml(sql, values = (), returning=None):
    if returning:
        sql += " RETURNING " + returning
    if dbtype == "pgsql":
        sql = sql.replace("?", "%s")
    if LOG_SQL_TO_FILE:
        sqllog.write("%s %s\n" % (sql, values))
        return
    cursor = db.cursor()
    log.debug(sql + " " + str(values))
    cursor.execute(sql, values)
    if dbtype == "pgsql":
        if returning:
            return cursor.fetchone()[0]
    else:
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
        qmarks.append(param_mark)
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
