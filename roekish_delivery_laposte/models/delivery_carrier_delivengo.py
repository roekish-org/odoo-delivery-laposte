# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import logging
import re

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from .delivery_carrier import EU_COUNTRY_CODES, OM1_COUNTRY_CODES, OM2_COUNTRY_CODES

_logger = logging.getLogger(__name__)

# MyDelivengo REST API (same endpoints for Delivengo easy and Delivengo
# Profil accounts). The API key comes from "Mon compte > Clé API".
DELIVENGO_API_URL = "https://mydelivengo.laposte.fr/api/v2.5/"
DELIVENGO_USER_AGENT = "Odoo/19.0 roekish_delivery_laposte"
DELIVENGO_TIMEOUT = 30
# Hard limit of the Delivengo offer: small goods up to 2 kg per item.
DELIVENGO_MAX_WEIGHT = 2.0
# Delivengo is an international-only service shipped from France: domestic
# and overseas destinations are handled by Colissimo instead.
DELIVENGO_EXCLUDED_CODES = {"FR", "MC"} | OM1_COUNTRY_CODES | OM2_COUNTRY_CODES
# EU customs union members: no customs declaration inside this set.
EU_MEMBER_CODES = EU_COUNTRY_CODES - {"CH"}
# Delivengo zone 1 = European Union + United Kingdom; everything else is
# zone 2 (rest of the world, Switzerland included).
DELIVENGO_ZONE1_CODES = EU_MEMBER_CODES | {"GB"}
# Sender mobile phone accepted by Delivengo: a French mobile number.
FR_MOBILE_RE = re.compile(r"^(?:\+336|\+337|00336|00337|06|07)\d{8}$")


class DeliveryCarrierDelivengo(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("delivengo", "La Poste / Delivengo")],
        ondelete={"delivengo": "set default"},
    )
    delivengo_api_key = fields.Char(
        string="Delivengo API key",
        groups="roekish_delivery_laposte.group_laposte_manager",
        help="API key of the MyDelivengo account (Mon compte > Clé API). "
        "Readable only by La Poste administrators.",
    )
    delivengo_sender_mobile = fields.Char(
        string="Sender mobile phone",
        help="French mobile number printed on the label and used by customs "
        "(+336..., +337..., 06... or 07...). Defaults to the company phone.",
    )
    delivengo_support = fields.Selection(
        selection=[
            ("33", "Delivengo Suivi"),
            ("36", "Delivengo Economique"),
            ("37", "Delivengo Prioritaire"),
        ],
        string="Delivengo product",
        default="33",
        help="Delivengo support (service level) activated on your account.",
    )
    delivengo_label_format = fields.Selection(
        selection=[
            ("32", "PDF 10x15"),
            ("4", "PDF A4 sheet"),
            ("64", "ZPL 10x15 (203 dpi)"),
            ("128", "ZPL 10x15 (300 dpi)"),
        ],
        string="Delivengo label format",
        default="32",
    )
    delivengo_shipment_nature = fields.Selection(
        selection=[
            ("6", "Sale of goods"),
            ("3", "Commercial sample"),
            ("1", "Gift"),
            ("2", "Document"),
            ("4", "Return"),
            ("5", "Other"),
        ],
        string="Nature of shipment",
        default="6",
        help="Printed on the CN22/CN23 customs declaration of shipments "
        "leaving the European Union.",
    )

    # ------------------------------------------------------------------
    # Rating
    # ------------------------------------------------------------------
    def delivengo_rate_shipment(self, order):
        """Return a delivery quote for ``order`` (sale.order)."""
        self.ensure_one()
        error = self._delivengo_check_destination(
            order.partner_shipping_id.country_id, order._get_estimated_weight()
        )
        if error:
            return {
                "success": False,
                "price": 0.0,
                "error_message": error,
                "warning_message": False,
            }
        if self.laposte_pricing_method == "base_on_rule":
            return self.base_on_rule_rate_shipment(order)
        price = self._laposte_grid_rate(
            self._delivengo_get_zone(order.partner_shipping_id.country_id),
            order._get_estimated_weight(),
        )
        if price is None:
            return {
                "success": False,
                "price": 0.0,
                "error_message": self.env._(
                    "No Delivengo tariff matches this destination and weight. "
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

    @api.model
    def _delivengo_get_zone(self, country):
        """Map a destination country to a Delivengo pricing zone."""
        code = country.code if country else None
        return "DGO1" if code in DELIVENGO_ZONE1_CODES else "DGO2"

    def _delivengo_check_destination(self, country, weight):
        """Return an error message when Delivengo cannot serve the shipment."""
        code = country.code if country else None
        if not code or code in DELIVENGO_EXCLUDED_CODES:
            return self.env._(
                "Delivengo only ships abroad. Use a Colissimo carrier for "
                "France and overseas destinations."
            )
        if weight > DELIVENGO_MAX_WEIGHT:
            return self.env._(
                "Delivengo is limited to %s kg per shipment.", DELIVENGO_MAX_WEIGHT
            )
        return False

    def _delivengo_postage(self, picking):
        """Postage paid by the sender, from the grid (0.0 when unknown)."""
        self.ensure_one()
        price = self._laposte_grid_rate(
            self._delivengo_get_zone(picking.partner_id.country_id),
            picking.shipping_weight or picking.weight or 0.0,
        )
        return price if price is not None else 0.0

    # ------------------------------------------------------------------
    # Shipping (label generation)
    # ------------------------------------------------------------------
    def delivengo_send_shipping(self, pickings):
        """Create one Delivengo shipment (envoi) per picking."""
        self.ensure_one()
        return [self._delivengo_send_one(picking) for picking in pickings]

    def _delivengo_send_one(self, picking):
        self.ensure_one()
        payload = self._delivengo_build_payload(picking)
        zpl = self.delivengo_label_format in ("64", "128")
        data = self._delivengo_request(
            "POST",
            "envois",
            params={"support": self.delivengo_label_format, "imprimer_reference": 1},
            json=payload,
            accept="application/zpl" if zpl else "application/pdf",
        )
        shipment_id = str(data.get("id") or "")
        plis = data.get("plis") or []
        tracking = ",".join(p.get("numero") for p in plis if p.get("numero"))
        # With the ZPL accept header Delivengo returns the label only; the
        # customs documents are fetched afterwards as PDF.
        if zpl and self._delivengo_needs_customs(picking.partner_id.country_id):
            pdf = self._delivengo_request(
                "GET", "envois/%s" % shipment_id, accept="application/pdf"
            )
            data["documents_douaniers"] = pdf.get("documents_douaniers")
            data["factures"] = pdf.get("factures")
        self._delivengo_attach_documents(picking, data, tracking, zpl)
        picking.delivengo_shipment_id = shipment_id
        return {
            "exact_price": self._delivengo_postage(picking),
            "tracking_number": tracking or False,
        }

    def _delivengo_attach_documents(self, picking, data, tracking, zpl):
        base = "%s_%s" % (picking.name.replace("/", "_"), tracking or data.get("id"))
        documents = [
            ("documents_supports", "label", "zpl" if zpl else "pdf"),
            ("documents_douaniers", "customs", "pdf"),
            ("factures", "invoice", "pdf"),
        ]
        attachments = [
            ("%s_%s.%s" % (base, suffix, ext), base64.b64decode(data[key]))
            for key, suffix, ext in documents
            if data.get(key)
        ]
        picking.message_post(
            body=self.env._("Delivengo label %s", tracking or ""),
            attachments=attachments,
        )

    def _delivengo_build_payload(self, picking):
        """Build the POST /envois body for one picking (one pli)."""
        self.ensure_one()
        self._delivengo_check_shipment(picking)
        company = self.company_id or self.env.company
        partner = picking.partner_id
        weight = picking.shipping_weight or picking.weight or 0.0
        pli = {
            "expediteur": self._delivengo_sender_address(company.partner_id),
            "expediteur_telephone": self._delivengo_sender_mobile(company),
            "expediteur_email": company.email or "",
            "destinataire": self._delivengo_recipient_address(partner),
            "destinataire_telephone": partner.phone or "",
            "destinataire_email": partner.email or "",
            "reference": picking.sale_id.name or picking.origin or picking.name,
            "poids": int(round(weight * 1000)),
        }
        if self._delivengo_needs_customs(partner.country_id):
            pli["documents_douaniers"] = self._delivengo_customs(picking)
        return {
            "data": {
                "id_support": int(self.delivengo_support),
                "descriptif": picking.name,
                "plis": [pli],
            }
        }

    def _delivengo_check_shipment(self, picking):
        """Fail closed, with a clear message, before calling Delivengo."""
        partner = picking.partner_id
        weight = picking.shipping_weight or picking.weight or 0.0
        if weight <= 0:
            raise UserError(
                self.env._(
                    "Set a shipping weight on %s before generating a Delivengo "
                    "label.",
                    picking.name,
                )
            )
        error = self._delivengo_check_destination(partner.country_id, weight)
        if error:
            raise UserError(error)
        missing = [
            partner._fields[name].string
            for name in ("street", "zip", "city", "country_id")
            if not partner[name]
        ]
        if missing:
            raise UserError(
                self.env._(
                    "The delivery address of %(picking)s is incomplete "
                    "(missing: %(fields)s).",
                    picking=picking.name,
                    fields=", ".join(missing),
                )
            )
        if not (partner.phone or partner.email):
            raise UserError(
                self.env._(
                    "Delivengo requires a phone number or an email on the "
                    "recipient %s.",
                    partner.display_name,
                )
            )
        if partner.country_id.code == "US" and not partner.state_id.code:
            raise UserError(
                self.env._(
                    "Delivengo requires the state on US addresses (recipient %s).",
                    partner.display_name,
                )
            )
        company = self.company_id or self.env.company
        if company.partner_id.country_id.code != "FR":
            raise UserError(
                self.env._(
                    "Delivengo only ships from France: set the country of "
                    "company %s to France.",
                    company.name,
                )
            )

    @api.model
    def _delivengo_needs_customs(self, country):
        return (country.code if country else None) not in EU_MEMBER_CODES

    def _delivengo_sender_mobile(self, company):
        raw = self.delivengo_sender_mobile or company.phone or ""
        mobile = re.sub(r"[\s.\-()]", "", raw)
        if not FR_MOBILE_RE.match(mobile):
            raise UserError(
                self.env._(
                    "Delivengo requires a French mobile number for the sender "
                    "(+336..., +337..., 06... or 07...). Set it on the carrier "
                    "or on company %s.",
                    company.name,
                )
            )
        return mobile

    @api.model
    def _delivengo_sender_address(self, partner):
        return {
            "raison_sociale": partner.commercial_company_name or partner.name or "",
            "nom": partner.name or "",
            "complement_voie": partner.street2 or "",
            "voie": partner.street or "",
            "boite_postale": "",
            "code_postal_commune": "%s %s" % (partner.zip or "", partner.city or ""),
        }

    @api.model
    def _delivengo_recipient_address(self, partner):
        code = partner.country_id.code or ""
        address = {
            "raison_sociale": partner.commercial_company_name or "",
            "nom": partner.name or "",
            "complement_voie": partner.street2 or "",
            "voie": partner.street or "",
            "boite_postale": "",
            "code_postal_commune": "%s %s" % (partner.zip or "", partner.city or ""),
            "pays": code,
            "code_pays": code,
        }
        if code == "US":
            address["code_etat"] = partner.state_id.code or ""
        return address

    def _delivengo_customs(self, picking):
        """CN22/CN23 data for a shipment leaving the European Union."""
        self.ensure_one()
        company = self.company_id or self.env.company
        articles = []
        for move in picking.move_ids:
            product = move.product_id
            qty = move.quantity or move.product_uom_qty
            if product.type == "service" or qty <= 0:
                continue
            hs_code = re.sub(r"\D", "", product.hs_code or "")
            if not (6 <= len(hs_code) <= 10):
                raise UserError(
                    self.env._(
                        "Set a 6 to 10 digit HS code on product '%s' (Inventory "
                        "tab): Delivengo needs it for the customs declaration.",
                        product.display_name,
                    )
                )
            if product.weight <= 0:
                raise UserError(
                    self.env._(
                        "Set a weight on product '%s': Delivengo needs it for "
                        "the customs declaration.",
                        product.display_name,
                    )
                )
            line = move.sale_line_id
            unit_price = (
                line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                if line
                else product.lst_price
            )
            origin = product.country_of_origin or company.partner_id.country_id
            articles.append(
                {
                    "description_detaillee": product.name,
                    "quantite": int(round(qty)),
                    "poids": round(product.weight * qty, 3),
                    "valeur": round(unit_price * qty, 2),
                    "pays_origine": origin.code or "FR",
                    "num_tarifaire": hs_code,
                }
            )
        if not articles:
            raise UserError(
                self.env._("%s has no goods to declare to customs.", picking.name)
            )
        postage = self._delivengo_postage(picking) or picking.carrier_price
        if postage <= 0:
            raise UserError(
                self.env._(
                    "Delivengo requires the postage paid for shipments leaving "
                    "the European Union: add a matching line to the tariff "
                    "grid of carrier '%s'.",
                    self.name,
                )
            )
        invoice = picking.sale_id.invoice_ids.filtered(
            lambda inv: inv.state == "posted" and inv.move_type == "out_invoice"
        )[:1]
        return {
            "envoi_nature": [int(self.delivengo_shipment_nature)],
            "num_facture": invoice.name or picking.sale_id.name or picking.name,
            "frais_port": "%.2f" % postage,
            "articles": articles,
        }

    # ------------------------------------------------------------------
    # HTTP client
    # ------------------------------------------------------------------
    def _delivengo_request(self, method, path, params=None, json=None, accept=None):
        """Call the MyDelivengo API and return the ``data`` object.

        Any transport error or non-2xx answer is turned into a UserError
        carrying Delivengo's own description, with the API key redacted.
        """
        self.ensure_one()
        api_key = self.sudo().delivengo_api_key
        if not api_key:
            raise UserError(
                self.env._(
                    "Fill the Delivengo API key on carrier '%s' first.", self.name
                )
            )
        headers = {
            "API-Authorization": api_key,
            "User-Agent": DELIVENGO_USER_AGENT,
        }
        if accept:
            headers["Accept"] = accept
        try:
            response = requests.request(
                method,
                DELIVENGO_API_URL + path,
                headers=headers,
                params=params,
                json=json,
                timeout=DELIVENGO_TIMEOUT,
            )
        except requests.RequestException as exc:
            _logger.exception("Delivengo request failed")
            raise UserError(
                self.env._(
                    "Delivengo is unreachable:\n%s",
                    self._delivengo_mask_secrets(str(exc)),
                )
            ) from exc
        try:
            body = response.json() if response.text else {}
        except ValueError:
            body = {}
        # DELETE answers with an empty list; normalise to a dict.
        if not isinstance(body, dict):
            body = {}
        if response.status_code == 401:
            raise UserError(self.env._("Delivengo refused the API key."))
        if response.status_code == 429:
            raise UserError(
                self.env._("Delivengo rate limit reached, retry in a few seconds.")
            )
        if not response.ok:
            error = body.get("error") or {}
            raise UserError(
                self.env._(
                    "Delivengo rejected the request (HTTP %(code)s): "
                    "%(description)s\n%(details)s",
                    code=response.status_code,
                    description=error.get("description")
                    or error.get("message")
                    or response.reason,
                    details=self._delivengo_mask_secrets(
                        self._delivengo_format_details(error.get("details"))
                    ),
                )
            )
        return body.get("data") or {}

    @api.model
    def _delivengo_format_details(self, details, path=""):
        """Flatten Delivengo's nested validation errors into readable lines."""
        if isinstance(details, dict):
            lines = (
                self._delivengo_format_details(
                    value, "%s.%s" % (path, key) if path else str(key)
                )
                for key, value in details.items()
            )
        elif isinstance(details, list):
            lines = (self._delivengo_format_details(value, path) for value in details)
        elif details in (None, ""):
            return ""
        else:
            return "%s: %s" % (path, details) if path else str(details)
        return "\n".join(filter(None, lines))

    def _delivengo_mask_secrets(self, text):
        self.ensure_one()
        api_key = self.sudo().delivengo_api_key
        if text and api_key:
            text = text.replace(api_key, "****")
        return text

    # ------------------------------------------------------------------
    # Connectivity test, tracking, cancellation
    # ------------------------------------------------------------------
    def action_delivengo_test_connection(self):
        """Read the account owner with the configured API key."""
        self.ensure_one()
        user = self._delivengo_request("GET", "utilisateurs/0")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Delivengo"),
                "message": self.env._(
                    "Connection successful, account %s.", user.get("email") or ""
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def delivengo_get_tracking_link(self, picking):
        self.ensure_one()
        ref = (picking.carrier_tracking_ref or "").split(",")[0].strip()
        return "https://www.laposte.fr/outils/suivre-vos-envois?code=%s" % ref

    def delivengo_cancel_shipment(self, pickings):
        """Delete the shipment on MyDelivengo, then clear the Odoo state."""
        self.ensure_one()
        for picking in pickings:
            if picking.delivengo_shipment_id:
                self._delivengo_request(
                    "DELETE", "envois/%s" % picking.delivengo_shipment_id
                )
            picking.write(
                {"delivengo_shipment_id": False, "carrier_tracking_ref": False}
            )
        return True
