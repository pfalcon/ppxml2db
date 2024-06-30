import sys
import argparse
import logging
from collections import defaultdict
from pprint import pprint
import json
import logging
import os.path

import lxml.etree as ET

from version import __version__
import dbhelper


_log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-5s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# Rename field in a dictionary
def ren(d, old, new):
    d[new] = d[old]
    del d[old]


def as_bool(v):
    return {"false": 0, "true": 1}[v]


class PortfolioPerformanceXML2DB:

    def parse_props(self, el, props):
        d = {}
        for p in props:
            conv = lambda x: x
            if isinstance(p, tuple):
                conv = p[1]
                p = p[0]
            pel = el.find(p)
            if pel is not None:
                d[p] = conv("" if pel.text is None else pel.text)
            elif p in el.attrib:
                # Otherwise try attribute (will return None if not there)
                d[p] = conv(el.get(p))
        return d

    def resolve(self, el):
        ref = el.get("reference")
        if ref is not None:
            norm = os.path.normpath(self.etree.getelementpath(el) + "/" + ref)
            # Workaround for Windows.
            norm = norm.replace("\\", "/")
            el = self.refcache.get(norm)
            if el is None:
                el = self.etree.find(norm)
                self.refcache[norm] = el
        return el

    def uuid(self, el):
        el = self.resolve(el)
        id_el = el.find("uuid")
        if id_el is None:
            id_el = el.find("id")
        return id_el.text

    def parse_entry(self, entry_el):
        els = entry_el.findall("*")
        assert len(els) == 2, len(els)
        return [(e.tag, e.text) for e in els]

    def parse_configuration(self, pel):
        conf = {}
        for c_el in pel.findall("configuration/entry"):
            d = self.parse_entry(c_el)
            assert d[0][0] == "string"
            assert d[1][0] == "string"
            conf[d[0][1]] = d[1][1] if d[1][1] is not None else ""
        return conf

    def parse_attributes(self, pel, el_tag="attributes/map"):
        attr_els = pel.findall(el_tag + "/entry")
        for seq, attr_el in enumerate(attr_els):
            els = attr_el.findall("*")
            assert len(els) == 2
            assert els[0].tag == "string"
            if els[1].tag == "limitPrice":
                fields = self.parse_props(els[1], ("operator", "value"))
                value = "%s %s" % (fields["operator"], fields["value"])
            else:
                value = els[1].text
            fields = {
                "attr_uuid": els[0].text,
                "type": els[1].tag,
                "value": value,
                "seq": seq,
            }
            yield fields

    def handle_security(self, el):
        props = [
            "uuid", "onlineId", "name", "currencyCode", "note",
            "isin", "tickerSymbol", "calendar", "wkn", "feedTickerSymbol",
            "feed", "feedURL", "latestFeed", "latestFeedURL",
            ("isRetired", as_bool), "updatedAt"
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

        for fields in self.parse_attributes(el):
            fields["security"] = sec["uuid"]
            dbhelper.insert("security_attr", fields, or_replace=True)

        for event_el in el.findall("events/event"):
            props = ["date", "type", "details"]
            fields = self.parse_props(event_el, props)
            fields["security"] = sec["uuid"]
            dbhelper.insert("security_event", fields)

        prop_els = el.findall("property")
        for seq, prop_el in enumerate(prop_els):
            fields = {
                "security": sec["uuid"], "type": prop_el.get("type"),
                "name": prop_el.get("name"), "value": prop_el.text, "seq": seq,
            }
            dbhelper.insert("security_prop", fields, or_replace=True)

    def handle_account_attrs(self, pel, uuid):
        for fields in self.parse_attributes(pel):
            fields["account"] = uuid
            dbhelper.insert("account_attr", fields, or_replace=True)

    def handle_account(self, el):
        el = self.resolve(el)
        props = ["uuid", "name", "currencyCode", ("isRetired", as_bool), "updatedAt"]
        fields = self.parse_props(el, props)
        fields["type"] = "account"
        dbhelper.insert("account", fields, or_replace=True)
        self.handle_account_attrs(el, fields["uuid"])

    def handle_portfolio(self, el):
        el = self.resolve(el)
        props = ["uuid", "name", ("isRetired", as_bool), "updatedAt"]
        fields = self.parse_props(el, props)
        acc = self.resolve(el.find("referenceAccount"))
        fields["referenceAccount"] = self.uuid(acc)
        fields["type"] = "portfolio"
        dbhelper.insert("account", fields, or_replace=True)
        self.handle_account_attrs(el, fields["uuid"])

    def handle_watchlist(self, el):
        fields = self.parse_props(el, ["name"])
        id = dbhelper.insert("watchlist", fields, or_replace=True)
        for sec in el.findall("securities/security"):
            sec = self.resolve(sec)
            fields = {"list": id, "security": self.uuid(sec)}
            dbhelper.insert("watchlist_security", fields, or_replace=True)

    def handle_xact(self, acc_type, acc_uuid, el):
        el = self.resolve(el)

        # Start with calculating unit aggregates, to add to xact row in DB.
        units_dict = defaultdict(int)
        for unit_el in el.findall("units/unit"):
            am_el = unit_el.find("amount")
            units_dict[unit_el.get("type")] += int(am_el.get("amount"))

        props = ["uuid", "date", "currencyCode", "amount", "shares", "note", "updatedAt", "type"]
        fields = self.parse_props(el, props)
        fields["account"] = acc_uuid
        fields["acctype"] = acc_type
        sec = el.find("security")
        if sec is not None:
            fields["security"] = self.uuid(sec)
        fields["fees"] = units_dict["FEE"]
        fields["taxes"] = units_dict["TAX"]
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
        level_uuid = fields["uuid"]
        dbhelper.insert("taxonomy_category", fields, or_replace=True)

        for data_el in level_el.findall("data/entry"):
            data = self.parse_entry(data_el)
            fields = {
                "name": data[0][1],
                "value": data[1][1],
                "category": level_uuid,
                "taxonomy": taxon_uuid,
            }
            dbhelper.insert("taxonomy_data", fields, or_replace=True)

        for as_el in level_el.findall("assignments/assignment"):
            props = ["weight", "rank"]
            fields = self.parse_props(as_el, props)
            el = as_el.find("investmentVehicle")
            fields["item_type"] = el.get("class")
            fields["item"] = self.uuid(el)
            fields["category"] = level_uuid
            fields["taxonomy"] = taxon_uuid
            dbhelper.insert("taxonomy_assignment", fields, or_replace=True)

        for ch_el in level_el.findall("children/classification"):
            self.handle_taxonomy_level(taxon_uuid, level_uuid, ch_el)

    def __init__ (self, etree):
        self.etree = etree
        self.refcache = {}

        props = ["version", "baseCurrency"]
        fields = self.parse_props(self.etree, props)
        for n in props:
            dbhelper.insert("property", {"name": n, "value": fields[n], "special": 1}, or_replace=True)

        _log.info("Handling <security>")
        security_els = self.etree.findall("securities/security")
        for s in security_els:
            self.handle_security(s)

        _log.info("Handling <watchlist>")
        for w in self.etree.findall("watchlists/watchlist"):
            self.handle_watchlist(w)

        _log.info("Handling <account>")
        account_els = self.etree.findall("accounts/account")
        for el in account_els:
            self.handle_account(el)

        _log.info("Handling <portfolio>")
        portfolio_els = self.etree.findall("portfolios/portfolio")
        for el in portfolio_els:
            self.handle_portfolio(el)

        _log.info("Handling <account-transaction>")
        for acc_el in self.etree.findall(".//account"):
            acc_uuid = self.uuid(acc_el)
            for xact_el in acc_el.findall(".//account-transaction"):
                self.handle_xact("account", acc_uuid, xact_el)

        _log.info("Handling <portfolio-transaction>")
        for acc_el in self.etree.findall(".//portfolio"):
            acc_uuid = self.uuid(acc_el)
            for xact_el in acc_el.findall(".//portfolio-transaction"):
                self.handle_xact("portfolio", acc_uuid, xact_el)

        _log.info("Handling <crossEntry>")
        for x_el in self.etree.findall("//crossEntry"):
            if x_el.get("reference") is not None:
                continue
            typ = x_el.get("class")
            if typ == "buysell":
                fields = {
                    "type": typ,
                    "portfolio": self.uuid(x_el.find("portfolio")),
                    "portfolio_xact": self.uuid(x_el.find("portfolioTransaction")),
                    "account": self.uuid(x_el.find("account")),
                    "account_xact": self.uuid(x_el.find("accountTransaction")),
                }
            elif typ == "account-transfer":
                raise NotImplementedError
                fields = {
                    "type": typ,
                    "accountFrom": self.uuid(x_el.find("accountFrom")),
                    "accountFrom_xact": self.uuid(x_el.find("transactionFrom")),
                    "account": self.uuid(x_el.find("accountTo")),
                    "account_xact": self.uuid(x_el.find("transactionTo")),
                }
            else:
                raise NotImplementedError
            dbhelper.insert("xact_cross_entry", fields, or_replace=True)

        _log.info("Handling <taxonomy>")
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

        _log.info("Handling <dashboard>")
        for dashb_el in self.etree.findall("dashboards/dashboard"):
            fields = {"name": dashb_el.get("name")}
            conf = self.parse_configuration(dashb_el)
            fields["config_json"] = json.dumps(conf)

            columns = []
            for col_el in dashb_el.findall("columns/column"):
                props = ["weight"]
                col_fields = self.parse_props(col_el, props)
                col_fields["widgets"] = []
                for widget_el in col_el.findall("widgets/widget"):
                    wid_fields = self.parse_props(widget_el, ["label"])
                    wid_fields["type"] = widget_el.get("type")
                    if widget_el.find("configuration") is not None:
                        conf = self.parse_configuration(widget_el)
                        wid_fields["config"] = conf
                    col_fields["widgets"].append(wid_fields)
                columns.append(col_fields)
            fields["columns_json"] = json.dumps(columns)
            dbhelper.insert("dashboard", fields, or_replace=True)

        _log.info("Handling <properties>")
        for prop_el in self.etree.findall("properties/entry"):
            d = self.parse_entry(prop_el)
            assert d[0][0] == "string"
            assert d[1][0] == "string"
            fields = {"name": d[0][1], "value": d[1][1]}
            dbhelper.insert("property", fields, or_replace=True)

        _log.info("Handling <settings>")
        for bmark_el in self.etree.findall("settings/bookmarks/bookmark"):
            props = ["label", "pattern"]
            fields = self.parse_props(bmark_el, props)
            dbhelper.insert("bookmark", fields, or_replace=True)

        for attr_type_el in self.etree.findall("settings/attributeTypes/attribute-type"):
            props = ["id", "name", "columnLabel", "source", "target", "type", "converterClass"]
            fields = self.parse_props(attr_type_el, props)
            props = []
            for p in self.parse_attributes(attr_type_el, "properties"):
                props.append({"name": p["attr_uuid"], "type": p["type"], "value": p["value"]})
            fields["props_json"] = json.dumps(props)
            dbhelper.insert("attribute_type", fields, or_replace=True)

        for config_set_el in self.etree.findall("settings/configurationSets/entry"):
            props = ["string"]
            fields = self.parse_props(config_set_el, props)
            ren(fields, "string", "name")
            cset_id = dbhelper.insert("config_set", fields, or_replace=True)
            for config_e_el in config_set_el.findall("config-set/configurations/config"):
                props = ["uuid", "name", "data"]
                fields = self.parse_props(config_e_el, props)
                fields["config_set"] = cset_id
                dbhelper.insert("config_entry", fields, or_replace=True)


if __name__ == "__main__":
    argp = argparse.ArgumentParser(description="Import PortfolioPerformance XML file to Sqlite DB")
    argp.add_argument("xml_file", help="input XML file")
    argp.add_argument("db_file", help="output DB file")
    argp.add_argument("--debug", action="store_true", help="enable debug logging")
    argp.add_argument("--dry-run", action="store_true", help="don't commit changes to DB")
    argp.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = argp.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    dbhelper.init(args.db_file)
    with open(args.xml_file, encoding="utf-8") as f:
        root = ET.parse(f)
    conv = PortfolioPerformanceXML2DB(root)
    if not args.dry_run:
        dbhelper.commit()
