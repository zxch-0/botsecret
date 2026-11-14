# botsecret

Bot Discord de destruction de serveur, piloté **exclusivement par un dashboard web** noir et rouge.
Les commandes côté Discord sont des leurres banals : sans le **code secret** (configurable sur le
site), elles ne font rien d'utile.

## Modes de frappe

| Mode | Effet |
| --- | --- |
| 🌪️ Chaos | Renommage général, salons et fils créés en masse, webhooks et invitations spammés |
| ☢️ Nuke total | Tout : renommage, confinement, suppressions, mute, ban, MP de masse |
| 🔥 Incendie | Suppressions lourdes, expulsions, cendres partout |
| 🕶️ Furtif | Peu de workers, délais longs, noms vides, personne ne comprend |
| 🔒 Confinement | Rien n'est supprimé : salons verrouillés, membres renommés et muselés |

Chaque mode surcharge le preset personnalisé, modifiable champ par champ sur le dashboard.

## Fonctionnalités

- Renommage instantané du serveur, de **tous** les salons, rôles et membres
- Création massive de salons, vocaux, fils et rôles
- Suppression des anciens salons, catégories, rôles, emojis, stickers, invitations, webhooks
- Confinement, spam de messages, spam de webhooks, invitations en masse
- Mute, kick vocal, MP de masse, ban ou kick
- Progression en direct, compteurs, journal, arrêt d'urgence, message final
- Confirmation par saisie de `DETRUIRE` et raccourci `Ctrl+Shift+D`

## Déploiement sur Render

1. Forkez ou poussez ce dépôt sur votre compte GitHub.
2. Sur [Render](https://render.com), **New > Blueprint**, sélectionnez le dépôt
   (le fichier `render.yaml` est détecté) — ou créez un **Web Service** manuel :
   - Build : `pip install -r requirements.txt`
   - Start : `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check : `/healthz`
3. Renseignez les variables d'environnement :
   - `DISCORD_TOKEN` : token du bot (Developer Portal > Bot)
   - `DASHBOARD_PASSWORD` : mot de passe du dashboard
   - `SECRET_KEY` : `openssl rand -hex 32`
   - `COOKIE_SECURE` : `true`
4. Déployez, ouvrez l'URL du service, connectez-vous.
5. Invitez le bot avec le scope `applications.commands` et la permission `Administrator`.
6. Collez l'identifiant du serveur dans « Serveur cible », synchronisez les commandes,
   puis frappez.

## Commandes Discord

Toutes sont muettes sans le code secret.

| Commande | Sans code | Avec le bon code |
| --- | --- | --- |
| `/gerer` | « ✅ Rien à signaler. » | Panneau + sélecteur de mode |
| `/welcome` | « 👋 Bienvenue ! » | Mode Chaos |
| `/salut` | « Salut 👋 » | Mode Nuke total |
| `/regles` | Règles génériques | Mode Incendie |
| `/info` | Infos serveur | Mode Furtif |
| `/ping` | Latence | Latence + panneau |
| `/stats` | Statistiques | Panneau de contrôle |
| `/aide` | Aide générique | Mode Confinement |

## Notes

- Le plan gratuit Render met le service en veille : utilisez un pinger externe sur `/healthz`.
- Le disque Render est éphémère : le SQLite (`data/`) est réinitialisé à chaque redéploiement.
  Ajoutez un disque persistant ou passez `DATA_DIR` sur un volume monté si besoin.
- Le code secret est affiché sur le dashboard et peut être régénéré à tout moment.
