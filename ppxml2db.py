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
#logging.basicConfig(
#    level=logging.INFO,
#    format='%(asctime)s %(levelname)-5s %(message)s',
#    datefmt='%Y-%m-%d %H:%M:%S',
#)

# Rename field in a dictionary
def ren(d, old, new):
    if old in d:
        d[new] = d[old]
        del d[old]


def as_bool(v):
    return {"false": 0, "true": 1}[v]


def dump_el(el):
    print(ET.tostring(el).decode())


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

    def uuid(self, el):
        id = el.get("reference")
        if id is None:
            id = el.get("id")
        assert id is not None
        return self.id2uuid_map[id]

    @staticmethod
    def is_account_tag(tag):
        return tag in ("account", "referenceAccount", "accountFrom", "accountTo")

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
            elif els[1].tag == "bookmark":
                fields = self.parse_props(els[1], ("label", "pattern"))
                if not fields:
                    value = None
                else:
                    value = json.dumps(fields)
            else:
                value = els[1].text
            fields = {
                "attr_uuid": els[0].text,
                "type": els[1].tag,
                "value": value,
                "seq": seq,
            }
            yield fields

    def handle_price(self, price_el):
            props = ["t", "v"]
            price_fields = self.parse_props(price_el, props)
            ren(price_fields, "v", "value")
            ren(price_fields, "t", "tstamp")
            price_fields["security"] = self.cur_uuid()
            dbhelper.insert("price", price_fields, or_replace=True)

    def handle_latest(self, latest_el):
        if latest_el is not None:
            props = ["t", "v", "high", "low", "volume"]
            latest_fields = self.parse_props(latest_el, props)
            ren(latest_fields, "v", "value")
            ren(latest_fields, "t", "tstamp")
            latest_fields["security"] = self.cur_uuid()
            dbhelper.insert("latest_price", latest_fields, or_replace=True)

    def handle_event(self, event_el):
            props = ["date", "type", "details"]
            fields = self.parse_props(event_el, props)
            fields["security"] = self.cur_uuid()
            dbhelper.insert("security_event", fields)

    def handle_security(self, el):
        if el.get("reference") is not None:
            return

        props = [
            "uuid", "onlineId", "name", "currencyCode", "targetCurrencyCode", "note",
            "isin", "tickerSymbol", "calendar", "wkn", "feedTickerSymbol",
            "feed", "feedURL", "latestFeed", "latestFeedURL",
            ("isRetired", as_bool), "updatedAt"
        ]
        sec = self.parse_props(el, props)
        ren(sec, "currencyCode", "currency")
        ren(sec, "targetCurrencyCode", "targetCurrency")
        dbhelper.insert("security", sec, or_replace=True)

        for fields in self.parse_attributes(el):
            fields["security"] = sec["uuid"]
            dbhelper.insert("security_attr", fields, or_replace=True)

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

    def handle_account(self, el, orderno):
        props = ["uuid", "name", "currencyCode", ("isRetired", as_bool), "updatedAt", "id"]
        fields = self.parse_props(el, props)
        ren(fields, "currencyCode", "currency")
        ren(fields, "id", "_xmlid")
        fields["type"] = "account"
        fields["_order"] = orderno
        dbhelper.insert("account", fields, or_replace=True)
        self.handle_account_attrs(el, fields["uuid"])

    def handle_portfolio(self, el, orderno):
        props = ["uuid", "name", ("isRetired", as_bool), "updatedAt", "id"]
        fields = self.parse_props(el, props)
        ren(fields, "id", "_xmlid")
        acc = el.find("referenceAccount")
        fields["referenceAccount"] = self.uuid(acc)
        fields["type"] = "portfolio"
        fields["_order"] = orderno
        dbhelper.insert("account", fields, or_replace=True)
        self.handle_account_attrs(el, fields["uuid"])

    def handle_watchlist(self, el):
        fields = self.parse_props(el, ["name"])
        id = dbhelper.insert("watchlist", fields, or_replace=True)
        for sec in el.findall("securities/security"):
            fields = {"list": id, "security": self.uuid(sec)}
            dbhelper.insert("watchlist_security", fields, or_replace=True)

    def handle_xact(self, acc_type, acc_uuid, el, orderno):
        # Start with calculating unit aggregates, to add to xact row in DB.
        units_dict = defaultdict(int)
        for unit_el in el.findall("units/unit"):
            am_el = unit_el.find("amount")
            units_dict[unit_el.get("type")] += int(am_el.get("amount"))

        props = ["uuid", "date", "currencyCode", "amount", "shares", "note", "source", "updatedAt", "type", "id"]
        fields = self.parse_props(el, props)
        ren(fields, "currencyCode", "currency")
        ren(fields, "id", "_xmlid")
        fields["account"] = acc_uuid
        fields["acctype"] = acc_type
        fields["_order"] = orderno
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
                "currency": am_el.get("currency"),
            }
            forex_el = unit_el.find("forex")
            if forex_el is not None:
                fields["forex_amount"] = forex_el.get("amount")
                fields["forex_currency"] = forex_el.get("currency")
            rate_el = unit_el.find("exchangeRate")
            if rate_el is not None:
                fields["exchangeRate"] = rate_el.text
            dbhelper.insert("xact_unit", fields, or_replace=True)

    def handle_crossEntry(self, x_el):
            if x_el.get("reference") is not None:
                return

            typ = x_el.get("class")
            if typ == "buysell":
                fields = {
                    "type": typ,
                    "from_acc": self.uuid(x_el.find("portfolio")),
                    "from_xact": self.uuid(x_el.find("portfolioTransaction")),
                    "to_acc": self.uuid(x_el.find("account")),
                    "to_xact": self.uuid(x_el.find("accountTransaction")),
                }
            elif typ == "account-transfer":
                fields = {
                    "type": typ,
                    "from_acc": self.uuid(x_el.find("accountFrom")),
                    "from_xact": self.uuid(x_el.find("transactionFrom")),
                    "to_acc": self.uuid(x_el.find("accountTo")),
                    "to_xact": self.uuid(x_el.find("transactionTo")),
                }
            elif typ == "portfolio-transfer":
                fields = {
                    "type": typ,
                    "from_acc": self.uuid(x_el.find("portfolioFrom")),
                    "from_xact": self.uuid(x_el.find("transactionFrom")),
                    "to_acc": self.uuid(x_el.find("portfolioTo")),
                    "to_xact": self.uuid(x_el.find("transactionTo")),
                }
            else:
                raise NotImplementedError(typ)
            dbhelper.insert("xact_cross_entry", fields, or_replace=True)

    def handle_taxonomy(self, taxon_el):
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

    def handle_dashboard(self, dashb_el):
            props = ["id", "name"]
            fields = self.parse_props(dashb_el, props)
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

    def handle_settings(self, settings_el):
        for bmark_el in settings_el.findall("bookmarks/bookmark"):
            props = ["label", "pattern"]
            fields = self.parse_props(bmark_el, props)
            dbhelper.insert("bookmark", fields, or_replace=True)

        for attr_type_el in settings_el.findall("attributeTypes/attribute-type"):
            props = ["id", "name", "columnLabel", "source", "target", "type", "converterClass"]
            fields = self.parse_props(attr_type_el, props)
            props = []
            for p in self.parse_attributes(attr_type_el, "properties"):
                props.append({"name": p["attr_uuid"], "type": p["type"], "value": p["value"]})
            fields["props_json"] = json.dumps(props)
            dbhelper.insert("attribute_type", fields, or_replace=True)

        for config_set_el in settings_el.findall("configurationSets/entry"):
            props = ["string"]
            fields = self.parse_props(config_set_el, props)
            ren(fields, "string", "name")
            cset_id = dbhelper.insert("config_set", fields, or_replace=True)
            for config_e_el in config_set_el.findall("config-set/configurations/config"):
                props = ["uuid", "name", "data"]
                fields = self.parse_props(config_e_el, props)
                fields["config_set"] = cset_id
                dbhelper.insert("config_entry", fields, or_replace=True)

    def handle_toplevel_properties(self, el):
        for prop_el in el.findall("entry"):
            d = self.parse_entry(prop_el)
            assert d[0][0] == "string"
            assert d[1][0] == "string"
            fields = {"name": d[0][1], "value": d[1][1]}
            dbhelper.insert("property", fields, or_replace=True)

    def handle_client(self, el):
        props = ["version", "baseCurrency"]
        fields = self.parse_props(el, props)
        for n in props:
            dbhelper.insert("property", {"name": n, "value": fields[n], "special": 1}, or_replace=True)

    def __init__(self, xml):
        self.xml = xml
        self.refcache = {}

    def parse(self):
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
        for acc_el in self.etree.xpath(".//*[self::account or self::accountTo]"):
            acc_uuid = self.uuid(acc_el)
            for xact_el in acc_el.findall(".//account-transaction"):
                self.handle_xact("account", acc_uuid, xact_el)

        _log.info("Handling <portfolio-transaction>")
        for acc_el in self.etree.xpath(".//*[self::portfolio or self::portfolioTo]"):
            acc_uuid = self.uuid(acc_el)
            for xact_el in acc_el.findall(".//portfolio-transaction"):
                self.handle_xact("portfolio", acc_uuid, xact_el)

        _log.info("Handling <crossEntry>")
        for x_el in self.etree.findall("//crossEntry"):
            self.handle_crossEntry(x_el)

        _log.info("Handling <taxonomy>")
        for taxon_el in self.etree.findall("taxonomies/taxonomy"):
            self.handle_taxonomy(taxon_el)

        _log.info("Handling <dashboard>")
        for dashb_el in self.etree.findall("dashboards/dashboard"):
            self.handle_dashboard(dashb_el)

        _log.info("Handling <properties>")
        self.handle_toplevel_properties(self.etree.find("properties"))

        _log.info("Handling <settings>")
        self.handle_settings(self.etree.find("settings"))

    def cur_uuid(self):
        return self.container_stack[-1][1]

    def iterparse(self):
        self.el_stack = []
        self.container_stack = []
        self.cur_xmlid = None
        self.id2uuid_map = {}
        self.uuid2ctr_map = {}
        self.el_order = 0
        for event, el in ET.iterparse(self.xml, events=("start", "end")):
            #print(event, el, el.attrib)
            self.el_order += 1
            if event == "start":
                self.el_stack.append(el.tag)
                if el.tag in ("security", "account", "referenceAccount", "accountFrom", "accountTo", "portfolio", "portfolioFrom", "portfolioTo"):
                    self.cur_xmlid = el.get("id")
                    if self.cur_xmlid is not None:
                        # Real element definition, not reference
                        self.container_stack.append([el.tag, None])
                        #print("Pushed on container stack:", self.container_stack)
                elif el.tag in ("account-transaction", "accountTransaction", "portfolio-transaction", "portfolioTransaction", "transactionFrom", "transactionTo"):
                    self.cur_xmlid = el.get("id")
                elif el.tag in ("root", "classification"):
                    self.cur_xmlid = el.get("id")
                elif el.tag in ("taxonomy", "dashboard", "settings"):
                    self.container_stack.append([el.tag, None])

            elif event == "end":
                assert self.el_stack[-1] == el.tag
                self.el_stack.pop()
                if el.tag in ("uuid", "id"):
                    if  self.container_stack and self.container_stack[-1][1] is None:
                        self.container_stack[-1][1] = el.text
                        #print("Setting uuid of top container:", self.container_stack, el.sourceline)
                        self.uuid2ctr_map[el.text] = self.container_stack[-1][0]
                    self.id2uuid_map[self.cur_xmlid] = el.text

                elif el.tag == "price":
                    self.handle_price(el)
                elif el.tag == "latest":
                    self.handle_latest(el)
                elif el.tag == "event":
                    self.handle_event(el)

                elif el.tag == "security":
                    self.handle_security(el)
                elif el.tag == "watchlist":
                    self.handle_watchlist(el)
                elif el.tag in ("account", "accountFrom", "accountTo", "referenceAccount"):
                    if el.get("id"):
                        self.handle_account(el, self.el_order)
                    elif el.tag == "account":
                        xmlid = el.get("reference")
                        dbhelper.execute_insert("UPDATE account SET _order=? WHERE _xmlid=?", (self.el_order, xmlid))
                elif el.tag in ("portfolio", "portfolioFrom", "portfolioTo"):
                    if el.get("id"):
                        self.handle_portfolio(el, self.el_order)
                    elif el.tag == "portfolio":
                        xmlid = el.get("reference")
                        dbhelper.execute_insert("UPDATE account SET _order=? WHERE _xmlid=?", (self.el_order, xmlid))

                elif el.tag == "account-transaction":
                    if el.get("id"):
                        assert self.is_account_tag(self.uuid2ctr_map[self.cur_uuid()]), self.uuid2ctr_map[self.cur_uuid()]
                        self.handle_xact("account", self.cur_uuid(), el, self.el_order)
                    else:
                        xmlid = el.get("reference")
                        dbhelper.execute_insert("UPDATE xact SET _order=? WHERE _xmlid=?", (self.el_order, xmlid))

                elif el.tag == "accountTransaction":
                    if el.get("id"):
                        parent = el.getparent()
                        uuid = self.uuid(parent.find("account"))
                        assert self.is_account_tag(self.uuid2ctr_map[uuid]), self.uuid2ctr_map[uuid]
                        self.handle_xact("account", uuid, el, 0)

                elif el.tag in ("portfolio-transaction",):
                    if el.get("id"):
                        assert self.uuid2ctr_map[self.cur_uuid()].startswith("portfolio")
                        self.handle_xact("portfolio", self.cur_uuid(), el, self.el_order)
                    else:
                        xmlid = el.get("reference")
                        dbhelper.execute_insert("UPDATE xact SET _order=? WHERE _xmlid=?", (self.el_order, xmlid))

                elif el.tag in ("portfolioTransaction",):
                    if el.get("id"):
                        parent = el.getparent()
                        uuid = self.uuid(parent.find("portfolio"))
                        assert self.uuid2ctr_map[uuid].startswith("portfolio"), self.uuid2ctr_map[uuid]
                        self.handle_xact("portfolio", uuid, el, 0)

                elif el.tag == "transactionTo":
                    if el.get("id"):
                        parent = el.getparent()
                        assert parent.tag == "crossEntry"
                        if parent.get("class") == "account-transfer":
                            what = "account"
                            uuid = self.uuid(parent.find("accountTo"))
                        elif parent.get("class") == "portfolio-transfer":
                            what = "portfolio"
                            uuid = self.uuid(parent.find("portfolioTo"))
                        else:
                            assert False, "Unexpected crossEntry class: " + parent.get("class")

                        assert self.uuid2ctr_map[uuid].startswith(what), self.uuid2ctr_map[uuid]
                        self.handle_xact(what, uuid, el, 0)
                elif el.tag == "transactionFrom":
                    if el.get("id"):
                        parent = el.getparent()
                        assert parent.tag == "crossEntry"
                        if parent.get("class") == "account-transfer":
                            what = "account"
                            uuid = self.uuid(parent.find("accountFrom"))
                        elif parent.get("class") == "portfolio-transfer":
                            what = "portfolio"
                            uuid = self.uuid(parent.find("portfolioFrom"))
                        else:
                            assert False, "Unexpected crossEntry class: " + parent.get("class")

                        if what == "account":
                            assert self.is_account_tag(self.uuid2ctr_map[uuid]), self.uuid2ctr_map[uuid]
                        else:
                            assert self.uuid2ctr_map[uuid].startswith(what), self.uuid2ctr_map[uuid]
                        self.handle_xact(what, uuid, el, 0)

                elif el.tag == "crossEntry":
                    if el.get("id"):
                        self.handle_crossEntry(el)

                elif el.tag == "taxonomy":
                    self.handle_taxonomy(el)
                elif el.tag == "dashboard":
                    self.handle_dashboard(el)
                elif el.tag == "settings":
                    self.handle_settings(el)
                elif el.tag == "properties" and self.el_stack[-1] == "client":
                    self.handle_toplevel_properties(el)
                elif el.tag == "client":
                    self.handle_client(el)

                if el.get("reference") is None and self.container_stack and self.container_stack[-1][0] == el.tag:
                    self.container_stack.pop()

                # To save memory, we clear children of processed elements,
                # execept for cases below.
                preserve = False
                if self.container_stack and self.container_stack[-1][0] in ("taxonomy", "dashboard", "settings"):
                    preserve = True
                elif el.tag in ("units", "unit"):
                    preserve = True
                elif el.tag in ("limitPrice", "bookmark"):
                    preserve = True
                elif el.tag in ("map", "entry"):
                    preserve = True
                elif self.el_stack and self.el_stack[-1] == "watchlist" and el.tag == "securities":
                    preserve = True
                elif self.container_stack and self.container_stack[-1][0] in ("security", "account", "portfolio") and el.tag == "attributes":
                    preserve = True

                if not preserve:
                    # Remove children and text of elements. We don't use
                    # el.clear(), as that also removed attributes, but
                    # we want to preserve them (need id/reference at least).
                    for ch in list(el):
                        el.remove(ch)
                        el.text = el.tail = None


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

    with open(args.xml_file, "rb") as f:
        conv = PortfolioPerformanceXML2DB(f)
        conv.iterparse()

    if not args.dry_run:
        dbhelper.commit()
