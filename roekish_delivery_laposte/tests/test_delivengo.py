# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

DELIVENGO_MODULE = (
    "odoo.addons.roekish_delivery_laposte.models.delivery_carrier_delivengo"
)


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.ok = status_code < 400
        self.reason = "Fake"
        self.text = json.dumps(body) if body is not None else ""
        self._body = body

    def json(self):
        return self._body


class TestDeliveryDelivengo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_id.write(
            {
                "street": "26 rue George Sand",
                "zip": "75016",
                "city": "Paris",
                "country_id": cls.env.ref("base.fr").id,
                "phone": "06 12 34 56 78",
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Delivengo", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Delivengo Test",
                "delivery_type": "delivengo",
                "product_id": cls.product.id,
                "laposte_pricing_method": "grid",
                "delivengo_api_key": "Oono8eez7eez9NRZ3xaeFaeh8hee3u",
            }
        )
        cls.env["delivery.laposte.tariff"].create(
            [
                {
                    "carrier_id": cls.carrier.id,
                    "zone": "DGO1",
                    "max_weight": 0.25,
                    "price": 6.46,
                },
                {
                    "carrier_id": cls.carrier.id,
                    "zone": "DGO1",
                    "max_weight": 2.0,
                    "price": 12.67,
                },
                {
                    "carrier_id": cls.carrier.id,
                    "zone": "DGO2",
                    "max_weight": 2.0,
                    "price": 34.90,
                },
            ]
        )
        cls.boxed = cls.env["product.product"].create(
            {
                "name": "Black tee-shirt",
                "is_storable": True,
                "weight": 0.15,
                "lst_price": 32.0,
                "hs_code": "6109.10",
            }
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _partner(self, country_xmlid, **vals):
        values = {
            "name": "John Smith",
            "street": "1 Street J.F.Kennedy",
            "zip": "02155",
            "city": "Medford",
            "email": "john@example.com",
            "country_id": self.env.ref(country_xmlid).id,
        }
        values.update(vals)
        return self.env["res.partner"].create(values)

    def _state(self, code):
        return self.env["res.country.state"].search(
            [("country_id", "=", self.env.ref("base.us").id), ("code", "=", code)],
            limit=1,
        )

    def _order(self, partner, product=None, qty=1):
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "carrier_id": self.carrier.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": (product or self.boxed).id,
                            "product_uom_qty": qty,
                        },
                    )
                ],
            }
        )

    def _delivery(self, partner, **kwargs):
        order = self._order(partner, **kwargs)
        order.action_confirm()
        picking = order.picking_ids[:1]
        self.assertTrue(picking, "a delivery order should have been created")
        return picking

    # ------------------------------------------------------------------
    # zones and rating
    # ------------------------------------------------------------------
    def test_zone_mapping(self):
        get_zone = self.carrier._delivengo_get_zone
        self.assertEqual(get_zone(self.env.ref("base.de")), "DGO1")
        self.assertEqual(get_zone(self.env.ref("base.uk")), "DGO1")
        self.assertEqual(get_zone(self.env.ref("base.ch")), "DGO2")
        self.assertEqual(get_zone(self.env.ref("base.us")), "DGO2")

    def test_rate_shipment_grid(self):
        order = self._order(self._partner("base.de"))
        res = self.carrier.delivengo_rate_shipment(order)
        self.assertTrue(res["success"])
        self.assertEqual(res["price"], 6.46)
        order = self._order(self._partner("base.us"), qty=5)
        res = self.carrier.delivengo_rate_shipment(order)
        self.assertEqual(res["price"], 34.90)

    def test_rate_shipment_refuses_france_and_heavy_parcels(self):
        res = self.carrier.delivengo_rate_shipment(
            self._order(self._partner("base.fr"))
        )
        self.assertFalse(res["success"])
        self.assertIn("abroad", res["error_message"])
        res = self.carrier.delivengo_rate_shipment(
            self._order(self._partner("base.de"), qty=20)  # 3 kg
        )
        self.assertFalse(res["success"])
        self.assertIn("2", res["error_message"])

    def test_rate_shipment_base_on_rule_keeps_weight_limit(self):
        self.carrier.write(
            {
                "laposte_pricing_method": "base_on_rule",
                "price_rule_ids": [
                    (
                        0,
                        0,
                        {
                            "variable": "weight",
                            "operator": ">=",
                            "max_value": 0.0,
                            "list_base_price": 9.0,
                        },
                    )
                ],
            }
        )
        res = self.carrier.delivengo_rate_shipment(
            self._order(self._partner("base.de"))
        )
        self.assertEqual(res["price"], 9.0)
        res = self.carrier.delivengo_rate_shipment(
            self._order(self._partner("base.de"), qty=20)
        )
        self.assertFalse(res["success"])

    # ------------------------------------------------------------------
    # payload
    # ------------------------------------------------------------------
    def test_payload_inside_eu_has_no_customs(self):
        picking = self._delivery(self._partner("base.de", zip="10115", city="Berlin"))
        payload = self.carrier._delivengo_build_payload(picking)
        pli = payload["data"]["plis"][0]
        self.assertEqual(payload["data"]["id_support"], 33)
        self.assertEqual(pli["poids"], 150)
        self.assertEqual(pli["expediteur_telephone"], "0612345678")
        self.assertEqual(pli["expediteur"]["code_postal_commune"], "75016 Paris")
        self.assertEqual(pli["destinataire"]["code_pays"], "DE")
        self.assertEqual(pli["destinataire"]["code_postal_commune"], "10115 Berlin")
        self.assertNotIn("code_etat", pli["destinataire"])
        self.assertNotIn("documents_douaniers", pli)

    def test_payload_outside_eu_has_customs(self):
        picking = self._delivery(
            self._partner("base.us", state_id=self._state("CA").id), qty=2
        )
        payload = self.carrier._delivengo_build_payload(picking)
        pli = payload["data"]["plis"][0]
        self.assertEqual(pli["destinataire"]["code_etat"], "CA")
        customs = pli["documents_douaniers"]
        self.assertEqual(customs["envoi_nature"], [6])
        self.assertEqual(customs["num_facture"], picking.sale_id.name)
        self.assertEqual(customs["frais_port"], "34.90")
        self.assertEqual(len(customs["articles"]), 1)
        article = customs["articles"][0]
        self.assertEqual(article["num_tarifaire"], "610910")
        self.assertEqual(article["quantite"], 2)
        self.assertEqual(article["poids"], 0.3)
        self.assertEqual(article["valeur"], 64.0)
        self.assertEqual(article["pays_origine"], "FR")

    def test_customs_requires_hs_code(self):
        self.boxed.hs_code = False
        picking = self._delivery(
            self._partner("base.us", state_id=self._state("CA").id)
        )
        with self.assertRaises(UserError) as ctx:
            self.carrier._delivengo_build_payload(picking)
        self.assertIn("HS code", str(ctx.exception))

    def test_check_shipment_requires_contact_and_mobile(self):
        picking = self._delivery(self._partner("base.de", email=False, phone=False))
        with self.assertRaises(UserError) as ctx:
            self.carrier._delivengo_build_payload(picking)
        self.assertIn("phone number or an email", str(ctx.exception))

        picking = self._delivery(self._partner("base.de"))
        self.carrier.delivengo_sender_mobile = "01 23 45 67 89"
        with self.assertRaises(UserError) as ctx:
            self.carrier._delivengo_build_payload(picking)
        self.assertIn("mobile", str(ctx.exception))

    def test_check_shipment_requires_us_state(self):
        picking = self._delivery(self._partner("base.us"))
        with self.assertRaises(UserError) as ctx:
            self.carrier._delivengo_build_payload(picking)
        self.assertIn("state", str(ctx.exception))

    # ------------------------------------------------------------------
    # HTTP flow (mocked)
    # ------------------------------------------------------------------
    def test_send_shipping_mocked(self):
        picking = self._delivery(self._partner("base.de", zip="10115", city="Berlin"))
        response = FakeResponse(
            201,
            {
                "data": {
                    "id": 5306429,
                    "plis": [{"id": "11450170", "numero": "LD037508768FR"}],
                    "documents_supports": base64.b64encode(b"%PDF-label").decode(),
                    "documents_douaniers": None,
                    "factures": None,
                }
            },
        )
        with patch(DELIVENGO_MODULE + ".requests.request") as request:
            request.return_value = response
            result = self.carrier.delivengo_send_shipping(picking)
        args, kwargs = request.call_args
        self.assertEqual(args[0], "POST")
        self.assertTrue(args[1].endswith("/envois"))
        self.assertEqual(
            kwargs["headers"]["API-Authorization"], "Oono8eez7eez9NRZ3xaeFaeh8hee3u"
        )
        self.assertEqual(kwargs["headers"]["Accept"], "application/pdf")
        self.assertEqual(kwargs["params"]["support"], "32")
        self.assertEqual(kwargs["json"]["data"]["plis"][0]["poids"], 150)
        self.assertEqual(result[0]["tracking_number"], "LD037508768FR")
        self.assertEqual(result[0]["exact_price"], 6.46)
        self.assertEqual(picking.delivengo_shipment_id, "5306429")
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", "stock.picking"), ("res_id", "=", picking.id)]
        )
        self.assertEqual(len(attachment), 1)
        self.assertTrue(attachment.name.endswith("_label.pdf"))

    def test_send_shipping_surfaces_validation_errors_masked(self):
        picking = self._delivery(self._partner("base.de", zip="10115", city="Berlin"))
        response = FakeResponse(
            400,
            {
                "error": {
                    "code": 400,
                    "message": "Bad Request",
                    "description": "Erreur lors de la création de l'envoi.",
                    "details": {
                        "data": {
                            "plis": {
                                "1": {
                                    "destinataire": {
                                        "nom": {
                                            "forbiddenWord": "'UNKNOWN' ne peut pas "
                                            "être utilisé. key "
                                            "Oono8eez7eez9NRZ3xaeFaeh8hee3u"
                                        }
                                    }
                                }
                            }
                        }
                    },
                }
            },
        )
        with patch(DELIVENGO_MODULE + ".requests.request") as request:
            request.return_value = response
            with self.assertRaises(UserError) as ctx:
                self.carrier.delivengo_send_shipping(picking)
        message = str(ctx.exception)
        self.assertIn("HTTP 400", message)
        self.assertIn("data.plis.1.destinataire.nom.forbiddenWord", message)
        self.assertNotIn("Oono8eez7eez9NRZ3xaeFaeh8hee3u", message)

    def test_cancel_shipment_deletes_on_delivengo(self):
        picking = self._delivery(self._partner("base.de"))
        picking.write(
            {"delivengo_shipment_id": "5306429", "carrier_tracking_ref": "LD1FR"}
        )
        with patch(DELIVENGO_MODULE + ".requests.request") as request:
            request.return_value = FakeResponse(200, [])
            self.carrier.delivengo_cancel_shipment(picking)
        args, _ = request.call_args
        self.assertEqual(args[0], "DELETE")
        self.assertTrue(args[1].endswith("/envois/5306429"))
        self.assertFalse(picking.delivengo_shipment_id)
        self.assertFalse(picking.carrier_tracking_ref)

    def test_test_connection(self):
        with patch(DELIVENGO_MODULE + ".requests.request") as request:
            request.return_value = FakeResponse(
                200, {"data": {"id": "1", "email": "ops@example.com"}}
            )
            action = self.carrier.action_delivengo_test_connection()
        self.assertIn("ops@example.com", action["params"]["message"])
        with patch(DELIVENGO_MODULE + ".requests.request") as request:
            request.return_value = FakeResponse(401, {"error": {"code": 401}})
            with self.assertRaises(UserError):
                self.carrier.action_delivengo_test_connection()

    def test_request_requires_api_key(self):
        self.carrier.delivengo_api_key = False
        with self.assertRaises(UserError) as ctx:
            self.carrier.action_delivengo_test_connection()
        self.assertIn("API key", str(ctx.exception))

    def test_tracking_link(self):
        picking = self.env["stock.picking"].new(
            {"carrier_tracking_ref": "LD037508768FR"}
        )
        self.assertIn(
            "LD037508768FR", self.carrier.delivengo_get_tracking_link(picking)
        )
