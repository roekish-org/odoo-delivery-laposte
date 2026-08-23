# roekish_delivery_laposte: Development & Go-Live Guide

Odoo 19 delivery carrier for **La Poste / Colissimo**: rating (tariff grid or
Odoo rules), Colissimo label generation, parcel tracking and pickup-point
(relay) selection. Owned by **ROEKISH**.

---

## 1. Requirements

- Docker and Docker Compose (v2).
- No local Python/Postgres needed, everything runs in containers.

The stack (`docker-compose.yml`): Postgres 16 + Odoo 19 with `roulier`
(labels) and `zeep` (pickup search) baked into the image (`docker/Dockerfile`).

---

## 2. Quick start

```bash
make init   # build the image + create the demo DB with the module & demo data
make up     # start Odoo  ->  http://localhost:8069   (login: admin / admin)
```

Other targets:

| Command | What it does |
|---|---|
| `make test` | Run the module test suite |
| `make shell` | Open an Odoo shell on the demo DB |
| `make logs` | Follow the Odoo logs |
| `make down` | Stop the stack |
| `make reset` | Drop the demo database (then `make init` to rebuild) |

The demo database is `colissimo` (override with `make init DB=mydb`).

---

## 3. What the demo ships

Four ready-to-use carriers under *Inventory → Configuration → Shipping
Methods*, each with a real, editable Colissimo 2026 grid:

- **Colissimo Domicile**: full zone grid (FR, OM1, OM2, EU+CH, UK, Zone B,
  Zone C).
- **Colissimo Point Retrait**: France relay grid (drives the pickup selector).
- **Colissimo Éco Outre-mer**: overseas economy grid.
- **Colissimo Prêt-à-Envoyer**: prepaid-packaging grid.

Demo grids are indicative public tariffs. Your users **copy a carrier and edit
its grid** with their negotiated contract rates.

---

## 4. Going live with a real Colissimo account

1. Open the carrier (e.g. *Colissimo Domicile*) → **La Poste** tab.
2. **Web service credentials**: enter your Colissimo **contract number** and
   **password** (these fields are readable only by La Poste *Administrators*,
   see §6).
3. Click **Test connection**: it calls the Point Retrait web service with your
   credentials and reports success or a masked error. This is the go-live
   check.
4. Set the **Colissimo product** and **Label format**:
   - Label format is passed straight through to Colissimo's
     `outputPrintingType`. The demo uses `PDF_10x15_300dpi`. If your `roulier`
     version rejects it, switch to a short code (`PDF`, `ZPL`, `DPL`).
5. Set **Integration Level = Get Rate and Create Shipment** so labels generate
   on delivery validation.
6. Make sure your **company address** is complete (street, ZIP, city, country,
   phone). It is the parcel sender.

### Sender/recipient data
Addresses are built from `res.partner` (company for the sender, delivery
contact for the recipient). Ensure phone and full address are filled; La Poste
rejects incomplete addresses.

### Labels & tracking
On delivery validation Odoo calls `roulier.get('laposte_fr', 'get_label', …)`,
attaches the returned label(s) to the transfer, and stores the tracking
number in `carrier_tracking_ref`. The customer tracking link points to
`laposte.fr/outils/suivre-vos-envois`.

> The `roulier` label call and the `zeep` pickup SOAP are the version-sensitive
> external boundaries. Validate them once against your real account (see the
> go-live checklist in §8).

---

## 5. Pricing model

`laposte_rate_shipment` resolves a price in this order:

1. `_laposte_get_live_price(order)`: a fail-closed hook. La Poste exposes no
   live rating API, so it returns `None` by default. Override it to plug a
   real endpoint (e.g. a third-party aggregator) without touching the rest.
2. **Pricing method = Tariff grid** → looks up `(zone, weight)` in the
   carrier's grid. Zone is derived from the destination country
   (`_laposte_get_zone`).
3. **Pricing method = Odoo rules** → falls back to the standard
   `base_on_rule` engine (rules editable on the same tab).

Prices are expressed in the carrier company currency.

Zone → country mapping lives in `models/delivery_carrier.py`
(`FR_COUNTRY_CODES`, `OM1/OM2`, `EU`, `INTB`, …). **Zone B's country list is a
representative subset**. Complete it from La Poste's official zone tables
before finalizing international pricing.

---

## 6. Access rights

A dedicated **La Poste Delivery** privilege (Settings → Users) with two groups:

- **User**: generate labels, track parcels, pick relay points (implies
  *Inventory / User*).
- **Administrator**: configure carriers, credentials and tariff grids
  (implies *User* + *Inventory / Administrator*).

On install, the main administrator (`base.user_admin`) is added to
**Administrator** automatically (via `post_init_hook`) so the module is usable
out of the box. Assign the groups to your other users under *Settings → Users*.

Security notes:
- Credential fields (`laposte_account`, `laposte_password`) are locked to
  **Administrator** at the ORM level, and a plain user reading them gets an
  `AccessError`.
- All carrier/library error messages pass through a secret masker that redacts
  the password value and any `<password>` XML node.
- A global record rule isolates tariff grids per company.

---

## 7. Pickup points (relay)

For relay carriers (product code `A2P`/`BPR`), a **Choose pickup point** button
appears on the **sale order** and the **delivery order**. It opens a wizard
that searches nearby points and lets the user select one.

- With credentials set → live Colissimo Point Retrait SOAP call (`zeep`).
- Without credentials → three clearly-labelled demo points, so the flow is
  testable offline.

A point chosen on the sale order **propagates to the delivery order** on
confirmation, and is sent to Colissimo as `pickupLocationId` on the label.

---

## 8. Go-live checklist

- [ ] `make init && make up`, log in, confirm the four demo carriers load.
- [ ] Enter real credentials on a carrier and click **Test connection**.
- [ ] Replace demo grid lines with your contract tariffs.
- [ ] Complete Zone B country list if you ship there.
- [ ] Generate one real label end-to-end (confirm a delivery with the carrier).
- [ ] Verify the label format string is accepted by your `roulier` version.
- [ ] Test one pickup-point selection with real credentials.

---

## 9. Project layout

```
odoo_dev/
├── docker-compose.yml        # Postgres + Odoo 19 stack
├── docker/                   # Dockerfile (roulier, zeep) + odoo.conf
├── Makefile                  # init / up / test / shell / reset
└── roekish_delivery_laposte/         # the Odoo module
    ├── models/               # carrier, tariff, pickup mixin, sale, picking
    ├── wizards/              # pickup-point search wizard
    ├── views/                # carrier, sale order, picking forms
    ├── security/             # groups, privilege, ACLs, record rule
    ├── demo/                 # real Colissimo 2026 tariff grids
    └── tests/                # rating, zones, pickup, propagation
```

Runtime deps (`roulier`, `zeep`) are imported lazily and are **not** declared
as hard `external_dependencies`: the module installs light and each feature
fails closed with a clear message if its library is missing.

---

## 10. Sandbox & verifying it works

### Colissimo test/sandbox access
- **Labelling (SLS) & Point Retrait**: Colissimo has a sandbox environment, but
  **does not issue public test accounts**. You must open a (free) Colissimo
  Business contract; the credentials you receive work against both sandbox and
  production web services (`ws.colissimo.fr`).
- **Tracking (Suivi API)**: La Poste's developer portal
  (https://developer.laposte.fr/products/suivi/latest) offers a **free
  sandbox** with an instant API key, useful to test parcel tracking.

### What is already verified (no account needed)
- `make test` runs 8 tests: zone mapping, grid rating, rate_shipment,
  demo/offline pickup, sale→delivery pickup propagation, and a **mocked
  label generation** (`test_send_shipping_mocked`) that drives the real
  `send_shipping` code against roulier's response shape and asserts the label
  is attached and the tracking number stored.
- The **pickup web service path is verified against the live Colissimo
  server**: our *Test connection* button reaches `ws.colissimo.fr`, and with
  invalid credentials Colissimo replies `errorCode 201 – Identifiant / mot de
  passe invalide`, which we surface as an error (Colissimo returns auth
  failures in the response body, not as a SOAP fault, so this is checked
  explicitly).

### What still needs a real account
- Generating an actual label end-to-end (valid `roulier` `get_label` call).
- Listing real pickup points (valid Point Retrait credentials).

### How to check a real account
1. Enter the credentials on a carrier → **Test connection**. Success means the
   account authenticates against Colissimo; an error shows the exact Colissimo
   code/message.
2. Confirm a delivery with the carrier to generate one real label, and verify
   the tracking number and the attached label PDF/ZPL on the transfer.
