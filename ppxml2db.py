import sys
import logging
from pprint import pprint

import lxml.etree as ET

import dbhelper


# Rename field in a dictionary
def ren(d, old, new):
    d[new] = d[old]
    del d[old]


class PortfolioPerformanceXML2DB:

    def parse_props(self, el, props):
        d = {}
        for p in props:
            pel = el.find(p)
            if pel is not None:
                d[p] = pel.text
            else:
                # Otherwise try attribute (will return None if not there)
                d[p] = el.get(p)
        return d

    def resolve(self, el):
        ref = el.get("reference")
        if ref is not None:
            el = self.etree.find(self.etree.getelementpath(el) + "/" + ref)
        return el

    def uuid(self, el):
        return el.find("uuid").text

    def handle_security(self, el):
        props = [
            "uuid", "onlineId", "name", "currencyCode", "note",
            "isin", "tickerSymbol", "wkn", "feedTickerSymbol", "feed",
            "isRetired", "updatedAt"
        ]
        sec = self.parse_props(el, props)
        dbhelper.insert("security", sec, or_replace=True)

        latest_el = el.find("latest")
        if latest_el is not None:
            props = ["t", "v", "high", "low", "volume"]
            latest_fields = self.parse_props(latest_el, props)
            ren(latest_fields, "v", "value")
            ren(latest_fields, "t", "tstamp")
            latest_fields["security"] = sec["uuid"]
            dbhelper.insert("latest_price", latest_fields, or_replace=True)

        prices_els = el.findall("prices/price")
        for price_el in prices_els:
            props = ["t", "v"]
            price_fields = self.parse_props(price_el, props)
            ren(price_fields, "v", "value")
            ren(price_fields, "t", "tstamp")
            price_fields["security"] = sec["uuid"]
            dbhelper.insert("price", price_fields, or_replace=True)

        attr_els = el.findall("attributes/map/entry")
        for seq, attr_el in enumerate(attr_els):
            els = attr_el.findall("*")
            assert len(els) == 2
            assert els[0].tag == "string"
            fields = {
                "security": sec["uuid"], "attr_uuid": els[0].text,
                "type": els[1].tag, "value": els[1].text, "seq": seq,
            }
            dbhelper.insert("security_attr", fields, or_replace=True)

        prop_els = el.findall("property")
        for seq, prop_el in enumerate(prop_els):
            fields = {
                "security": sec["uuid"], "type": prop_el.get("type"),
                "name": prop_el.get("name"), "value": prop_el.text, "seq": seq,
            }
            dbhelper.insert("security_prop", fields, or_replace=True)

    def handle_account(self, el):
        props = ["uuid", "name", "currencyCode", "isRetired", "updatedAt"]
        fields = self.parse_props(el, props)
        dbhelper.insert("account", fields, or_replace=True)

    def handle_portfolio(self, el):
        el = self.resolve(el)
        props = ["uuid", "name", "isRetired", "updatedAt"]
        fields = self.parse_props(el, props)
        acc = self.resolve(el.find("referenceAccount"))
        fields["referenceAccount"] = self.uuid(acc)
        dbhelper.insert("portfolio", fields, or_replace=True)

    def __init__ (self, etree):
        self.etree = etree

        security_els = self.etree.findall("securities/security")
        for s in security_els:
            self.handle_security(s)

        account_els = self.etree.findall("accounts/account")
        for el in account_els:
            self.handle_account(el)

        portfolio_els = self.etree.findall("portfolios/portfolio")
        for el in portfolio_els:
            self.handle_portfolio(el)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    dbhelper.init(sys.argv[2])
    root = ET.parse(sys.argv[1])
    conv = PortfolioPerformanceXML2DB(root)
    dbhelper.commit()
