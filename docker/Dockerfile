# Odoo 19 image with the Python dependencies needed by roekish_delivery_laposte.
FROM odoo:19.0

USER root
# roulier -> Colissimo label generation ; zeep -> Point Retrait SOAP lookup.
RUN pip3 install --no-cache-dir --break-system-packages roulier zeep
USER odoo
