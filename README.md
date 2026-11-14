# botsecret

Bot Discord de destruction de serveur, piloté **exclusivement par un dashboard web**.
Les commandes côté Discord (`/gerer`, `/welcome`, `/stats`) sont déguisées en commandes
banales : sans le **code secret** (configurable sur le site), elles ne font rien d'utile.

## Fonctionnalités

- Renommage instantané du serveur et de **tous** les salons
- Création massive de salons textuels et vocaux
- Suppression des anciens salons, rôles, emojis, stickers, invitations, webhooks
- Spam de messages, ban ou kick des membres
- Parallélisation réglable (workers) et délai configurable
- Suivi en direct : progression, compteurs, journal, arrêt d'urgence
- Code secret régénérable, commandes synchronisables depuis le dashboard

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
5. Invitez le bot avec le scope `applications.commands` et les permissions
   `Administrator` (ou au minimum Gérer les salons, Gérer les rôles, Gérer le serveur,
   Gérer les webhooks, Bannir/Expulser des membres).
6. Collez l'identifiant du serveur dans « Serveur cible », cliquez sur
   « Synchroniser les commandes », puis réglez le preset et lancez.

## Commandes Discord

| Commande | Sans code | Avec le bon code |
| --- | --- | --- |
| `/gerer [code]` | « ✅ Rien à signaler. » | Panneau avec boutons Lancer / Statut / Arrêter |
| `/welcome [code]` | « 👋 Bienvenue ! » | Lance immédiatement la destruction |
| `/stats [code]` | Statistiques banales | Panneau de contrôle |

## Notes

- Le plan gratuit Render met le service en veille : utilisez un pinger externe sur `/healthz`
  pour garder le bot en ligne.
- Le disque Render est éphémère : le SQLite (`data/`) est réinitialisé à chaque redéploiement.
  Ajoutez un disque persistant ou passez `DATA_DIR` sur un volume monté si besoin.
- Le code secret est affiché sur le dashboard et peut être régénéré à tout moment.
