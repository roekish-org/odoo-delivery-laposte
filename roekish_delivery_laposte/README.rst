=====================================
Delivery Carrier La Poste / Colissimo
=====================================

Rate, ship and track parcels with **La Poste / Colissimo** from Odoo 19.

This module plugs into Odoo's native delivery framework (``delivery`` /
``stock_delivery``) and adds a ``laposte`` carrier type that can:

* **Rate** a shipment (get the delivery cost) using either a La Poste
  tariff grid (weight x destination zone) or Odoo's rule-based pricing.
* **Ship**: generate a Colissimo label and store the tracking number on the
  delivery order, using the `roulier <https://pypi.org/project/roulier/>`_
  library.
* **Track**: build the Colissimo tracking link for the customer.

Pricing
=======

La Poste / Colissimo does **not** expose a live rating API, so prices come
from data you control:

* **La Poste tariff grid** *(default)*: define weight brackets per zone
  (France, Overseas / DROM-COM, EU, Rest of the world) directly on the
  carrier.
* **Odoo pricing rules**: reuse the standard rule-based engine
  (``base_on_rule``).

``delivery.carrier._laposte_get_live_price`` is a documented, fail-closed
extension point: override it to plug a real rating endpoint (for example a
third-party aggregator) without touching the rest of the flow.

Requirements
============

* Python ``roulier`` for label generation (``pip install roulier``).
* Python ``zeep`` for live pickup-point search (``pip install zeep``).
* A Colissimo contract (login + password) configured on the carrier.

Rating works with no external library; both libraries are optional and
fail closed with a clear message when a feature that needs them is used.

Configuration
=============

#. Go to *Inventory > Configuration > Shipping Methods*.
#. Create a shipping method with provider **La Poste / Colissimo**.
#. Fill the contract number, password, Colissimo product and label format.
#. Choose a pricing method and fill the tariff grid (or the pricing rules).
#. Set *Integration Level* to **Get Rate and Create Shipment** to enable
   label generation.

Credits
=======

Authors
-------

* ROEKISH

Contributors
------------

* Alexis Maison (`alexis2m <https://github.com/alexis2m>`_), ROEKISH

This module reuses concepts from the OCA ``delivery_roulier_laposte_fr``
module (Akretion / OCA, AGPL-3), rebuilt on the native Odoo 19 delivery
framework.

License
=======

AGPL-3. See ``LICENSE`` / http://www.gnu.org/licenses/agpl.html.
