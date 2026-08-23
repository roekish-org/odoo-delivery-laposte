# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestDeliveryLaposte(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {"name": "Colissimo", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "La Poste Test",
                "delivery_type": "laposte",
                "product_id": cls.product.id,
                "laposte_pricing_method": "grid",
            }
        )
        cls.relay_carrier = cls.env["delivery.carrier"].create(
            {
                "name": "La Poste Relay Test",
                "delivery_type": "laposte",
                "product_id": cls.product.id,
                "laposte_product_code": "A2P",
                "laposte_pricing_method": "grid",
            }
        )
        cls.env["delivery.laposte.tariff"].create(
            [
                {
                    "carrier_id": cls.carrier.id,
                    "zone": "FR",
                    "max_weight": 1.0,
                    "price": 6.55,
                },
                {
                    "carrier_id": cls.carrier.id,
                    "zone": "FR",
                    "max_weight": 5.0,
                    "price": 14.10,
                },
                {
                    "carrier_id": cls.carrier.id,
                    "zone": "EU",
                    "max_weight": 2.0,
                    "price": 12.0,
                },
            ]
        )

    def test_zone_mapping(self):
        get_zone = self.carrier._laposte_get_zone
        self.assertEqual(get_zone(self.env.ref("base.fr")), "FR")
        self.assertEqual(get_zone(self.env.ref("base.de")), "EU")
        self.assertEqual(get_zone(self.env.ref("base.uk")), "UK")
        self.assertEqual(get_zone(self.env.ref("base.re")), "OM1")
        self.assertEqual(get_zone(self.env.ref("base.pf")), "OM2")
        self.assertEqual(get_zone(self.env.ref("base.ma")), "INTB")
        self.assertEqual(get_zone(self.env.ref("base.us")), "INTC")
        self.assertEqual(get_zone(self.env["res.country"]), "FR")

    def test_demo_pickup_points(self):
        # No credentials -> demonstrative points, so the flow stays testable.
        points = self.carrier._laposte_search_pickup_points("75001", "Paris", "FR", 1.0)
        self.assertEqual(len(points), 3)
        self.assertEqual(points[0]["zip"], "75001")
        self.assertTrue(all(p.get("code") for p in points))

    def test_grid_rate_bracket(self):
        # 0.8 kg falls in the 1 kg bracket.
        self.assertEqual(self.carrier._laposte_grid_rate("FR", 0.8), 6.55)
        # 3 kg falls in the 5 kg bracket.
        self.assertEqual(self.carrier._laposte_grid_rate("FR", 3.0), 14.10)
        # Above the last bracket: no match.
        self.assertIsNone(self.carrier._laposte_grid_rate("FR", 40.0))
        # No grid for this zone.
        self.assertIsNone(self.carrier._laposte_grid_rate("INTC", 1.0))

    def test_rate_shipment_success(self):
        partner = self.env["res.partner"].create(
            {"name": "Client", "country_id": self.env.ref("base.fr").id}
        )
        order = self.env["sale.order"].create({"partner_id": partner.id})
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 1,
            }
        )
        res = self.carrier.laposte_rate_shipment(order)
        self.assertTrue(res["success"])
        self.assertGreater(res["price"], 0.0)

    def test_is_pickup_compute(self):
        partner = self.env["res.partner"].create(
            {"name": "C", "country_id": self.env.ref("base.fr").id}
        )
        dom_order = self.env["sale.order"].create(
            {"partner_id": partner.id, "carrier_id": self.carrier.id}
        )
        relay_order = self.env["sale.order"].create(
            {"partner_id": partner.id, "carrier_id": self.relay_carrier.id}
        )
        self.assertFalse(dom_order.laposte_is_pickup)  # DOM
        self.assertTrue(relay_order.laposte_is_pickup)  # A2P

    def test_pickup_wizard_from_sale(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Relay Client",
                "zip": "69001",
                "city": "Lyon",
                "country_id": self.env.ref("base.fr").id,
            }
        )
        order = self.env["sale.order"].create(
            {"partner_id": partner.id, "carrier_id": self.relay_carrier.id}
        )
        wizard = (
            self.env["delivery.laposte.pickup.wizard"]
            .with_context(default_sale_id=order.id)
            .create({"zip": "69001"})
        )
        self.assertEqual(wizard.carrier_id, self.relay_carrier)
        wizard.action_search()
        self.assertTrue(wizard.line_ids)
        wizard.line_ids[0].action_select()
        self.assertTrue(order.laposte_pickup_point_code)
        self.assertEqual(order.laposte_pickup_point_city, "Lyon")

    def test_send_shipping_mocked(self):
        # Prove label handling end to end against roulier's normalized output
        # (shape taken from the recorded Colissimo WS response), no account.
        partner = self.env["res.partner"].create(
            {
                "name": "Ship To",
                "street": "27 Rue Henri Rolland",
                "zip": "69100",
                "city": "Villeurbanne",
                "phone": "+33400000000",
                "country_id": self.env.ref("base.fr").id,
            }
        )
        product = self.env["product.product"].create(
            {"name": "Boxed", "is_storable": True, "weight": 1.2}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "carrier_id": self.carrier.id,
                "order_line": [
                    (0, 0, {"product_id": product.id, "product_uom_qty": 1})
                ],
            }
        )
        order.action_confirm()
        picking = order.picking_ids[:1]
        self.assertTrue(picking, "a delivery order should have been created")

        fake_response = {
            "parcels": [
                {
                    "tracking": {"number": "6A21539158956"},
                    "label": {
                        "data": base64.b64encode(b"^XA...ZPL...^XZ").decode(),
                        "type": "zpl",
                        "name": "label",
                    },
                }
            ]
        }
        with patch(
            "odoo.addons.roekish_delivery_laposte.models.delivery_carrier.roulier"
        ) as roulier_mock:
            roulier_mock.get.return_value = fake_response
            result = self.carrier.laposte_send_shipping(picking)

        self.assertEqual(result[0]["tracking_number"], "6A21539158956")
        self.assertGreater(result[0]["exact_price"], 0.0)
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", "stock.picking"), ("res_id", "=", picking.id)]
        )
        self.assertTrue(attachment, "the label should be attached to the picking")

    def test_rate_shipment_no_bracket(self):
        partner = self.env["res.partner"].create(
            {"name": "Client US", "country_id": self.env.ref("base.us").id}
        )
        order = self.env["sale.order"].create({"partner_id": partner.id})
        res = self.carrier.laposte_rate_shipment(order)
        self.assertFalse(res["success"])
        self.assertTrue(res["error_message"])
