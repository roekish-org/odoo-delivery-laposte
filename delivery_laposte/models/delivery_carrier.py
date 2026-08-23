# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from roulier import roulier
except ImportError:  # pragma: no cover - roulier is an optional dependency
    roulier = None
    _logger.debug("Cannot `import roulier`; La Poste label generation disabled.")

try:
    from zeep import Client as ZeepClient
except ImportError:  # pragma: no cover - zeep is an optional dependency
    ZeepClient = None
    _logger.debug("Cannot `import zeep`; La Poste pickup search disabled.")

# roulier carrier id and action used for La Poste / Colissimo labels.
ROULIER_CARRIER = "laposte_fr"
ROULIER_LABEL_ACTION = "get_label"
# Colissimo "Point Retrait" SOAP endpoint used to list nearby pickup points.
PICKUP_WSDL = (
    "https://ws.colissimo.fr/pointretrait-ws-cxf/" "PointRetraitServiceWS/2.0?wsdl"
)

# ISO alpha-2 country sets used to map a destination to a Colissimo zone.
FR_COUNTRY_CODES = {"FR", "MC", "AD"}
# Overseas priority zone 1 / zone 2.
OM1_COUNTRY_CODES = {"GP", "MQ", "YT", "RE", "GF", "PM", "MF", "BL"}
OM2_COUNTRY_CODES = {"PF", "NC", "WF", "TF"}
# EU members + Switzerland (UK is priced apart, handled explicitly).
EU_COUNTRY_CODES = {
    "AT",
    "BE",
    "BG",
    "HR",
    "CY",
    "CZ",
    "DK",
    "EE",
    "FI",
    "DE",
    "GR",
    "HU",
    "IE",
    "IT",
    "LV",
    "LT",
    "LU",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SK",
    "SI",
    "ES",
    "SE",
    "CH",
}
# International zone B: near-Europe and Maghreb. Everything else is zone C.
INTB_COUNTRY_CODES = {
    "NO",
    "IS",
    "LI",
    "AL",
    "BA",
    "MK",
    "ME",
    "RS",
    "XK",
    "MD",
    "UA",
    "BY",
    "TR",
    "DZ",
    "MA",
    "TN",
}


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("laposte", "La Poste / Colissimo")],
        ondelete={"laposte": "set default"},
    )
    laposte_account = fields.Char(
        string="La Poste contract number",
        groups="delivery_laposte.group_laposte_manager",
        help="Colissimo contract number used as the web service login.",
    )
    laposte_password = fields.Char(
        string="La Poste password",
        groups="delivery_laposte.group_laposte_manager",
        help="Password of the Colissimo web service account. Readable only "
        "by La Poste administrators.",
    )
    laposte_product_code = fields.Selection(
        selection=[
            ("DOM", "Colissimo Domicile - without signature"),
            ("DOS", "Colissimo Domicile - with signature"),
            ("COLR", "Colissimo Retour France"),
            ("COM", "Colissimo Outre-mer"),
            ("CECO", "Colissimo Eco Outre-mer"),
            ("COLI", "Colissimo International"),
            ("BPR", "Colissimo Point de retrait - Bureau de Poste"),
            ("A2P", "Colissimo Point de retrait - relais / consigne"),
        ],
        string="Colissimo product",
        default="DOM",
        help="Colissimo product code sent to the label web service.",
    )
    laposte_label_format = fields.Selection(
        selection=[
            ("ZPL_10x15_203dpi", "ZPL (label printer)"),
            ("PDF_10x15_300dpi", "PDF 10x15"),
            ("PDF_A4_300dpi", "PDF A4"),
            ("DPL_10x15_203dpi", "DPL (label printer)"),
        ],
        string="Label format",
        default="PDF_10x15_300dpi",
    )
    laposte_pricing_method = fields.Selection(
        selection=[
            ("grid", "La Poste tariff grid"),
            ("base_on_rule", "Odoo pricing rules"),
        ],
        string="Pricing method",
        default="grid",
        help="How the delivery price is computed:\n"
        "- La Poste tariff grid: weight x destination zone lines defined on "
        "this carrier.\n"
        "- Odoo pricing rules: the standard rule-based pricing engine.",
    )
    laposte_tariff_ids = fields.One2many(
        "delivery.laposte.tariff",
        "carrier_id",
        string="La Poste tariff grid",
    )

    # ------------------------------------------------------------------
    # Rating
    # ------------------------------------------------------------------
    def laposte_rate_shipment(self, order):
        """Return a delivery quote for ``order`` (sale.order)."""
        self.ensure_one()
        # Extension point for a real La Poste rating endpoint. La Poste
        # currently exposes no such API, so this returns None and we fall
        # back to the configured pricing method. Any override MUST fail
        # closed (return None) when the endpoint is unavailable.
        price = self._laposte_get_live_price(order)
        if price is None and self.laposte_pricing_method == "base_on_rule":
            return self.base_on_rule_rate_shipment(order)
        if price is None:
            price = self._laposte_grid_rate(
                self._laposte_get_zone(order.partner_shipping_id.country_id),
                order._get_estimated_weight(),
            )
        if price is None:
            return {
                "success": False,
                "price": 0.0,
                "error_message": self.env._(
                    "No La Poste tariff matches this destination and weight. "
                    "Add a matching line to the tariff grid of carrier '%s'.",
                    self.name,
                ),
                "warning_message": False,
            }
        return {
            "success": True,
            "price": price,
            "error_message": False,
            "warning_message": False,
        }

    def _laposte_get_live_price(self, order):
        """Hook for a future La Poste live-pricing web call.

        La Poste / Colissimo does not expose a rating API today, so this
        returns None and pricing falls back to the tariff grid or Odoo
        rules. Override to plug a real endpoint; keep it fail-closed.
        """
        return None

    def _laposte_grid_rate(self, zone, weight):
        """Look up the price for ``zone`` and ``weight`` in the tariff grid.

        Returns the price (company currency) or None when no bracket matches.
        """
        self.ensure_one()
        line = self.env["delivery.laposte.tariff"].search(
            [
                ("carrier_id", "=", self.id),
                ("zone", "=", zone),
                ("max_weight", ">=", weight),
            ],
            order="max_weight asc",
            limit=1,
        )
        return line.price if line else None

    @api.model
    def _laposte_get_zone(self, country):
        """Map a destination country to a Colissimo pricing zone."""
        code = country.code if country else None
        if not code or code in FR_COUNTRY_CODES:
            return "FR"
        if code in OM1_COUNTRY_CODES:
            return "OM1"
        if code in OM2_COUNTRY_CODES:
            return "OM2"
        if code == "GB":
            return "UK"
        if code in EU_COUNTRY_CODES:
            return "EU"
        if code in INTB_COUNTRY_CODES:
            return "INTB"
        return "INTC"

    # ------------------------------------------------------------------
    # Shipping (label generation)
    # ------------------------------------------------------------------
    def laposte_send_shipping(self, pickings):
        """Generate a La Poste label for each picking."""
        self.ensure_one()
        return [self._laposte_send_one(picking) for picking in pickings]

    def _laposte_send_one(self, picking):
        self.ensure_one()
        if roulier is None:
            raise UserError(
                self.env._(
                    "The Python library 'roulier' is required to generate "
                    "La Poste labels. Install it with: pip install roulier"
                )
            )
        payload = self._laposte_build_payload(picking)
        try:
            result = roulier.get(ROULIER_CARRIER, ROULIER_LABEL_ACTION, payload)
        except Exception as exc:
            _logger.exception("La Poste label generation failed")
            raise UserError(
                self.env._(
                    "La Poste rejected the shipment for %(picking)s:\n%(error)s",
                    picking=picking.name,
                    error=self._laposte_mask_secrets(str(exc)),
                )
            ) from exc

        tracking_number = self._laposte_attach_labels(picking, result)
        return {
            "exact_price": self._laposte_price_for_picking(picking),
            "tracking_number": tracking_number or False,
        }

    def _laposte_attach_labels(self, picking, result):
        """Attach every returned label to the picking, return 1st tracking."""
        parcels = result.get("parcels") or []
        tracking_numbers = []
        for parcel in parcels:
            tracking = (parcel.get("tracking") or {}).get("number")
            if tracking:
                tracking_numbers.append(tracking)
            label = parcel.get("label") or {}
            data = label.get("data")
            if not data:
                continue
            filename = "%s_%s.%s" % (
                picking.name.replace("/", "_"),
                tracking or parcel.get("id", ""),
                (label.get("type") or "pdf").lower(),
            )
            picking.message_post(
                body=self.env._("La Poste label %s", tracking or ""),
                attachments=[(filename, base64.b64decode(data))],
            )
        return ",".join(tracking_numbers)

    def _laposte_price_for_picking(self, picking):
        """Best-effort delivery price for the confirmation of a shipment."""
        self.ensure_one()
        zone = self._laposte_get_zone(picking.partner_id.country_id)
        weight = picking.shipping_weight or picking.weight or 0.0
        price = self._laposte_grid_rate(zone, weight)
        return price if price is not None else 0.0

    def _laposte_build_payload(self, picking):
        """Build the roulier payload for one picking.

        The exact schema is validated by roulier at call time against the
        installed library version; keys below follow the laposte_fr encoder.
        """
        self.ensure_one()
        company_partner = self.company_id.partner_id
        weight = picking.shipping_weight or picking.weight or 0.0
        service = {
            "productCode": self.laposte_product_code,
            "labelFormat": self.laposte_label_format,
            "shippingDate": fields.Date.context_today(picking).isoformat(),
            "commercialName": self.company_id.name,
            "returnTypeChoice": 3,  # do not return to sender
        }
        if picking.laposte_pickup_point_code:
            service["pickupLocationId"] = picking.laposte_pickup_point_code
        return {
            "auth": {
                "login": self.laposte_account or "",
                "password": self.laposte_password or "",
            },
            "service": service,
            "parcels": [{"weight": weight}],
            "from_address": self._laposte_convert_address(company_partner),
            "to_address": self._laposte_convert_address(picking.partner_id),
        }

    def _laposte_mask_secrets(self, text):
        """Redact the account password from any carrier/library message."""
        self.ensure_one()
        if not text:
            return text
        password = self.sudo().laposte_password
        if password:
            text = text.replace(password, "****")
        # Also redact a <password>...</password> XML node, if echoed back.
        return re.sub(
            r"(<password>).*?(</password>)", r"\1****\2", text, flags=re.DOTALL
        )

    @api.model
    def _laposte_convert_address(self, partner):
        """Convert a res.partner to the address dict roulier expects."""
        return {
            "company": partner.commercial_company_name or "",
            "name": partner.name or "",
            "street": partner.street or "",
            "street2": partner.street2 or "",
            "city": partner.city or "",
            "zip": partner.zip or "",
            "country": partner.country_id.code or "",
            "phone": partner.phone or "",
            "email": partner.email or "",
        }

    # ------------------------------------------------------------------
    # Connectivity test (go-live check)
    # ------------------------------------------------------------------
    def action_laposte_test_connection(self):
        """Ping La Poste with the configured credentials.

        Uses the Point Retrait web service against the company address as a
        non-destructive connectivity and authentication check.
        """
        self.ensure_one()
        if not (self.laposte_account and self.laposte_password):
            raise UserError(
                self.env._(
                    "Fill the contract number and password before testing "
                    "the connection."
                )
            )
        company_partner = self.company_id.partner_id
        points = self._laposte_call_pickup_ws(
            company_partner.zip or "75001",
            company_partner.city or "Paris",
            company_partner.country_id.code or "FR",
            1.0,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("La Poste"),
                "message": self.env._(
                    "Connection successful, %s pickup points returned.",
                    len(points),
                ),
                "type": "success",
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # Pickup points (relay)
    # ------------------------------------------------------------------
    def _laposte_search_pickup_points(self, zipcode, city, country_code, weight):
        """Return a list of pickup points near ``zipcode``.

        Each item is a dict: code, name, street, zip, city, distance.
        When credentials are set, the live Colissimo web service is queried;
        otherwise demonstrative points are returned so the flow stays
        testable without an account.
        """
        self.ensure_one()
        if self.laposte_account and self.laposte_password:
            return self._laposte_call_pickup_ws(zipcode, city, country_code, weight)
        return self._laposte_demo_pickup_points(zipcode, city)

    def _laposte_call_pickup_ws(self, zipcode, city, country_code, weight):
        self.ensure_one()
        if ZeepClient is None:
            raise UserError(
                self.env._(
                    "The Python library 'zeep' is required to search La Poste "
                    "pickup points. Install it with: pip install zeep"
                )
            )
        client = ZeepClient(PICKUP_WSDL)
        today = fields.Date.context_today(self)
        try:
            # Parameter names follow the Point Retrait WS 2.0 contract; adjust
            # to the WSDL version you subscribe to if it rejects the call.
            response = client.service.findRDVPointRetraitAcheminement(
                accountNumber=self.laposte_account,
                password=self.laposte_password,
                address=" ",
                zipCode=zipcode or "",
                city=city or "",
                countryCode=country_code or "FR",
                weight=int((weight or 0) * 1000) or 100,
                shippingDate=today.strftime("%d/%m/%Y"),
                optionInter=0 if (country_code or "FR") == "FR" else 1,
            )
        except Exception as exc:
            _logger.exception("La Poste pickup search failed")
            raise UserError(
                self.env._(
                    "La Poste pickup search failed:\n%s",
                    self._laposte_mask_secrets(str(exc)),
                )
            ) from exc
        # Colissimo returns errorCode 0 on success; on bad credentials or bad
        # input it returns a non-zero code in the body (no SOAP fault), so we
        # must check it explicitly, otherwise a wrong account looks "OK".
        error_code = getattr(response, "errorCode", None)
        if error_code not in (None, 0, "0"):
            message = getattr(response, "errorMessage", "") or ("error %s" % error_code)
            raise UserError(
                self.env._(
                    "La Poste refused the request (code %(code)s): %(msg)s",
                    code=error_code,
                    msg=self._laposte_mask_secrets(str(message)),
                )
            )
        points = []
        for point in getattr(response, "listePointRetraitAcheminement", None) or []:
            points.append(
                {
                    "code": getattr(point, "identifiant", "") or "",
                    "name": getattr(point, "nom", "") or "",
                    "street": getattr(point, "adresse1", "") or "",
                    "zip": getattr(point, "codePostal", "") or "",
                    "city": getattr(point, "localite", "") or "",
                    "distance": float(getattr(point, "distanceEnMetre", 0) or 0),
                }
            )
        return points

    @api.model
    def _laposte_demo_pickup_points(self, zipcode, city):
        zipcode = zipcode or "75001"
        city = city or "Paris"
        return [
            {
                "code": "DEMO1",
                "name": "Bureau de Poste %s" % city,
                "street": "1 rue de la Poste",
                "zip": zipcode,
                "city": city,
                "distance": 120.0,
            },
            {
                "code": "DEMO2",
                "name": "Relais Pickup %s" % city,
                "street": "12 avenue des Colis",
                "zip": zipcode,
                "city": city,
                "distance": 340.0,
            },
            {
                "code": "DEMO3",
                "name": "Consigne Pickup Station",
                "street": "3 place du Marche",
                "zip": zipcode,
                "city": city,
                "distance": 560.0,
            },
        ]

    # ------------------------------------------------------------------
    # Tracking & cancellation
    # ------------------------------------------------------------------
    def laposte_get_tracking_link(self, picking):
        self.ensure_one()
        ref = (picking.carrier_tracking_ref or "").split(",")[0].strip()
        return "https://www.laposte.fr/outils/suivre-vos-envois?code=%s" % ref

    def laposte_cancel_shipment(self, pickings):
        """Clear the tracking reference.

        Colissimo exposes no reliable label-cancellation web service, so we
        only reset Odoo state and remind the user to act on the portal.
        """
        self.ensure_one()
        for picking in pickings:
            picking.message_post(
                body=self.env._(
                    "La Poste tracking reference cleared in Odoo. If the "
                    "parcel was already handed over, cancel it on the "
                    "Colissimo portal."
                )
            )
            picking.carrier_tracking_ref = False
        return True
