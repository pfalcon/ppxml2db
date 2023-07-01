import sys

import xml.etree.ElementTree as ET

import dbhelper


def make_prop(pel, row, prop):
    if row[prop] is not None:
        el = ET.SubElement(pel, prop)
        el.text = str(row[prop])


def make_map(pel, rows):
    mapel = ET.SubElement(pel, "map")
    for r in rows:
        enel = ET.SubElement(mapel, "entry")
        ET.SubElement(enel, "string").text = r["attr_uuid"]
        ET.SubElement(enel, r["type"]).text = r["value"]


def main():
    root = ET.Element("client")
    ET.SubElement(root, "version").text = "56"
    ET.SubElement(root, "baseCurrency").text = "USD"
    securities = ET.SubElement(root, "securities")

    for sec_r in dbhelper.select("security"):
    #    print(dict(sec_r))
        sec = ET.SubElement(securities, "security")
        make_prop(sec, sec_r, "uuid")
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

        make_prop(sec, sec_r, "isRetired")
        make_prop(sec, sec_r, "updatedAt")


    ET.indent(root)
    ET.dump(root)
    #root.write(sys.stdout)


if __name__ == "__main__":
    dbhelper.init(sys.argv[1])
    main()
