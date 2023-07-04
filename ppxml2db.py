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
        el = self.resolve(el)
        id_el = el.find("uuid")
        if id_el is None:
            id_el = el.find("id")
        return id_el.text

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
        fields["type"] = "account"
        dbhelper.insert("account", fields, or_replace=True)

    def handle_portfolio(self, el):
        el = self.resolve(el)
        props = ["uuid", "name", "isRetired", "updatedAt"]
        fields = self.parse_props(el, props)
        acc = self.resolve(el.find("referenceAccount"))
        fields["referenceAccount"] = self.uuid(acc)
        fields["type"] = "portfolio"
        dbhelper.insert("account", fields, or_replace=True)

    def handle_watchlist(self, el):
        fields = self.parse_props(el, ["name"])
        id = dbhelper.insert("watchlist", fields, or_replace=True)
        for sec in el.findall("securities/security"):
            sec = self.resolve(sec)
            fields = {"list": id, "security": self.uuid(sec)}
            dbhelper.insert("watchlist_security", fields, or_replace=True)

    def handle_xact(self, acc_type, acc_uuid, el):
        el = self.resolve(el)
        props = ["uuid", "date", "currencyCode", "amount", "shares", "note", "updatedAt", "type"]
        fields = self.parse_props(el, props)
        fields["account"] = acc_uuid
        fields["acctype"] = acc_type
        sec = el.find("security")
        if sec is not None:
            fields["security"] = self.uuid(sec)
        dbhelper.insert("xact", fields, or_replace=True)

        xact_uuid = fields["uuid"]
        for unit_el in el.findall("units/unit"):
            am_el = unit_el.find("amount")
            fields = {
                "xact": xact_uuid,
                "type": unit_el.get("type"),
                "amount": am_el.get("amount"),
                "currencyCode": am_el.get("currency"),
            }
            dbhelper.insert("xact_unit", fields, or_replace=True)

    def handle_taxonomy_level(self, taxon_uuid, parent_uuid, level_el):
        props = ["id", "name", "color", "weight", "rank"]
        fields = self.parse_props(level_el, props)
        ren(fields, "id", "uuid")
        fields["parent"] = parent_uuid
        fields["taxonomy"] = taxon_uuid
        dbhelper.insert("taxonomy_category", fields, or_replace=True)
        for ch_el in level_el.findall("children/classification"):
            self.handle_taxonomy_level(taxon_uuid, fields["uuid"], ch_el)

    def __init__ (self, etree):
        self.etree = etree

        security_els = self.etree.findall("securities/security")
        for s in security_els:
            self.handle_security(s)

        for w in self.etree.findall("watchlists/watchlist"):
            self.handle_watchlist(w)

        account_els = self.etree.findall("accounts/account")
        for el in account_els:
            self.handle_account(el)

        portfolio_els = self.etree.findall("portfolios/portfolio")
        for el in portfolio_els:
            self.handle_portfolio(el)

        for acc_el in self.etree.findall("accounts/account"):
            acc_uuid = self.uuid(acc_el)
            for xact_el in acc_el.findall(".//account-transaction"):
                self.handle_xact("account", acc_uuid, xact_el)

        for acc_el in self.etree.findall(".//portfolio"):
            acc_uuid = self.uuid(acc_el)
            for xact_el in acc_el.findall(".//portfolio-transaction"):
                self.handle_xact("portfolio", acc_uuid, xact_el)

        for x_el in self.etree.findall("//crossEntry"):
            if x_el.get("reference") is not None:
                continue
            fields = {
                "type": x_el.get("class"),
                "portfolio": self.uuid(x_el.find("portfolio")),
                "portfolio_xact": self.uuid(x_el.find("portfolioTransaction")),
                "account": self.uuid(x_el.find("account")),
                "account_xact": self.uuid(x_el.find("accountTransaction")),
            }
            dbhelper.insert("xact_cross_entry", fields, or_replace=True)

        for taxon_el in self.etree.findall("taxonomies/taxonomy"):
            props = ["id", "name"]
            fields = self.parse_props(taxon_el, props)
            ren(fields, "id", "uuid")
            for dim_els in taxon_el.findall("dimensions/string"):
                dim_fields = {
                    "taxonomy": fields["uuid"],
                    "name": "dimension",
                    "value": dim_els.text,
                }
                dbhelper.insert("taxonomy_data", dim_fields, or_replace=True)
            root_el = taxon_el.find("root")
            fields["root"] = self.uuid(root_el)
            dbhelper.insert("taxonomy", fields, or_replace=True)
            self.handle_taxonomy_level(fields["uuid"], None, root_el)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    dbhelper.init(sys.argv[2])
    root = ET.parse(sys.argv[1])
    conv = PortfolioPerformanceXML2DB(root)
    dbhelper.commit()
