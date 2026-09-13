# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "delivery.laposte.pickup.mixin"]

    delivengo_shipment_id = fields.Char(
        string="Delivengo shipment ID",
        copy=False,
        readonly=True,
        help="Identifier of the shipment (envoi) on MyDelivengo, used to cancel it.",
    )
