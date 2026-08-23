<p align="center">
  <img src="docs/logo.svg" alt="delivery_laposte" width="480">
</p>

<h1 align="center">delivery_laposte</h1>

<p align="center">
  <strong>Expédiez avec La Poste / Colissimo depuis Odoo 19.</strong><br>
  Tarification, étiquettes, suivi, points de retrait.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-AGPL--3.0-blue.svg" alt="Licence AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/Odoo-19.0-875A7B.svg" alt="Odoo 19.0">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB.svg" alt="Python 3.12">
  <a href="https://github.com/roekish-org/odoo-delivery-laposte/actions/workflows/ci.yml"><img src="https://github.com/roekish-org/odoo-delivery-laposte/actions/workflows/ci.yml/badge.svg?branch=19.0" alt="CI"></a>
  <img src="https://img.shields.io/badge/PRs-bienvenues-brightgreen.svg" alt="PRs bienvenues">
</p>

---

## Fonctionnalités

| | |
|---|---|
| **Tarification** | Prix calculé depuis une **grille tarifaire Colissimo** (poids × zone) ou les **règles de prix natives** d'Odoo. Point d'extension `_laposte_get_live_price` (fail-closed) pour un futur service de cotation. |
| **Étiquettes** | Génération d'étiquette Colissimo via [`roulier`](https://pypi.org/project/roulier/) ; numéro de suivi enregistré sur le bon de livraison. |
| **Points de retrait** | Recherche des relais proches (web service Colissimo *Point Retrait* via `zeep`), sélectionnable sur le **devis** et le **bon de livraison**, propagé à la validation. |
| **Suivi** | Lien de suivi Colissimo pour le client. |

Bâti sur le framework de livraison natif d'Odoo (`delivery` / `stock_delivery`).
Une **seule dépendance** de module ; `roulier` et `zeep` sont importés à la
demande et **fail-closed** si absents. Le module reste léger et installable.

## Transporteurs et zones

Grilles Colissimo 2026 fournies en démo, **éditables** par vos utilisateurs :
France, Outre-mer (OM1/OM2), UE + Suisse, Royaume-Uni, zones internationales
B et C. Quatre transporteurs prêts à l'emploi :

`Domicile` &nbsp; `Point Retrait` &nbsp; `Éco Outre-mer` &nbsp; `Prêt-à-Envoyer`

## Installation

```bash
pip install roulier zeep          # optionnel : étiquettes + points de retrait
```

Copiez `delivery_laposte/` dans votre `addons_path`, puis installez le module
depuis *Applications*. La tarification fonctionne **sans aucune librairie
externe**.

## Démo locale (Docker)

Pile Odoo 19 + PostgreSQL fournie pour tester immédiatement :

```bash
make init   # image + base de démo avec données
make up     # http://localhost:8069  (admin / admin)
make test   # suite de tests du module
```

## Sécurité

- Identifiants Colissimo réservés au groupe **Administrateur La Poste** ;
  secrets masqués dans les messages d'erreur.
- Droits d'accès fins : groupes **Utilisateur** et **Administrateur** dédiés.
- Isolation multi-société sur les grilles tarifaires.

## Documentation

- [DEVELOPMENT.md](DEVELOPMENT.md) : mise en production, sandbox Colissimo,
  vérification, droits d'accès.
- [Wiki](https://github.com/roekish-org/odoo-delivery-laposte/wiki) :
  installation, configuration, grilles, points de retrait, go-live.
- [delivery_laposte/README.rst](delivery_laposte/README.rst) : fiche du module.

## Contribuer

Les contributions sont bienvenues. Lisez le
[guide de contribution](CONTRIBUTING.md) et le
[code de conduite](CODE_OF_CONDUCT.md). Ouvrez une *issue* pour discuter d'une
évolution, ou proposez une *pull request* sur la branche `19.0`.

## Licence

[AGPL-3.0](LICENSE). © 2026 [ROEKISH](https://github.com/roekish-org).
Maintenu par [alexis2m](https://github.com/alexis2m).
