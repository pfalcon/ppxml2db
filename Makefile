PYTHON = python3
DB = pp.db
TABLES = .account .security .security_attr .security_prop .latest_price .price \
    .watchlist .watchlist_security \
    .xact .xact_unit .xact_cross_entry \
    .taxonomy .taxonomy_category


all:

init: tables

tables: $(TABLES)

reload-data:
	rm -f $(DATA)
	make all

.%: %.sql .create-db
	-echo "DROP TABLE IF EXISTS $(patsubst .%,%,$@);" | sqlite3 $(DB)
	sqlite3 $(DB) < $<
	touch $@

.create-db: 
	-rm $(DB)
	touch $@

clean:
	-rm -f .[a-z]*


# It appears that sqlite3 dump CSV by default with CRLF line endings. Use
# ".separator" directive to override that.
dump:
	for db in `echo ".tables" |  sqlite3 $(DB)`; do \
	    echo -e ".mode csv\n.separator , \\\n\n select * from $$db;" | sqlite3 $(DB) >$$db.csv; \
	done
