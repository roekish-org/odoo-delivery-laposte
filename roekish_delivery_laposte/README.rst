=================================================
Delivery Carrier La Poste / Colissimo / Delivengo
=================================================

Rate, ship and track parcels with **La Poste** from Odoo 19: **Colissimo** for
parcels and **Delivengo** for international small goods up to 2 kg.

This module plugs into Odoo's native delivery framework (``delivery`` /
``stock_delivery``) and adds a ``laposte`` carrier type that can:

* **Rate** a shipment using a Colissimo tariff grid (weight by zone) or Odoo's
  rule-based pricing.
* **Ship**: generate a Colissimo label with the
  `roulier <https://pypi.org/project/roulier/>`_ library and store the tracking
  number on the delivery order. Zero-weight parcels and incomplete addresses
  are rejected with a clear message before anything is sent.
* **Track**: expose the Colissimo tracking link to the customer.
* **Pickup points**: search nearby relay points through the Colissimo
  *Point Retrait* web service and select one on the sale order or the delivery
  order. A point chosen on the order is carried onto the delivery at
  confirmation and sent to Colissimo on the label.
* **Test the connection** from the carrier form: Colissimo returns its error
  codes in the response body, and the check surfaces them (for example
  ``201``, invalid credentials).

It also adds a ``delivengo`` carrier type for **Delivengo** (La Poste's
international offer for goods up to 2 kg, Delivengo easy or Delivengo Profil):

* **Rate** on the two Delivengo zones (European Union + United Kingdom, rest
  of the world) or with Odoo rules, refusing domestic destinations and parcels
  above 2 kg.
* **Ship** through the MyDelivengo REST API (version 2.5): the label and, for
  destinations outside the EU customs union, the **CN22/CN23 customs
  documents** built from the delivery lines (HS code, country of origin,
  weight, value) are attached to the delivery order with the tracking number.
* **Cancel** the shipment on MyDelivengo from the delivery order.
* **Test the connection** with the API key. No extra Python library is needed.

Pricing
=======

La Poste / Colissimo does not expose a live rating API, so prices come from
data you control:

* **Tariff grid** *(default)*: weight brackets per zone, edited directly on
  the carrier. Zones: metropolitan France (with Monaco and Andorra), Overseas
  zones 1 and 2, European Union with Switzerland, United Kingdom, and
  international zones B and C.
* **Odoo pricing rules**: the standard ``base_on_rule`` engine.

Every quote also reports the announced **delivery time** in working days
(``delay_min`` / ``delay_max`` in the ``rate_shipment`` result, shown in the
shipping wizard). Set it on the carrier and override it per zone on the
tariff grid, then compare carriers on cost and speed.

``delivery.carrier._laposte_get_live_price`` is a fail-closed extension point.
Override it to plug a rating endpoint (for example a third-party aggregator)
without touching the rest of the flow.

Demo data ships four carriers with the public Colissimo 2026 tariffs (Home,
Pickup Point, Overseas Economy, Prepaid) and a *Delivengo easy* carrier with
the public Delivengo easy grid. Replace them with your negotiated rates.

Requirements
============

* Python ``roulier`` for Colissimo label generation.
* Python ``zeep`` for live pickup-point search.
* A Colissimo contract (contract number and password) set on the carrier.
* For Delivengo: a MyDelivengo account and its API key (*Mon compte > Clé
  API*). The API is called with ``requests``, shipped with Odoo.

Rating works with no external library. Both libraries are optional, imported
on demand, and each feature fails closed with a clear message if its library
is missing.

Deploy the module on the ``addons_path`` (Odoo.sh or On-Premise). The
*Apps > Import Module* zip upload is data-only: it never loads Python models,
so it fails on the first model reference. On Odoo Online (SaaS) Python
libraries cannot be installed either, so labels and pickup search need Odoo.sh
or On-Premise.

Configuration
=============

#. Go to *Inventory > Configuration > Shipping Methods*.
#. Create a shipping method with provider **La Poste / Colissimo**.
#. Fill the contract number, password, Colissimo product and label format,
   then click **Test connection**.
#. Choose a pricing method and fill the tariff grid (or the pricing rules).
#. Set *Integration Level* to **Get Rate and Create Shipment** to generate
   labels on delivery validation.
#. Make sure the company address is complete: it is the parcel sender.

For Delivengo, create a shipping method with provider **La Poste /
Delivengo**, paste the API key, choose the Delivengo product (Suivi,
Economique, Prioritaire), the label format and the nature of shipment, set the
sender's French mobile number, then click **Test connection**. Fill the HS code
and the weight of the products you export: they feed the customs declaration.

Access rights
=============

A **La Poste Delivery** privilege provides two groups: *User* (ship, track,
pick relay points) and *Administrator* (configure carriers, credentials and
grids). Credentials and the Delivengo API key are readable by administrators
only, secrets are masked in error messages, and a record rule isolates tariff
grids per company. Sales
users can pick a relay point on quotations. The main administrator is added to
the *Administrator* group at install.

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
