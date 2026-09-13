# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Ce projet suit le versionnage des modules Odoo (`19.0.x.y.z`).

## [19.0.1.3.0] - 2026-09-13

### Ajouté

- **Délai de livraison** annoncé, en jours ouvrés : champs min / max sur le
  transporteur (Colissimo et Delivengo), surcharge par zone sur les lignes de
  la grille tarifaire, valeurs de démo indicatives.
- Chaque cotation (`rate_shipment`) renvoie `delay_min` et `delay_max` avec
  le prix, pour choisir un transporteur sur le coût et le délai ; la phrase
  « Livraison en X à Y jours ouvrés » s'affiche dans l'assistant d'ajout de
  livraison et est conservée sur le devis.
- Tests du délai (grille, surcharge par zone, règles Odoo, point d'entrée
  générique) pour Colissimo et Delivengo.

## [19.0.1.2.0] - 2026-09-13

### Ajouté

- Fournisseur **La Poste / Delivengo** pour les petites marchandises à
  l'international (2 kg max) : étiquette et documents douaniers CN22/CN23
  générés via l'API REST MyDelivengo 2.5 (comptes easy et Profil), numéro de
  suivi, annulation de l'envoi sur MyDelivengo, test de connexion.
- Grille tarifaire Delivengo sur deux zones (UE + Royaume-Uni, reste du
  monde), avec le transporteur de démo *Delivengo easy* et sa grille publique.
- Déclaration douanière construite depuis les lignes du bon de livraison :
  code SH et pays d'origine du produit, quantité, poids, valeur, nature de
  l'envoi, numéro de facture, frais de port.
- Contrôles avant appel : destination hors France, poids inférieur ou égal à
  2 kg, adresse complète, téléphone ou email du destinataire, État pour les
  États-Unis, mobile français de l'expéditeur, code SH et poids des articles.
- Champ *Delivengo shipment ID* sur le bon de livraison.
- Tests : zones, tarification (grille et règles), charge utile avec et sans
  douane, garde-fous, création et annulation d'envoi (API simulée), masquage
  de la clé API dans les erreurs.

### Modifié

- Nom du module : *Delivery Carrier La Poste / Colissimo / Delivengo*.

## [19.0.1.1.0] - 2026-09-09

### Corrigé

- La recherche de points de retrait et le test de connexion lisent les
  identifiants Colissimo avec `sudo` : un utilisateur non administrateur
  obtenait une erreur d'accès, les champs étant réservés aux administrateurs.
- L'adresse expéditeur se rabat sur la société courante quand le transporteur
  n'est rattaché à aucune société.

### Ajouté

- Contrôle avant appel à Colissimo : poids nul et adresse incomplète sont
  refusés avec un message explicite.
- Les vendeurs peuvent ouvrir l'assistant de point de retrait sur les devis.
- Traduction française du module.
- Tests : lien de suivi, annulation, masquage des secrets, tarification par
  règles, propagation du point de retrait, codes d'erreur Colissimo, garde-fous
  sans librairie, accès utilisateur non administrateur.

### Modifié

- Fichiers internes renommés pour suivre le nom technique du module.
- Fiche du module (README.rst) mise à jour : zones réelles, points de retrait,
  test de connexion, droits d'accès.
- Le champ `website` du manifeste pointe vers le dépôt.

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
