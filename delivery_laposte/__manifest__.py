# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Delivery Carrier La Poste / Colissimo",
    "version": "19.0.1.0.0",
    "summary": "Rate, ship and track parcels with La Poste / Colissimo",
    "author": "ROEKISH",
    "maintainers": ["alexis2m"],
    "website": "https://github.com/Roekish-org",
    "category": "Inventory/Delivery",
    "license": "AGPL-3",
    "depends": [
        "stock_delivery",
    ],
    "post_init_hook": "post_init_hook",
    # roulier (labels) and zeep (pickup search) are imported lazily and fail
    # closed with a clear message when missing, so they are NOT declared as
    # hard external_dependencies: the module stays installable and light.
    "data": [
        "security/delivery_laposte_security.xml",
        "security/ir.model.access.csv",
        "views/delivery_carrier_views.xml",
        "views/stock_picking_views.xml",
        "views/sale_order_views.xml",
        "wizards/pickup_wizard_views.xml",
    ],
    "demo": [
        "demo/delivery_laposte_demo.xml",
    ],
    "installable": True,
}
