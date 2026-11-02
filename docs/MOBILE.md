# Appli mobile de Jimmy

L'appli mobile est une **appli web (PWA)** servie par Jimmy lui-même, sur ton PC. Elle s'installe sur l'écran d'accueil du téléphone, ne demande aucun compte et n'envoie rien à un serveur tiers.

> Elle ne marche que si **le PC est allumé et Jimmy ouvert**. Si le PC s'éteint, le téléphone affiche « Hors ligne ».

## Relier un téléphone

1. Dans Jimmy : **Appli mobile** → coche **Activer** → choisis un mode.
2. Scanne le **QR code** avec l'appareil photo du téléphone (ou ouvre l'adresse affichée et tape le **code**).
3. Le téléphone est relié. Pour l'ajouter à l'écran d'accueil : menu du navigateur → « Ajouter à l'écran d'accueil » / « Installer l'application ».

Le code de jumelage est à **usage unique** et expire au bout de 10 minutes. Une fois relié, le téléphone garde sa propre clé ; le PC n'en conserve que l'empreinte (`devices.json`). Tu peux **délier** un téléphone à tout moment (Appli mobile → Délier).

## Les trois modes

| Mode | Quand l'utiliser | Micro du téléphone |
|---|---|---|
| **Wi-Fi** | Téléphone et PC sur le même réseau | Non (adresse `http`) : écriture seulement |
| **Internet (Cloudflare)** | Partout, sans rien configurer. Jimmy télécharge `cloudflared` (officiel) une seule fois | Oui (`https`) |
| **Mon adresse** | Tailscale, ZeroTier, ou ton propre domaine vers `http://IP-du-PC:8765` | Oui si l'adresse est en `https` |

L'adresse du tunnel Cloudflare **change à chaque démarrage de Jimmy** : il faut alors re-scanner le QR code. Pour une adresse fixe, utilise « Mon adresse ».

## Ce que tu peux faire depuis le téléphone

- Écrire ou **parler** à Jimmy (bouton micro, ou « conversation continue » : il se remet à écouter après chaque réponse), sans mot d'éveil.
- Entendre ses réponses à voix haute (réglable).
- Voir en direct ce qu'il fait (étapes), l'arrêter (**Stop**), démarrer une **nouvelle discussion**.
- **Changer de discussion** (bouton ☰) : la liste est la même que sur le PC. En choisir une sur le téléphone l'ouvre aussi sur l'ordinateur, et inversement : tout reste synchronisé.
- **Ajouter du contexte pendant qu'il travaille** : ton message est injecté dans la tâche en cours.

Les demandes envoyées depuis le téléphone ne sont pas lues à voix haute sur le PC.

## Sécurité

- Un téléphone relié peut donner des ordres à Jimmy, donc **agir sur ton PC**. Ne relie que tes appareils.
- Clé de 256 bits, code de jumelage à usage unique, tentatives limitées par adresse, connexion chiffrée en `https` avec le tunnel ou ton domaine.
- En Wi-Fi (`http`), le trafic n'est pas chiffré : à éviter sur un réseau que tu ne maîtrises pas.
- L'appli est **désactivée par défaut** ; désactive-la quand tu n'en as pas besoin.

## Dépannage

- « Hors ligne » : Jimmy est fermé, le PC est en veille, ou l'adresse du tunnel a changé (re-scanne).
- Le micro ne s'affiche pas : il faut une adresse `https` (mode Internet) et un navigateur compatible (Chrome/Android, Safari/iOS).
- Rien ne se passe en Wi-Fi : le pare-feu Windows doit autoriser Jimmy sur le port 8765 (réseau privé).
