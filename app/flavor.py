"""Textes d'ambiance : citations, bannières, libellés sinistres."""

from __future__ import annotations

import random

BANNER = (
    "╔══════════════════════════════════╗\n"
    "║   ☠  B O T S E C R E T  ☠   ║\n"
    "╚══════════════════════════════════╝"
)

QUOTES = [
    "Tout ce qui est construit peut être rasé.",
    "Le silence après le chaos, c'est le vrai but.",
    "Un serveur propre est un serveur vide.",
    "On ne détruit bien que ce qu'on aime.",
    "Les salons tombent, les souvenirs restent.",
    "L'ordre est une illusion temporaire.",
    "Chaque salon supprimé est une page arrachée.",
    "Le bot observe. Le bot attend. Le bot frappe.",
    "Il n'y a pas de sauvegarde. Il n'y a que des ruines.",
    "Bienvenue dans l'après.",
    "La poussière est le seul héritage durable.",
    "Tu as cliqué. C'est ta faute.",
]

PRESENCE = [
    "💀 prête à frapper",
    "☠️ compte les salons",
    "🩸 affûte la faux",
    "🕯️ dans l'ombre",
    "⚰️ en embuscade",
]

LABELS = {
    "serveur_renomme": "serveur renommé",
    "messages": "messages spam",
    "salons_renommes": "salons renommés",
    "salons_crees": "salons créés",
    "vocaux_crees": "vocaux créés",
    "fils_crees": "fils créés",
    "salons_supprimes": "salons supprimés",
    "categories_supprimees": "catégories supprimées",
    "roles_supprimes": "rôles supprimés",
    "roles_renommes": "rôles renommés",
    "roles_crees": "rôles créés",
    "emojis_supprimes": "emojis supprimés",
    "stickers_supprimes": "stickers supprimés",
    "invitations_supprimees": "invitations supprimées",
    "invitations_creees": "invitations créées",
    "webhooks_supprimes": "webhooks supprimés",
    "webhooks_crees": "webhooks créés",
    "membres_renommes": "membres renommés",
    "membres_mutes": "membres muselés",
    "membres_deconnectes": "membres déconnectés",
    "membres_bannis": "membres bannis",
    "membres_expulses": "membres expulsés",
    "mp_envoyes": "MP envoyés",
    "salons_confines": "salons confinés",
}


def quote() -> str:
    return random.choice(QUOTES)


def presence() -> str:
    return random.choice(PRESENCE)


def label(key: str) -> str:
    return LABELS.get(key, key.replace("_", " "))
