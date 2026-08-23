# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class LapostePickupMixin(models.AbstractModel):
    """Pickup-point holder shared by sale.order and stock.picking."""

    _name = "delivery.laposte.pickup.mixin"
    _description = "La Poste pickup point holder"

    laposte_pickup_point_code = fields.Char(string="Pickup point ID", copy=False)
    laposte_pickup_point_name = fields.Char(string="Pickup point", copy=False)
    laposte_pickup_point_street = fields.Char(copy=False)
    laposte_pickup_point_zip = fields.Char(copy=False)
    laposte_pickup_point_city = fields.Char(copy=False)
    laposte_is_pickup = fields.Boolean(
        compute="_compute_laposte_is_pickup",
        help="The selected carrier delivers to a La Poste pickup point.",
    )

    @api.depends("carrier_id")
    def _compute_laposte_is_pickup(self):
        for rec in self:
            carrier = rec.carrier_id
            rec.laposte_is_pickup = (
                carrier.delivery_type == "laposte"
                and carrier.laposte_product_code in ("BPR", "A2P")
            )

    def action_laposte_choose_pickup_point(self):
        self.ensure_one()
        default_key = (
            "default_picking_id" if self._name == "stock.picking" else "default_sale_id"
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Choose a pickup point"),
            "res_model": "delivery.laposte.pickup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {default_key: self.id},
        }
