# roekish_delivery_laposte: Development & Go-Live Guide

Odoo 19 delivery carrier for **La Poste**: Colissimo (rating, labels,
tracking, pickup points) and **Delivengo** (international small goods up to
2 kg, labels with CN22/CN23 customs documents through the MyDelivengo REST
API). Owned by **ROEKISH**.

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

Five ready-to-use carriers under *Inventory → Configuration → Shipping
Methods*, each with a real, editable grid:

- **Colissimo Domicile**: full zone grid (FR, OM1, OM2, EU+CH, UK, Zone B,
  Zone C).
- **Colissimo Point Retrait**: France relay grid (drives the pickup selector).
- **Colissimo Éco Outre-mer**: overseas economy grid.
- **Colissimo Prêt-à-Envoyer**: prepaid-packaging grid.
- **Delivengo easy**: the public Delivengo easy grid, two zones (EU + UK,
  rest of the world) and four brackets (250 g, 500 g, 1 kg, 2 kg).

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

## 4b. Going live with a Delivengo account

Delivengo is a separate La Poste service with its own account (Delivengo easy
without contract, or Delivengo Profil with a contract) and its own REST API.
Both account types use the same endpoints and the same API key mechanism.

1. Create a shipping method with provider **La Poste / Delivengo**, or copy
   the demo *Delivengo easy* carrier.
2. **Delivengo** tab → paste the **API key** from MyDelivengo (*Mon compte >
   Clé API*). The field is readable by La Poste *Administrators* only.
3. Click **Test connection**: it reads the account owner
   (`GET /utilisateurs/0`) and reports the account email or the exact API
   error.
4. Choose the **Delivengo product** (support) activated on your account:
   Suivi (33), Economique (36) or Prioritaire (37), and the label format
   (PDF 10x15, PDF A4 sheet, ZPL 203 or 300 dpi).
5. Set the **sender mobile phone**: Delivengo requires a French mobile number
   on the sender (+336, +337, 06 or 07). It defaults to the company phone.
6. Set **Integration Level = Get Rate and Create Shipment**.

### What the label call does
On delivery validation Odoo sends `POST /envois` (API 2.5) with one *pli* per
picking: sender (company), recipient, weight in grams, reference (sale order)
and, when the destination is outside the EU customs union, a
`documents_douaniers` block built from the delivery lines. The response carries
the tracking number (`plis[].numero`), the label (`documents_supports`) and the
customs documents (`documents_douaniers`, `factures`), all attached to the
transfer. The MyDelivengo shipment id is stored on the picking
(`delivengo_shipment_id`) so that cancelling the shipment in Odoo issues
`DELETE /envois/{id}` on MyDelivengo.

### Customs data (CN22 / CN23)
For each non-service product on the delivery, Delivengo needs:

- an **HS code** of 6 to 10 digits (`product.hs_code`, Inventory tab),
- a **weight** (`product.weight`),
- a **country of origin** (`product.country_of_origin`, defaults to the company
  country),
- the value (sale line unit price after discount, or the list price).

Shipment nature (sale of goods, sample, gift, ...) is set on the carrier. The
invoice number is the posted customer invoice of the sale order, or the sale
order name. The postage comes from the tariff grid (Delivengo requires a value
above zero for zone 2). Any missing data raises a clear error before the call.

Constraints enforced before the call: destination abroad (France, Monaco and
overseas territories are refused, use Colissimo), weight at most 2 kg, complete
address, phone or email on the recipient, state code on US addresses, French
mobile on the sender, company located in France.

Delivengo rate-limits the API at 15 requests per 5 seconds; a 429 answer is
surfaced as a retry message. Delivengo also rejects non-latin characters in
recipient addresses and a list of forbidden words in names; both come back as
`400` with a detailed message that the module flattens into the error.

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

`delivengo_rate_shipment` (`models/delivery_carrier_delivengo.py`) first
refuses destinations Delivengo does not serve and parcels above 2 kg, then
applies the same pricing method: grid on the Delivengo zones (`DGO1` = EU +
UK, `DGO2` = rest of the world, Switzerland included) or Odoo rules. Delivengo
Profil contracts may be priced on finer zones: use Odoo rules, or one carrier
per country group with the `Countries` restriction of the carrier.

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

- [ ] `make init && make up`, log in, confirm the five demo carriers load.
- [ ] Enter real credentials on a carrier and click **Test connection**.
- [ ] Replace demo grid lines with your contract tariffs.
- [ ] Complete Zone B country list if you ship there.
- [ ] Generate one real label end-to-end (confirm a delivery with the carrier).
- [ ] Verify the label format string is accepted by your `roulier` version.
- [ ] Test one pickup-point selection with real credentials.
- [ ] Delivengo: paste the API key, **Test connection**, set the sender mobile,
      fill HS codes and weights on exported products, then create one real
      shipment to a non-EU destination and check the label and CN23 PDF.

---

## 9. Project layout

```
odoo_dev/
├── docker-compose.yml        # Postgres + Odoo 19 stack
├── docker/                   # Dockerfile (roulier, zeep) + odoo.conf
├── Makefile                  # init / up / test / shell / reset
└── roekish_delivery_laposte/         # the Odoo module
    ├── models/               # carrier (Colissimo, Delivengo), tariff, pickup mixin, sale, picking
    ├── wizards/              # pickup-point search wizard
    ├── views/                # carrier, sale order, picking forms
    ├── security/             # groups, privilege, ACLs, record rule
    ├── demo/                 # real Colissimo 2026 tariff grids
    └── tests/                # rating, zones, pickup, propagation, Delivengo
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
- `make test` runs the module suite: zone mapping, grid and rule-based
  rating, tracking link, cancellation, secret masking, demo/offline pickup,
  sale→delivery pickup propagation, the Colissimo `errorCode` handling and
  non-administrator access to pickup search (both with a mocked SOAP client),
  the fail-closed guards (missing library, zero weight, incomplete address,
  shared carrier without company), and a **mocked label generation**
  (`test_send_shipping_mocked`) that drives the real `send_shipping` code
  against roulier's response shape and asserts the label is attached and the
  tracking number stored.
- The **pickup web service path is verified against the live Colissimo
  server**: our *Test connection* button reaches `ws.colissimo.fr`, and with
  invalid credentials Colissimo replies `errorCode 201 – Identifiant / mot de
  passe invalide`, which we surface as an error (Colissimo returns auth
  failures in the response body, not as a SOAP fault, so this is checked
  explicitly).

### Delivengo
- The API needs a MyDelivengo account (easy or Profil); there is no public
  sandbox. The `api-creation-mode: simulation` request header validates a
  `POST /envois` body without creating anything, useful for a dry run.
- `make test` covers the Delivengo flow with a mocked HTTP client
  (`tests/test_delivengo.py`): zones, grid and rule rating with the 2 kg
  limit, payload with and without customs, all fail-closed guards, shipment
  creation (label attached, tracking and shipment id stored), validation
  errors flattened and API key masked, cancellation (`DELETE`), test
  connection.

### What still needs a real account
- Generating an actual label end-to-end (valid `roulier` `get_label` call).
- Listing real pickup points (valid Point Retrait credentials).
- Creating a real Delivengo shipment (valid MyDelivengo API key).

### How to check a real account
1. Enter the credentials on a carrier → **Test connection**. Success means the
   account authenticates against Colissimo; an error shows the exact Colissimo
   code/message.
2. Confirm a delivery with the carrier to generate one real label, and verify
   the tracking number and the attached label PDF/ZPL on the transfer.
