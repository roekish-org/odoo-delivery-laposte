# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "delivery.laposte.pickup.mixin"]

    def _action_confirm(self):
        res = super()._action_confirm()
        # Carry the chosen pickup point onto the delivery orders created at
        # confirmation, unless one was already set on the picking.
        for order in self:
            if not order.laposte_pickup_point_code:
                continue
            pickings = order.picking_ids.filtered(
                lambda p: p.laposte_is_pickup and not p.laposte_pickup_point_code
            )
            pickings.write(
                {
                    "laposte_pickup_point_code": order.laposte_pickup_point_code,
                    "laposte_pickup_point_name": order.laposte_pickup_point_name,
                    "laposte_pickup_point_street": (order.laposte_pickup_point_street),
                    "laposte_pickup_point_zip": order.laposte_pickup_point_zip,
                    "laposte_pickup_point_city": order.laposte_pickup_point_city,
                }
            )
        return res
