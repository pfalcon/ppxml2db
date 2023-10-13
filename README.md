# Tools to import/export PortfolioPerformance XML file to/from database

[PortfolioPerformance](https://github.com/portfolio-performance/portfolio)
or "PP" for short, is an OpenSource, advanced, full-featured portfolio/asset
tracker. It can
do a lot of things, but definitely not all that you may want. Given that
it stores data in an XML file, it may seem that it would be easy to access
data in it, e.g. to produce a custom report, or modify, e.g. add new
operations or automatically categorize assets. But turns out, that's not
the case, as the XML format used by PP is nothing but internal serialization
format of 3rd-party library [XStream](https://x-stream.github.io/). This
format never was intended to be human readable, writable, easy to process
by 3rd-party tools, or anything like.

This project tries to ~~solve~~ address this problem, by providing Python
scripts to parse this, effectively proprietary, XML format and storing
data into an SQLite database, and performing reverse operation - exporting
data from such an SQLite database back to the XML format, while achieving
as perfect round-trip as possible (meaning that if you import data and
immediately export, you will get almost no differences comparing to the
original XML file, and if you change something in the database, then in
general, only these changes will be propagated to XML file). Round-tripping
is important, because it will allow you to review the changes made to the
data in the database, and ensure they correspond with your expectations.

While developing 3rd-party tools is the primary usecase behind this project,
it also tries to be a "proof of concept" of the idea of storing
PortfolioPerformance data in the database. To that end, database schema
is intended to match internal PP object schema pretty well. This means
that while writing data manipulation scripts you may need to just
thru some extra hops, but potentially opens a possibility to integrate
database backend directly into PP (by making at least a first step -
providing a realisitic database schema for that).

## What can be done with the resulting database?

Anything you want. Two general directions is read-only access to produce
various stats and reports, and write access to modify data, e.g. to
write a custom statement importer (much easier in your favorite scripting
language than Java, in which PP written), or add custom price feed
handler, or add/update data about your assets, e.g. market capitalization
or next earnings date - possibilities are limitless.

## What's in the repository

* `*.sql` - Database schema, one table per file.
* `ppxml2db.py` - Script to import XML file into a database.
* `db2ppxml.py` - Script to export database to XML file.
* `Makefile` - Makefile to create an empty database.

## Example usage

Not that using `Makefile` requires POSIX-like operating system
(e.g. Linux or Windows Subsystem for Linux) with the `make`
tool. Main scripts are written in (Python3)[https://www.python.org].

1. Start PortfolioPerformance. Make sure you see "Welcome" page.
2. On the "Welcome" page, click "Open the DAX sample file".
3. "dax.xml" will open in a new tab, press Ctrl+S to save it.
   That's the sample file we'll use for import/export.
4. Copy the file to this project's directory for easy access.
5. Create an empty database with all the needed tables:
   `make init DB=dax.db`
6. Import the XML into the database:
   `python3 ppxml2db.py dax.xml dax.db`
7. Export the database to a new XML file:
   `python3 python3 ppxml2db.py >dax.xml.out`
8. Ensure that the new file matches the original character-by-character:
   `diff -u dax.xml dax.xml.out`

Now let's do something pretty simple, yet useful, and already something
which PP itself doesn't do: show how many securities are in this portfolio:

```
echo "SELECT COUNT(*) FROM security;" | sqlite3 dax.db
31
```

## References

* ["anybody interested in PP with a database?"](https://github.com/portfolio-performance/portfolio/issues/2216)
* [Criticism of PP XML format](https://github.com/portfolio-performance/portfolio/issues/3417)
