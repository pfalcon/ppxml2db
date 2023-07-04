import sys
import os.path

import lxml.etree as ET

import dbhelper


# uuid to #
sec_map = {}

# uuid to element
output_els = {}

# (portfolio_xact, account_xact) to element
cross_els = {}


def make_prop(pel, row, prop, row_prop=None):
    if row[row_prop or prop] is not None:
        el = ET.SubElement(pel, prop)
        el.text = str(row[row_prop or prop])


def make_map(pel, rows):
    mapel = ET.SubElement(pel, "map")
    for r in rows:
        enel = ET.SubElement(mapel, "entry")
        ET.SubElement(enel, "string").text = r["attr_uuid"]
        ET.SubElement(enel, r["type"]).text = r["value"]


def security_ref(uuid, levels=4):
    ref = "../" * levels + "securities/security"
    i = sec_map[uuid]
    if i != 0:
        ref += "[%d]" % (i + 1)
    return ref


def make_ref(etree, el, to_el):
    rel_path = os.path.relpath(etree.getelementpath(to_el), etree.getelementpath(el))
    rel_path = rel_path.replace("[1]", "")
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
                #print(x_r)
                x = ET.SubElement(xact, "crossEntry")
                x.set("class", x_r["type"])
                cross_key = (x_r["portfolio_xact"], x_r["account_xact"])
                existing_x = cross_els.get(cross_key)
                if existing_x is not None:
                    make_ref(etree, x, existing_x)
                    continue
                cross_els[cross_key] = x
                make_portfolio(etree, x, x_r["portfolio"])
                rf = ET.SubElement(x, "portfolioTransaction")
                assert try_ref(etree, rf, x_r["portfolio_xact"])
                rf = ET.SubElement(x, "account")
                assert try_ref(etree, rf, x_r["account"])

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
        make_prop(el, port_r, "isRetired")
        a = ET.SubElement(el, "referenceAccount")
        assert try_ref(etree, a, port_r["referenceAccount"])

        xacts = ET.SubElement(el, "transactions")
        make_xacts(etree, xacts, port_r["uuid"])

        make_prop(el, port_r, "updatedAt")


def make_account(etree, pel, acc_r):
        acc = ET.SubElement(pel, "account")
        output_els[acc_r["uuid"]] = acc
        make_prop(acc, acc_r, "uuid")
        make_prop(acc, acc_r, "name")
        make_prop(acc, acc_r, "currencyCode")
        make_prop(acc, acc_r, "isRetired")

        xacts = ET.SubElement(acc, "transactions")
        make_xacts(etree, xacts, acc_r["uuid"])

        make_prop(acc, acc_r, "updatedAt")


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


def main():
    root = ET.Element("client")
    etree = ET.ElementTree(root)
    ET.SubElement(root, "version").text = "56"
    ET.SubElement(root, "baseCurrency").text = "USD"
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
        make_prop(sec, sec_r, "wkn")
        make_prop(sec, sec_r, "feedTickerSymbol")
        make_prop(sec, sec_r, "feed")

        prices = ET.SubElement(sec, "prices")
        for price_r in dbhelper.select("price", where="security='%s'" % sec_r["uuid"]):
            p = ET.SubElement(prices, "price")
            p.set("t", price_r["tstamp"])
            p.set("v", str(price_r["value"]))

        # Can be 0 or 1
        for latest_r in dbhelper.select("latest_price", where="security='%s'" % sec_r["uuid"]):
            latest = ET.SubElement(sec, "latest")
            latest.set("t", latest_r["tstamp"])
            latest.set("v", str(latest_r["value"]))
            make_prop(latest, latest_r, "high")
            make_prop(latest, latest_r, "low")
            make_prop(latest, latest_r, "volume")

        attributes = ET.SubElement(sec, "attributes")
        attr_rows = dbhelper.select("security_attr", where="security='%s'" % sec_r["uuid"], order="seq")
        make_map(attributes, attr_rows)

        events = ET.SubElement(sec, "events")

        for prop_r in dbhelper.select("security_prop", where="security='%s'" % sec_r["uuid"], order="seq"):
            p = ET.SubElement(sec, "property")
            p.set("type", prop_r["type"])
            p.set("name", prop_r["name"])
            p.text = prop_r["value"]

        make_prop(sec, sec_r, "isRetired")
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


    ET.indent(root)
    ET.dump(root)
    #root.write(sys.stdout)


if __name__ == "__main__":
    dbhelper.init(sys.argv[1])
    main()
