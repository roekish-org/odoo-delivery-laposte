# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

CARRIER_MODULE = "odoo.addons.roekish_delivery_laposte.models.delivery_carrier"


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

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _create_order(self, carrier, weight=1.2, partner_vals=None):
        """A confirmable sale order with one storable line."""
        vals = {
            "name": "Ship To",
            "street": "27 Rue Henri Rolland",
            "zip": "69100",
            "city": "Villeurbanne",
            "phone": "+33400000000",
            "country_id": self.env.ref("base.fr").id,
        }
        vals.update(partner_vals or {})
        partner = self.env["res.partner"].create(vals)
        product = self.env["product.product"].create(
            {"name": "Boxed", "is_storable": True, "weight": weight}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "carrier_id": carrier.id,
                "order_line": [
                    (0, 0, {"product_id": product.id, "product_uom_qty": 1})
                ],
            }
        )

    def _create_delivery(self, carrier, **kwargs):
        order = self._create_order(carrier, **kwargs)
        order.action_confirm()
        picking = order.picking_ids[:1]
        self.assertTrue(picking, "a delivery order should have been created")
        return picking

    # ------------------------------------------------------------------
    # tracking, cancellation, secrets
    # ------------------------------------------------------------------
    def test_tracking_link_uses_first_reference(self):
        picking = self.env["stock.picking"].new(
            {"carrier_tracking_ref": "6A111, 6A222"}
        )
        link = self.carrier.laposte_get_tracking_link(picking)
        self.assertIn("6A111", link)
        self.assertNotIn("6A222", link)

    def test_cancel_shipment_clears_reference(self):
        picking = self._create_delivery(self.carrier)
        picking.carrier_tracking_ref = "6A111"
        self.carrier.laposte_cancel_shipment(picking)
        self.assertFalse(picking.carrier_tracking_ref)

    def test_mask_secrets(self):
        self.carrier.sudo().laposte_password = "S3cret!"
        masked = self.carrier._laposte_mask_secrets(
            "pw=S3cret! <password>S3cret!</password>"
        )
        self.assertNotIn("S3cret!", masked)
        self.assertIn("<password>****</password>", masked)

    def test_test_connection_requires_credentials(self):
        with self.assertRaises(UserError):
            self.carrier.action_laposte_test_connection()

    # ------------------------------------------------------------------
    # pricing: Odoo rules path
    # ------------------------------------------------------------------
    def test_rate_shipment_base_on_rule(self):
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "La Poste Rules",
                "delivery_type": "laposte",
                "product_id": self.product.id,
                "laposte_pricing_method": "base_on_rule",
                "price_rule_ids": [
                    (
                        0,
                        0,
                        {
                            "variable": "weight",
                            "operator": ">=",
                            "max_value": 0.0,
                            "list_base_price": 7.5,
                        },
                    )
                ],
            }
        )
        order = self._create_order(carrier)
        res = carrier.laposte_rate_shipment(order)
        self.assertTrue(res["success"])
        self.assertEqual(res["price"], 7.5)

    # ------------------------------------------------------------------
    # pickup points
    # ------------------------------------------------------------------
    def test_pickup_propagates_to_delivery_on_confirm(self):
        order = self._create_order(self.relay_carrier)
        order.write(
            {
                "laposte_pickup_point_code": "PT1",
                "laposte_pickup_point_name": "Relais Lyon",
                "laposte_pickup_point_city": "Lyon",
            }
        )
        order.action_confirm()
        picking = order.picking_ids[:1]
        self.assertEqual(picking.laposte_pickup_point_code, "PT1")
        self.assertEqual(picking.laposte_pickup_point_name, "Relais Lyon")
        payload = self.relay_carrier._laposte_build_payload(picking)
        self.assertEqual(payload["service"]["pickupLocationId"], "PT1")

    def test_pickup_ws_as_plain_user_and_error_code(self):
        # A La Poste *user* (not administrator) must be able to search relay
        # points even though the credential fields are manager-only, and a
        # Colissimo errorCode in the body must surface as an error.
        user = self.env["res.users"].create(
            {
                "name": "Ops",
                "login": "ops_laposte",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref(
                                "roekish_delivery_laposte.group_laposte_user"
                            ).id
                        ],
                    )
                ],
            }
        )
        self.carrier.sudo().write(
            {"laposte_account": "000000", "laposte_password": "pw"}
        )
        carrier = self.carrier.with_user(user)
        with patch(CARRIER_MODULE + ".ZeepClient") as zeep_client:
            call = zeep_client.return_value.service.findRDVPointRetraitAcheminement
            call.return_value = SimpleNamespace(
                errorCode=201,
                errorMessage="Identifiant / mot de passe invalide",
                listePointRetraitAcheminement=[],
            )
            with self.assertRaises(UserError) as ctx:
                carrier._laposte_search_pickup_points("75001", "Paris", "FR", 1.0)
            self.assertIn("201", str(ctx.exception))

            call.return_value = SimpleNamespace(
                errorCode=0,
                errorMessage="",
                listePointRetraitAcheminement=[
                    SimpleNamespace(
                        identifiant="X1",
                        nom="Relais",
                        adresse1="1 rue Test",
                        codePostal="69001",
                        localite="Lyon",
                        distanceEnMetre=120,
                    )
                ],
            )
            points = carrier._laposte_search_pickup_points("69001", "Lyon", "FR", 1.0)
        self.assertEqual(points[0]["code"], "X1")
        self.assertEqual(points[0]["distance"], 120.0)

    # ------------------------------------------------------------------
    # fail-closed guards
    # ------------------------------------------------------------------
    def test_send_shipping_without_roulier_fails_closed(self):
        picking = self._create_delivery(self.carrier)
        with patch(CARRIER_MODULE + ".roulier", None):
            with self.assertRaises(UserError) as ctx:
                self.carrier.laposte_send_shipping(picking)
        self.assertIn("roulier", str(ctx.exception))

    def test_check_shipment_rejects_zero_weight(self):
        picking = self._create_delivery(self.carrier, weight=0.0)
        with self.assertRaises(UserError) as ctx:
            self.carrier._laposte_check_shipment(picking)
        self.assertIn("weight", str(ctx.exception))

    def test_check_shipment_rejects_incomplete_address(self):
        picking = self._create_delivery(
            self.carrier, partner_vals={"zip": False, "city": False}
        )
        with self.assertRaises(UserError) as ctx:
            self.carrier._laposte_check_shipment(picking)
        self.assertIn("incomplete", str(ctx.exception))

    def test_payload_falls_back_to_env_company(self):
        # A shared carrier (no company) must still send a sender address.
        self.carrier.company_id = False
        picking = self._create_delivery(self.carrier)
        payload = self.carrier._laposte_build_payload(picking)
        self.assertEqual(payload["service"]["commercialName"], self.env.company.name)
        self.assertTrue(payload["from_address"]["name"])

    def test_rate_shipment_no_bracket(self):
        partner = self.env["res.partner"].create(
            {"name": "Client US", "country_id": self.env.ref("base.us").id}
        )
        order = self.env["sale.order"].create({"partner_id": partner.id})
        res = self.carrier.laposte_rate_shipment(order)
        self.assertFalse(res["success"])
        self.assertTrue(res["error_message"])
