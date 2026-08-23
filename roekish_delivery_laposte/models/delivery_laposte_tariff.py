# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models

# Colissimo pricing zones, mirroring La Poste's published "affranchissement"
# grids: France, the two overseas priority zones, EU+Switzerland, the United
# Kingdom (priced apart since Brexit) and the two international zones.
LAPOSTE_ZONES = [
    ("FR", "France (metropolitan, Monaco, Andorra)"),
    ("OM1", "Overseas zone 1"),
    ("OM2", "Overseas zone 2"),
    ("EU", "European Union + Switzerland"),
    ("UK", "United Kingdom"),
    ("INTB", "International zone B"),
    ("INTC", "International zone C"),
]


class DeliveryLaposteTariff(models.Model):
    _name = "delivery.laposte.tariff"
    _description = "La Poste / Colissimo Tariff Grid Line"
    _order = "carrier_id, zone, max_weight"

    carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Carrier",
        required=True,
        ondelete="cascade",
        index=True,
    )
    zone = fields.Selection(
        selection=LAPOSTE_ZONES,
        string="Zone",
        required=True,
    )
    max_weight = fields.Float(
        string="Weight up to (kg)",
        required=True,
        help="This line applies to shipments whose total weight is at or "
        "below this value, for the selected zone.",
    )
    price = fields.Float(
        string="Price",
        required=True,
        help="Delivery price charged to the customer, expressed in the "
        "carrier company currency.",
    )
    currency_id = fields.Many2one(
        related="carrier_id.company_id.currency_id",
        readonly=True,
    )
