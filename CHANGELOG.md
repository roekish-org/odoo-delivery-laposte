# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Ce projet suit le versionnage des modules Odoo (`19.0.x.y.z`).

## [19.0.1.0.0] - 2026-08-23

### Ajouté

- Type de transporteur `laposte` sur le framework de livraison natif d'Odoo.
- Tarification par grille Colissimo (zones FR, OM1, OM2, EU+CH, UK, B, C) ou
  par règles Odoo, avec un point d'extension `_laposte_get_live_price`.
- Génération d'étiquettes Colissimo via `roulier`, avec numéro de suivi.
- Sélection de point de retrait sur le devis et le bon de livraison, avec
  propagation à la confirmation (web service Colissimo Point Retrait via `zeep`).
- Bouton de test de connexion aux web services Colissimo.
- Grilles tarifaires Colissimo 2026 en données de démonstration (4 transporteurs).
- Droits d'accès fins (groupes Utilisateur et Administrateur), masquage des
  secrets, isolation multi-société.
- Pile Docker de démonstration, suite de tests, intégration continue.
