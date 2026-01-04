import sys
import argparse
import logging
import os.path
import json

from version import __version__
import dbhelper


# uuid to #
sec_map = {}

# uuid to element
output_els = {}

# (portfolio_xact, account_xact) to element
cross_els = {}

xml_id = 0
uuid2xmlid = {}

out = None


class ET_SubElement:

    def __init__(self, parent, tag):
        if parent is None:
            self._indent = 0
        else:
            self._indent = parent._indent + 1
            if not parent.start_written:
                parent.wr_start()
        self.tag = tag
        self.attrib = {}
        self.start_written = False

    def get(self, attr):
        return self.attrib[attr]

    def set(self, attr, val):
        self.attrib[attr] = val

    def indent(self):
        global out
        if self._indent:
            out.write("\n" + "  " * self._indent)

    def _wr_start(self, end):
        global out
        self.indent()
        out.write("<%s" % self.tag)
        for k, v in self.attrib.items():
            out.write(' %s="%s"' % (k, v))
        out.write(end)
        self.start_written = True

    def wr_start(self):
        self._wr_start(">")

    def wr_nb(self):
        self._wr_start("/>")

    def wr_end(self, indent=True):
        global out
        if not self.start_written:
            self.wr_nb()
            return

        if indent:
            self.indent()
            # Still need to indent top closing tag
            if self._indent == 0:
                out.write("\n")
        out.write("</%s>" % self.tag)

    @property
    def text(self):
        raise NotImplementedError

    @text.setter
    def text(self, txt):
        global out
        if txt is None:
            self.wr_nb()
        else:
            self.wr_start()
            out.write(quote_text(txt))
            self.wr_end(False)


def ET_Element(tag):
    return ET_SubElement(None, tag)


# Initial version of this script used lxml.etree (ET) and built a DOM tree
# in memory. But that had poor scalability to large files, so it was rewritten
# using adhoc object mimicking ET API, but writing out most of object content
# to stream eagerly and not keeping unneeded objects in memory.
class ET:
    Element = ET_Element
    SubElement = ET_SubElement


def add_xmlid(el, uuid=None):
    global xml_id

    xml_id += 1
    el.attrib["id"] = str(xml_id)
    if uuid is not None:
        uuid2xmlid[uuid] = str(xml_id)


def ET_SubElementWId(parent, tag, uuid=None):
    el = ET.SubElement(parent, tag)
    add_xmlid(el, uuid)
    return el


def as_bool(v):
    return ["false", "true"][v]


def make_prop(pel, row, prop, row_prop=None, conv=str):
    if row[row_prop or prop] is not None:
        el = ET.SubElement(pel, prop)
        el.text = conv(row[row_prop or prop])


def make_map(pel, rows):
    mapel = ET.SubElement(pel, "map")
    for r in rows:
        enel = ET.SubElement(mapel, "entry")
        ET.SubElement(enel, "string").text = r["attr_uuid"]
        if r["type"] == "limitPrice":
            el = ET.SubElement(enel, r["type"])
            op, val = r["value"].split(" ", 1)
            ET.SubElement(el, "operator").text = op
            ET.SubElement(el, "value").text = val
            el.wr_end()
        elif r["type"] == "bookmark":
            el = ET.SubElement(enel, r["type"])
            if r["value"] is not None:
                subels = json.loads(r["value"])
                for k, v in subels.items():
                    ET.SubElement(el, k).text = v
            el.wr_end()
        else:
            ET.SubElement(enel, r["type"]).text = r["value"]
        enel.wr_end()
    mapel.wr_end()


def make_attributes(pel, rows):
    attributes = ET.SubElement(pel, "attributes")
    make_map(attributes, rows)
    attributes.wr_end()


def make_entry(pel, k, v, type="string"):
    e = ET.SubElement(pel, "entry")
    ET.SubElement(e, "string").text = k
    ET.SubElement(e, type).text = v
    e.wr_end()


def make_configuration(pel, conf):
    conf_el = ET.SubElement(pel, "configuration")
    for k, v in conf.items():
        make_entry(conf_el, k, v)
    conf_el.wr_end()


def make_data_entries(pel, data_rows):
    if data_rows:
        data = ET.SubElement(pel, "data")
        for d_r in data_rows:
            make_entry(data, d_r["name"], d_r["value"], d_r["type"])
        data.wr_end()


def security_ref(uuid, levels=4):
    return uuid2xmlid[uuid]


def make_ref(etree, el, to_el):
    el.set("reference", to_el.get("id"))


def try_ref(etree, el, uuid):
    if uuid in uuid2xmlid:
        el.set("reference", uuid2xmlid[uuid])
        el.wr_nb()
        return True
    return False


def make_xact(etree, pel, tag, xact_r):
            xact = ET.SubElement(pel, tag)
            if try_ref(etree, xact, xact_r["uuid"]):
                return

            add_xmlid(xact, xact_r["uuid"])
            output_els[xact_r["uuid"]] = xact
            make_prop(xact, xact_r, "uuid")
            make_prop(xact, xact_r, "date")
            make_prop(xact, xact_r, "currencyCode", "currency")
            make_prop(xact, xact_r, "amount")
            if xact_r["security"] is not None:
                s = ET.SubElement(xact, "security")
                #s.set("reference", security_ref(xact_r["security"], 5))
                assert try_ref(etree, s, xact_r["security"])

            # 0 or 1
            crit = "from_xact='%s' OR to_xact='%s'" % (xact_r["uuid"], xact_r["uuid"])
            for x_r in dbhelper.select("xact_cross_entry", where=crit):
                #print(dict(x_r))
                x = ET.SubElement(xact, "crossEntry")
                x.set("class", x_r["type"])
                cross_key = (x_r["type"], x_r["from_xact"], x_r["to_xact"])
                existing_x = cross_els.get(cross_key)
                if existing_x is not None:
                    make_ref(etree, x, existing_x)
                    x.wr_nb()
                    continue
                add_xmlid(x)
                cross_els[cross_key] = x
                if x_r["type"] == "account-transfer":
                    accfrom_r = dbhelper.select("account", where="uuid='%s'" % x_r["from_acc"])[0]
                    make_account(etree, x, accfrom_r, el_name="accountFrom")
                    acc_xact_r = dbhelper.select("xact", where="uuid='%s'" % x_r["from_xact"])[0]
                    make_xact(etree, x, "transactionFrom", acc_xact_r)
                    accto_r = dbhelper.select("account", where="uuid='%s'" % x_r["to_acc"])[0]
                    make_account(etree, x, accto_r, el_name="accountTo")
                    acc_xact_r = dbhelper.select("xact", where="uuid='%s'" % x_r["to_xact"])[0]
                    make_xact(etree, x, "transactionTo", acc_xact_r)
                elif x_r["type"] == "portfolio-transfer":
                    accfrom_r = dbhelper.select("account", where="uuid='%s'" % x_r["from_acc"])[0]
                    make_portfolio(etree, x, accfrom_r["uuid"], el_name="portfolioFrom")
                    acc_xact_r = dbhelper.select("xact", where="uuid='%s'" % x_r["from_xact"])[0]
                    make_xact(etree, x, "transactionFrom", acc_xact_r)
                    accto_r = dbhelper.select("account", where="uuid='%s'" % x_r["to_acc"])[0]
                    make_portfolio(etree, x, accto_r["uuid"], el_name="portfolioTo")
                    acc_xact_r = dbhelper.select("xact", where="uuid='%s'" % x_r["to_xact"])[0]
                    make_xact(etree, x, "transactionTo", acc_xact_r)
                else:
                    make_portfolio(etree, x, x_r["from_acc"])
                    port_xact_r = dbhelper.select("xact", where="uuid='%s'" % x_r["from_xact"])[0]
                    make_xact(etree, x, "portfolioTransaction", port_xact_r)

                    acc_r = dbhelper.select("account", where="uuid='%s'" % x_r["to_acc"])[0]
                    make_account(etree, x, acc_r)
                    acc_xact_r = dbhelper.select("xact", where="uuid='%s'" % x_r["to_xact"])[0]
                    make_xact(etree, x, "accountTransaction", acc_xact_r)
                x.wr_end()

            make_prop(xact, xact_r, "shares")
            make_prop(xact, xact_r, "note")
            make_prop(xact, xact_r, "source")

            unit_rows = dbhelper.select("xact_unit", where="xact='%s'" % xact_r["uuid"])
            if unit_rows:
                units = ET.SubElement(xact, "units")
                for unit_r in unit_rows:
                    u = ET.SubElement(units, "unit")
                    u.set("type", unit_r["type"])
                    a = ET.SubElement(u, "amount")
                    a.set("currency", unit_r["currency"])
                    a.set("amount", str(unit_r["amount"]))
                    a.wr_nb()
                    if unit_r["forex_amount"] is not None or unit_r["forex_currency"] is not None:
                        forex = ET.SubElement(u, "forex")
                        forex.set("currency", unit_r["forex_currency"])
                        forex.set("amount", str(unit_r["forex_amount"]))
                        forex.wr_nb()
                        forex = ET.SubElement(u, "exchangeRate")
                        forex.text = str(unit_r["exchangeRate"])
                    u.wr_end()
                units.wr_end()

            make_prop(xact, xact_r, "updatedAt")
            make_prop(xact, xact_r, "type")

            xact.wr_end()


def make_xacts(etree, pel, acc_uuid):
        for xact_r in dbhelper.select("xact", where="account='%s'" % acc_uuid, order="_order"):
            tag = {"account": "account-transaction", "portfolio": "portfolio-transaction"}[xact_r["acctype"]]
            make_xact(etree, pel, tag, xact_r)


def make_portfolio(etree, pel, uuid, el_name="portfolio"):
        el = ET.SubElement(pel, el_name)
        if try_ref(etree, el, uuid):
            return
        add_xmlid(el, uuid)
        output_els[uuid] = el
        port_r = dbhelper.select("account", where="uuid='%s'" % uuid)[0]
        make_prop(el, port_r, "uuid")
        make_prop(el, port_r, "name")
        make_prop(el, port_r, "isRetired", conv=as_bool)
        refacc_r = dbhelper.select("account", where="uuid='%s'" % port_r["referenceAccount"])[0]
        make_account(etree, el, refacc_r, el_name="referenceAccount")

        xacts = ET.SubElement(el, "transactions")
        make_xacts(etree, xacts, port_r["uuid"])
        xacts.wr_end()

        attr_rows = dbhelper.select("account_attr", where="account='%s'" % port_r["uuid"], order="seq")
        make_attributes(el, attr_rows)

        make_prop(el, port_r, "updatedAt")
        el.wr_end()


def make_account(etree, pel, acc_r, el_name="account"):
        acc = ET.SubElement(pel, el_name)
        if try_ref(etree, acc, acc_r["uuid"]):
            return
        add_xmlid(acc, acc_r["uuid"])
        output_els[acc_r["uuid"]] = acc
        make_prop(acc, acc_r, "uuid")
        make_prop(acc, acc_r, "name")
        make_prop(acc, acc_r, "currencyCode", "currency")
        make_prop(acc, acc_r, "note")
        make_prop(acc, acc_r, "isRetired", conv=as_bool)

        xacts = ET.SubElement(acc, "transactions")
        make_xacts(etree, xacts, acc_r["uuid"])
        xacts.wr_end()

        attr_rows = dbhelper.select("account_attr", where="account='%s'" % acc_r["uuid"], order="seq")
        make_attributes(acc, attr_rows)

        make_prop(acc, acc_r, "updatedAt")
        acc.wr_end()


def quote_text(s):
    pats = (
        ("&", "&amp;"),
        ("<", "&lt;"),
        (">", "&gt;"),
        ('"', "&quot;"),
        ("'", "&apos;"),
    )
    for p, r in pats:
        s = s.replace(p, r)
    return s


def make_taxonomy_level(etree, pel, level_r):
        tag = "root" if level_r["parent"] is None else "classification"
        level = ET_SubElementWId(pel, tag, level_r["uuid"])
        output_els[level_r["uuid"]] = level
        make_prop(level, level_r, "id", "uuid")
        make_prop(level, level_r, "name")
        make_prop(level, level_r, "color")

        if level_r["parent"]:
            p = ET.SubElement(level, "parent")
            assert try_ref(etree, p, level_r["parent"])

        chds = ET.SubElement(level, "children")
        for e_r in dbhelper.select("taxonomy_category", where="parent='%s'" % level_r["uuid"]):
            make_taxonomy_level(etree, chds, e_r)
        chds.wr_end()

        assgn = ET.SubElement(level, "assignments")
        for a_r in dbhelper.select("taxonomy_assignment", where="category='%s'" % level_r["uuid"]):
            a = ET.SubElement(assgn, "assignment")
            iv = ET.SubElement(a, "investmentVehicle")
            iv.set("class", a_r["item_type"])
            assert try_ref(etree, iv, a_r["item"])
            make_prop(a, a_r, "weight")
            make_prop(a, a_r, "rank")

            data_rows =  dbhelper.select("taxonomy_assignment_data", where="assignment=%d" % a_r["_id"])
            make_data_entries(a, data_rows)
            a.wr_end()
        assgn.wr_end()

        make_prop(level, level_r, "weight")
        make_prop(level, level_r, "rank")

        data_rows = dbhelper.select("taxonomy_data", where="category='%s'" % level_r["uuid"])
        make_data_entries(level, data_rows)
        level.wr_end()


def main():
    global out
    out = sys.stdout
    if args.xml_file:
        out = open(args.xml_file, "w", encoding="utf-8", newline="\n")

    root = ET.Element("client")
    add_xmlid(root)
    etree = None
    for n in ["version", "baseCurrency"]:
        row = dbhelper.select("property", where="name='%s'" % n)[0]
        ET.SubElement(root, n).text = row["value"]

    securities = ET.SubElement(root, "securities")

    for i, sec_r in enumerate(dbhelper.select("security")):
    #    print(dict(sec_r))
        sec_map[sec_r["uuid"]] = i
        sec = ET_SubElementWId(securities, "security", sec_r["uuid"])
        output_els[sec_r["uuid"]] = sec
        make_prop(sec, sec_r, "uuid")
        make_prop(sec, sec_r, "onlineId")
        make_prop(sec, sec_r, "name")
        make_prop(sec, sec_r, "currencyCode", "currency")
        make_prop(sec, sec_r, "targetCurrencyCode", "targetCurrency")
        make_prop(sec, sec_r, "note")
        make_prop(sec, sec_r, "isin")
        make_prop(sec, sec_r, "tickerSymbol")
        make_prop(sec, sec_r, "calendar")
        make_prop(sec, sec_r, "wkn")
        make_prop(sec, sec_r, "feedTickerSymbol")
        make_prop(sec, sec_r, "feed")
        make_prop(sec, sec_r, "feedURL")

        prices = ET.SubElement(sec, "prices")
        for price_r in dbhelper.select("price", where="security='%s'" % sec_r["uuid"]):
            p = ET.SubElement(prices, "price")
            p.set("t", price_r["tstamp"])
            p.set("v", str(price_r["value"]))
            p.wr_nb()
        prices.wr_end()

        make_prop(sec, sec_r, "latestFeed")
        make_prop(sec, sec_r, "latestFeedURL")

        # Can be 0 or 1
        for latest_r in dbhelper.select("latest_price", where="security='%s'" % sec_r["uuid"]):
            latest = ET.SubElement(sec, "latest")
            latest.set("t", latest_r["tstamp"])
            latest.set("v", str(latest_r["value"]))
            make_prop(latest, latest_r, "high")
            make_prop(latest, latest_r, "low")
            make_prop(latest, latest_r, "volume")
            latest.wr_end()

        attr_rows = dbhelper.select("security_attr", where="security='%s'" % sec_r["uuid"], order="seq")
        make_attributes(sec, attr_rows)

        events = ET.SubElement(sec, "events")
        order_args = {}
        if args.sort_events:
            order_args = {"order": "date, details"}
        for event_r in dbhelper.select("security_event", where="security='%s'" % sec_r["uuid"], **order_args):
            event = ET.SubElement(events, "event")
            make_prop(event, event_r, "date")
            make_prop(event, event_r, "type")
            make_prop(event, event_r, "details")
            event.wr_end()
        events.wr_end()

        for prop_r in dbhelper.select("security_prop", where="security='%s'" % sec_r["uuid"], order="seq"):
            p = ET.SubElement(sec, "property")
            p.set("type", prop_r["type"])
            p.set("name", prop_r["name"])
            p.text = prop_r["value"]

        make_prop(sec, sec_r, "isRetired", conv=as_bool)
        make_prop(sec, sec_r, "updatedAt")
        sec.wr_end()
    securities.wr_end()

    watchlists = ET.SubElement(root, "watchlists")
    for wlist_r in dbhelper.select("watchlist"):
        wlist = ET_SubElementWId(watchlists, "watchlist")
        make_prop(wlist, wlist_r, "name")
        secs = ET.SubElement(wlist, "securities")
        for wlist_sec_r in dbhelper.select("watchlist_security", where="list=%d" % wlist_r["_id"]):
            s = ET.SubElement(secs, "security")
            s.set("reference", security_ref(wlist_sec_r["security"]))
            s.wr_nb()
        secs.wr_end()
        wlist.wr_end()
    watchlists.wr_end()

    accounts = ET.SubElement(root, "accounts")
    for acc_r in dbhelper.select("account", where="type='account'", order="_order"):
        make_account(etree, accounts, acc_r)
    accounts.wr_end()

    portfolios = ET.SubElement(root, "portfolios")
    for acc_r in dbhelper.select("account", where="type='portfolio'", order="_order"):
        make_portfolio(etree, portfolios, acc_r["uuid"])
    portfolios.wr_end()

    plans = ET.SubElement(root, "plans")
    plans.wr_end()

    taxonomies = ET.SubElement(root, "taxonomies")
    for taxon_r in dbhelper.select("taxonomy"):
        taxon = ET.SubElement(taxonomies, "taxonomy")
        make_prop(taxon, taxon_r, "id", "uuid")
        make_prop(taxon, taxon_r, "name")
        taxon_dim_rows =  dbhelper.select("taxonomy_data", where="taxonomy='%s' AND category IS NULL AND name='dimension'" % taxon_r["uuid"])
        if taxon_dim_rows:
            el = ET.SubElement(taxon, "dimensions")
            for taxon_dim_r in taxon_dim_rows:
                ET.SubElement(el, "string").text = taxon_dim_r["value"]
            el.wr_end()
        e_r = dbhelper.select("taxonomy_category", where="uuid='%s'" % taxon_r["root"])[0]
        make_taxonomy_level(etree, taxon, e_r)
        taxon.wr_end()
    taxonomies.wr_end()


    dashboards = ET.SubElement(root, "dashboards")
    for dashb_r in dbhelper.select("dashboard"):
        dashb = ET.SubElement(dashboards, "dashboard")
        dashb.set("name", dashb_r["name"])
        make_prop(dashb, dashb_r, "id")
        make_configuration(dashb, json.loads(dashb_r["config_json"]))
        columns = ET.SubElement(dashb, "columns")
        for col_j in json.loads(dashb_r["columns_json"]):
            col = ET.SubElement(columns, "column")
            make_prop(col, col_j, "weight")
            widgets = ET.SubElement(col, "widgets")
            for wid_j in col_j["widgets"]:
                wid = ET.SubElement(widgets, "widget")
                wid.set("type", wid_j["type"])
                make_prop(wid, wid_j, "label")
                if "config" in wid_j:
                    make_configuration(wid, wid_j["config"])
                wid.wr_end()
            widgets.wr_end()
            col.wr_end()
        columns.wr_end()
        dashb.wr_end()
    dashboards.wr_end()


    properties = ET.SubElement(root, "properties")
    for prop_r in dbhelper.select("property", where="special=0"):
        make_entry(properties, prop_r["name"], prop_r["value"])
    properties.wr_end()

    settings = ET.SubElement(root, "settings")

    bookmarks = ET.SubElement(settings, "bookmarks")
    for bmark_r in dbhelper.select("bookmark"):
        bmark = ET.SubElement(bookmarks, "bookmark")
        make_prop(bmark, bmark_r, "label")
        make_prop(bmark, bmark_r, "pattern")
        bmark.wr_end()
    bookmarks.wr_end()

    attrtypes = ET.SubElement(settings, "attributeTypes")
    for attr_type_r in dbhelper.select("attribute_type"):
        attr_type = ET.SubElement(attrtypes, "attribute-type")
        make_prop(attr_type, attr_type_r, "id")
        make_prop(attr_type, attr_type_r, "name")
        make_prop(attr_type, attr_type_r, "columnLabel")
        make_prop(attr_type, attr_type_r, "source")
        make_prop(attr_type, attr_type_r, "target")
        make_prop(attr_type, attr_type_r, "type")
        make_prop(attr_type, attr_type_r, "converterClass")
        prop_list = json.loads(attr_type_r["props_json"])
        if prop_list:
            props = ET.SubElement(attr_type, "properties")
            for p in prop_list:
                make_entry(props, p["name"], p["value"], type=p["type"])
            props.wr_end()
        elif attr_type_r["type"].rsplit(".", 1)[1] in ("LimitPrice",):
            props = ET.SubElement(attr_type, "properties")
            props.wr_end()
        attr_type.wr_end()
    attrtypes.wr_end()

    config_sets = ET.SubElement(settings, "configurationSets")
    for cset_r in dbhelper.select("config_set"):
        el = ET.SubElement(config_sets, "entry")
        make_prop(el, cset_r, "string", "name")
        el2 = ET.SubElement(el, "config-set")
        el3 = ET.SubElement(el2, "configurations")
        for centry_r in dbhelper.select("config_entry", where="config_set=%d" % cset_r["_id"]):
            centry = ET.SubElement(el3, "config")
            make_prop(centry, centry_r, "uuid")
            make_prop(centry, centry_r, "name")
            make_prop(centry, centry_r, "data")
            centry.wr_end()
        el3.wr_end()
        el2.wr_end()
        el.wr_end()
    config_sets.wr_end()

    settings.wr_end()

    root.wr_end()


if __name__ == "__main__":
    argp = argparse.ArgumentParser(description="Export Sqlite DB to PortfolioPerformance XML file")
    argp.add_argument("db", help="input DB (filename/connect string)")
    argp.add_argument("xml_file", nargs="?", help="output XML file (stdout if not provided)")
    argp.add_argument("--dbtype", choices=("sqlite", "pgsql"), default="sqlite", help="select database type")
    argp.add_argument("--sort-events", action="store_true", help="sort events by date (then description)")
    argp.add_argument("--debug", action="store_true", help="enable debug logging")
    argp.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = argp.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    dbhelper.init(args.dbtype, args.db)
    main()
