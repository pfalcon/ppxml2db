import sys
import argparse
import logging
import os.path
import json

import lxml.etree as ET

import dbhelper


# uuid to #
sec_map = {}

# uuid to element
output_els = {}

# (portfolio_xact, account_xact) to element
cross_els = {}


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
        else:
            ET.SubElement(enel, r["type"]).text = r["value"]


def make_attributes(pel, rows):
    attributes = ET.SubElement(pel, "attributes")
    make_map(attributes, rows)


def make_entry(pel, k, v, type="string"):
    e = ET.SubElement(pel, "entry")
    ET.SubElement(e, "string").text = k
    ET.SubElement(e, type).text = v


def make_configuration(pel, conf):
    conf_el = ET.SubElement(pel, "configuration")
    for k, v in conf.items():
        make_entry(conf_el, k, v)


def security_ref(uuid, levels=4):
    ref = "../" * levels + "securities/security"
    i = sec_map[uuid]
    if i != 0:
        ref += "[%d]" % (i + 1)
    return ref


def make_ref(etree, el, to_el):
    rel_path = os.path.relpath(etree.getelementpath(to_el), etree.getelementpath(el))
    rel_path = rel_path.replace("[1]", "")
    # Workaround for Windows.
    rel_path = rel_path.replace("\\", "/")
    el.set("reference", rel_path)


def try_ref(etree, el, uuid):
    if uuid in output_els:
        make_ref(etree, el, output_els[uuid])
        return True


def make_xact(etree, pel, tag, xact_r):
            xact = ET.SubElement(pel, tag)
            if try_ref(etree, xact, xact_r["uuid"]):
                return

            output_els[xact_r["uuid"]] = xact
            make_prop(xact, xact_r, "uuid")
            make_prop(xact, xact_r, "date")
            make_prop(xact, xact_r, "currencyCode")
            make_prop(xact, xact_r, "amount")
            if xact_r["security"] is not None:
                s = ET.SubElement(xact, "security")
                #s.set("reference", security_ref(xact_r["security"], 5))
                assert try_ref(etree, s, xact_r["security"])

            # 0 or 1
            if xact_r["acctype"] == "account":
                crit = "account_xact='%s'"
            else:
                crit = "portfolio_xact='%s'"
            for x_r in dbhelper.select("xact_cross_entry", where=crit % xact_r["uuid"]):
                #print(dict(x_r))
                x = ET.SubElement(xact, "crossEntry")
                x.set("class", x_r["type"])
                cross_key = (x_r["type"], x_r["portfolio_xact"], x_r["account_xact"])
                existing_x = cross_els.get(cross_key)
                if existing_x is not None:
                    make_ref(etree, x, existing_x)
                    continue
                cross_els[cross_key] = x
                if x_r["type"] == "account-transfer":
                    rf = ET.SubElement(x, "accountFrom")
                    assert try_ref(etree, rf, x_r["accountFrom"])
                    rf = ET.SubElement(x, "transactionFrom")
                    assert try_ref(etree, rf, x_r["accountFrom_xact"])
                    accto_r = dbhelper.select("account", where="uuid='%s'" % x_r["account"])[0]
                    make_account(etree, x, accto_r, el_name="accountTo")
                else:
                    make_portfolio(etree, x, x_r["portfolio"])
                    rf = ET.SubElement(x, "portfolioTransaction")
                    assert try_ref(etree, rf, x_r["portfolio_xact"])
                    acc_r = dbhelper.select("account", where="uuid='%s'" % x_r["account"])[0]
                    make_account(etree, x, acc_r)

                    acc_xact_r = dbhelper.select("xact", where="uuid='%s'" % x_r["account_xact"])[0]
                    make_xact(etree, x, "accountTransaction", acc_xact_r)

            make_prop(xact, xact_r, "shares")
            make_prop(xact, xact_r, "note")

            unit_rows = dbhelper.select("xact_unit", where="xact='%s'" % xact_r["uuid"])
            if unit_rows:
                units = ET.SubElement(xact, "units")
                for unit_r in unit_rows:
                    u = ET.SubElement(units, "unit")
                    u.set("type", unit_r["type"])
                    a = ET.SubElement(u, "amount")
                    a.set("currency", unit_r["currencyCode"])
                    a.set("amount", str(unit_r["amount"]))

            make_prop(xact, xact_r, "updatedAt")
            make_prop(xact, xact_r, "type")


def make_xacts(etree, pel, acc_uuid):
        for xact_r in dbhelper.select("xact", where="account='%s'" % acc_uuid):
            tag = {"account": "account-transaction", "portfolio": "portfolio-transaction"}[xact_r["acctype"]]
            make_xact(etree, pel, tag, xact_r)


def make_portfolio(etree, pel, uuid):
        el = ET.SubElement(pel, "portfolio")
        if try_ref(etree, el, uuid):
            return
        output_els[uuid] = el
        port_r = dbhelper.select("account", where="uuid='%s'" % uuid)[0]
        make_prop(el, port_r, "uuid")
        make_prop(el, port_r, "name")
        make_prop(el, port_r, "isRetired", conv=as_bool)
        a = ET.SubElement(el, "referenceAccount")
        try_ref(etree, a, port_r["referenceAccount"])

        xacts = ET.SubElement(el, "transactions")
        make_xacts(etree, xacts, port_r["uuid"])

        attr_rows = dbhelper.select("account_attr", where="account='%s'" % port_r["uuid"], order="seq")
        make_attributes(el, attr_rows)

        make_prop(el, port_r, "updatedAt")


def make_account(etree, pel, acc_r, el_name="account"):
        acc = ET.SubElement(pel, el_name)
        if try_ref(etree, acc, acc_r["uuid"]):
            return
        output_els[acc_r["uuid"]] = acc
        make_prop(acc, acc_r, "uuid")
        make_prop(acc, acc_r, "name")
        make_prop(acc, acc_r, "currencyCode")
        make_prop(acc, acc_r, "isRetired", conv=as_bool)

        xacts = ET.SubElement(acc, "transactions")
        make_xacts(etree, xacts, acc_r["uuid"])

        attr_rows = dbhelper.select("account_attr", where="account='%s'" % acc_r["uuid"], order="seq")
        make_attributes(acc, attr_rows)

        make_prop(acc, acc_r, "updatedAt")


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


def custom_dump(el, stream):
    stream.write("<%s" % el.tag)
    for k, v in el.attrib.items():
        stream.write(' %s="%s"' % (k, v))
    if el.text is None and not len(el):
        stream.write("/>")
    else:
        stream.write(">")
        if el.text:
            stream.write(quote_text(el.text))
        for ch in el:
            custom_dump(ch, stream)
        stream.write("</%s>" % el.tag)
    if el.tail:
        stream.write(el.tail)


def make_taxonomy_level(etree, pel, level_r):
        tag = "root" if level_r["parent"] is None else "classification"
        level = ET.SubElement(pel, tag)
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

        assgn = ET.SubElement(level, "assignments")
        for a_r in dbhelper.select("taxonomy_assignment", where="category='%s'" % level_r["uuid"]):
            a = ET.SubElement(assgn, "assignment")
            iv = ET.SubElement(a, "investmentVehicle")
            iv.set("class", a_r["item_type"])
            assert try_ref(etree, iv, a_r["item"])
            make_prop(a, a_r, "weight")
            make_prop(a, a_r, "rank")

        make_prop(level, level_r, "weight")
        make_prop(level, level_r, "rank")

        data_rows = dbhelper.select("taxonomy_data", where="category='%s'" % level_r["uuid"])
        if data_rows:
            data = ET.SubElement(level, "data")
            for d_r in data_rows:
                d_e = ET.SubElement(data, "entry")
                ET.SubElement(d_e, "string").text = d_r["name"]
                ET.SubElement(d_e, "string").text = d_r["value"]

def main():
    root = ET.Element("client")
    etree = ET.ElementTree(root)
    for n in ["version", "baseCurrency"]:
        row = dbhelper.select("property", where="name='%s'" % n)[0]
        ET.SubElement(root, n).text = row["value"]

    securities = ET.SubElement(root, "securities")

    for i, sec_r in enumerate(dbhelper.select("security")):
    #    print(dict(sec_r))
        sec_map[sec_r["uuid"]] = i
        sec = ET.SubElement(securities, "security")
        output_els[sec_r["uuid"]] = sec
        make_prop(sec, sec_r, "uuid")
        make_prop(sec, sec_r, "onlineId")
        make_prop(sec, sec_r, "name")
        make_prop(sec, sec_r, "currencyCode")
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

        attr_rows = dbhelper.select("security_attr", where="security='%s'" % sec_r["uuid"], order="seq")
        make_attributes(sec, attr_rows)

        events = ET.SubElement(sec, "events")
        for event_r in dbhelper.select("security_event", where="security='%s'" % sec_r["uuid"]):
            event = ET.SubElement(events, "event")
            make_prop(event, event_r, "date")
            make_prop(event, event_r, "type")
            make_prop(event, event_r, "details")

        for prop_r in dbhelper.select("security_prop", where="security='%s'" % sec_r["uuid"], order="seq"):
            p = ET.SubElement(sec, "property")
            p.set("type", prop_r["type"])
            p.set("name", prop_r["name"])
            p.text = prop_r["value"]

        make_prop(sec, sec_r, "isRetired", conv=as_bool)
        make_prop(sec, sec_r, "updatedAt")

    watchlists = ET.SubElement(root, "watchlists")
    for wlist_r in dbhelper.select("watchlist"):
        wlist = ET.SubElement(watchlists, "watchlist")
        make_prop(wlist, wlist_r, "name")
        secs = ET.SubElement(wlist, "securities")
        for wlist_sec_r in dbhelper.select("watchlist_security", where="list=%d" % wlist_r["_id"]):
            s = ET.SubElement(secs, "security")
            s.set("reference", security_ref(wlist_sec_r["security"]))

    accounts = ET.SubElement(root, "accounts")
    for acc_r in dbhelper.select("account", where="type='account'"):
        make_account(etree, accounts, acc_r)

    portfolios = ET.SubElement(root, "portfolios")
    for acc_r in dbhelper.select("account", where="type='portfolio'"):
        make_portfolio(etree, portfolios, acc_r["uuid"])

    plans = ET.SubElement(root, "plans")


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
        e_r = dbhelper.select("taxonomy_category", where="uuid='%s'" % taxon_r["root"])[0]
        make_taxonomy_level(etree, taxon, e_r)


    dashboards = ET.SubElement(root, "dashboards")
    for dashb_r in dbhelper.select("dashboard"):
        dashb = ET.SubElement(dashboards, "dashboard")
        dashb.set("name", dashb_r["name"])
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


    properties = ET.SubElement(root, "properties")
    for prop_r in dbhelper.select("property", where="special=0"):
        make_entry(properties, prop_r["name"], prop_r["value"])

    settings = ET.SubElement(root, "settings")

    bookmarks = ET.SubElement(settings, "bookmarks")
    for bmark_r in dbhelper.select("bookmark"):
        bmark = ET.SubElement(bookmarks, "bookmark")
        make_prop(bmark, bmark_r, "label")
        make_prop(bmark, bmark_r, "pattern")

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

    config_sets = ET.SubElement(settings, "configurationSets")
    for cset_r in dbhelper.select("config_set"):
        el = ET.SubElement(config_sets, "entry")
        make_prop(el, cset_r, "string", "name")
        el = ET.SubElement(el, "config-set")
        el = ET.SubElement(el, "configurations")
        for centry_r in dbhelper.select("config_entry", where="config_set=%d" % cset_r["_id"]):
            centry = ET.SubElement(el, "config")
            make_prop(centry, centry_r, "uuid")
            make_prop(centry, centry_r, "name")
            make_prop(centry, centry_r, "data")


    ET.indent(root)
    #ET.dump(root)
    custom_dump(root, sys.stdout)


if __name__ == "__main__":
    argp = argparse.ArgumentParser(description="Export Sqlite DB to PortfolioPerformance XML file")
    argp.add_argument("db_file", help="output DB file")
    argp.add_argument("--debug", action="store_true", help="enable debug logging")
    args = argp.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    dbhelper.init(args.db_file)
    main()
