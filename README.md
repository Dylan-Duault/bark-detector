# Bark Detector

**Le journal des aboiements de votre chien, à consulter depuis votre téléphone.**

Un Raspberry Pi écoute le microphone, repère les vocalisations du chien et
conserve les séries d’aboiements. L’interface **À l’écoute** permet ensuite de
réécouter ces moments et de suivre leur évolution au fil des jours.

**Raspberry Pi · Interface mobile · Données locales · Accès par code**

## L’interface en images

| Le journal de la journée | L’évolution dans le temps |
| :---: | :---: |
| <img src="docs/images/dashboard-mobile.png" width="320" alt="Interface mobile : statistiques quotidiennes, activité par heure"> | <img src="docs/images/trends-mobile.png" width="320" alt="Interface mobile : évolution quotidienne, calendrier de chaleur et activité cumulée par heure"> |

*Captures de l’interface réelle avec des données de démonstration. Les chiffres
et enregistrements illustrés ne proviennent pas du chien de l’utilisateur.*

<details>
<summary>Voir les lecteurs audio et l’écran de connexion</summary>

<p>Écoute et téléchargement des enregistrements, puis accès par code :</p>
<p>
<img src="docs/images/recordings-mobile.png" width="320" alt="Liste des enregistrements avec lecteurs audio et liens de téléchargement">
<img src="docs/images/login-mobile.png" width="320" alt="Écran de connexion demandant un code à quatre chiffres">
</p>

</details>

## Ce que fait le projet

- **Conserver toute la série** : l’enregistrement inclut jusqu’à une minute avant
  le déclenchement, puis continue jusqu’à 10 secondes sans détection.
- **Réécouter depuis le téléphone** : lecteurs audio, déplacement dans les fichiers
  et téléchargement, sans application à installer.
- **Comprendre les habitudes** : statistiques quotidiennes, historique et
  graphiques sur 7 ou 30 jours, avec détail au toucher.
- **Fonctionner au quotidien** : le détecteur et l’interface démarrent avec le Pi
  et redémarrent automatiquement en cas d’arrêt.
- **Garder les données chez soi** : journaux et audio restent sur le Pi. L’accès
  à la page, aux statistiques et aux fichiers audio exige un code.

## Comment l’enregistrement fonctionne

1. **Écouter.** [YAMNet](https://tfhub.dev/google/yamnet/1) analyse le microphone
   en blocs de 1,2 seconde, en mono à 16 kHz.
2. **Déclencher.** Deux blocs positifs consécutifs démarrent un enregistrement.
   La minute précédente est conservée pour inclure le début des aboiements.
3. **Continuer.** Chaque nouvelle détection prolonge l’enregistrement. Une courte
   pause entre deux salves ne coupe pas le fichier.
4. **Sauvegarder.** Après 10 secondes sans détection, le WAV terminé apparaît
   dans l’interface. Il n’y a pas de limite d’un fichier par heure.

L’audio est écrit progressivement sur disque pour éviter d’accumuler une longue
série en mémoire. Si le détecteur vient de démarrer, il conserve l’historique
disponible. Un arrêt propre sauvegarde l’enregistrement en cours ; une coupure
brutale peut laisser un fichier temporaire incomplet, masqué dans l’interface.

> **Ce que mesure le détecteur :** des blocs audio contenant des vocalisations
> de chien, pas chaque « ouaf ». La classe `Dog` peut aussi couvrir des hurlements
> et gémissements. Le modèle ne distingue pas votre chien de celui du voisin.

## Installer sur un Raspberry Pi

Testé sur un Pi sous **Linux ARM64 avec Python 3.13**, avec un microphone USB
accessible via ALSA. Le premier lancement nécessite Internet pour télécharger
YAMNet ; le modèle est ensuite mis en cache.

### 1. Préparer le projet

```bash
sudo apt-get install python3-venv libportaudio2 libsndfile1
git clone https://github.com/Dylan-Duault/bark-detector.git
cd bark-detector
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. Choisir le code d’accès

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Renseigner `DASHBOARD_PIN` avec **exactement quatre chiffres**, puis enregistrer.
Le serveur refuse de démarrer sans code valide. Si le projet est déjà installé,
conserver le `.env` existant. Ce fichier n’est pas envoyé dans Git.

### 3. Activer le démarrage automatique

```bash
sudo .venv/bin/python -m app.cli install-services
```

L’installateur configure et démarre deux services indépendants :

| Service | Rôle |
| --- | --- |
| `bark-detector` | Écoute du micro, détection, enregistrements et journaux |
| `bark-dashboard` | Interface web sur le port `8080` |

Ils fonctionnent sous le compte qui a lancé `sudo`, sans avoir besoin d’ouvrir
une session. Le détecteur dispose de l’accès au groupe `audio`.

### 4. Ouvrir le journal sur le téléphone

Sur le **même réseau Wi-Fi**, ouvrir :

```text
http://raspberrypi.local:8080
```

Si ce nom n’est pas reconnu, utiliser `http://IP-DU-PI:8080` ; `hostname -I`
affiche les adresses du Pi. Sur le Pi lui-même : `http://localhost:8080`.
La machine doit rester allumée et le microphone branché.

## Lire les statistiques

Choisir une date pour retrouver les **extraits avec aboiements**, les
**séries d’aboiements** et les fichiers audio. Un extrait est une portion de
1,2 seconde reconnue comme contenant un chien ; une série regroupe les
aboiements jusqu’à 1 min 30 de calme. Les explications restent courtes, sous
les compteurs. La page s’actualise toutes les 30 secondes sans interrompre une écoute.

Une ligne discrète près du bouton Actualiser indique l’état actuel du détecteur :
écoute active, démarrage, micro indisponible, absence de signal ou erreur. Le
service publie son état environ toutes les 5 secondes ; s’il ne répond plus,
l’interface cesse d’annoncer une écoute active. L’heure du dernier signal est
accessible dans l’infobulle de cette ligne.

Le temps d’écoute mesuré est indiqué à côté du titre de la journée et dans
l’historique, ainsi que dans les détails du graphique quotidien. Il correspond
aux extraits réellement analysés, sans compter le chargement du modèle, les
interruptions ni les échantillons non traités. La mesure commence à l’activation
de cette fonctionnalité ; les anciennes durées restent inconnues, sans estimation.
Les heures sans donnée sont hachurées dans le calendrier, tandis qu’une heure
écoutée sans aboiement reste affichée avec une activité nulle.

Les graphiques sont **en bas de page** :

| Graphique | À quoi il sert |
| --- | --- |
| Évolution quotidienne | Comparer la durée des séries d’aboiements déjà finies d’un jour à l’autre |
| Calendrier de chaleur | Repérer les heures et les jours où les détections se répètent |
| Activité horaire cumulée | Identifier les heures les plus animées sur la période |

Le sélecteur **7 / 30 jours** couvre la période se terminant à la date choisie.
Toucher une barre ou une case affiche le détail. Sur mobile, faire glisser le
calendrier horizontalement pour parcourir les heures.

Une **série d’aboiements** est comptée après 90 secondes sans détection. Sa
durée inclut les pauses entre aboiements : ce n’est ni le temps de vocalisation
exact ni la durée du fichier audio. La journée en cours peut être incomplète.
Les jours sans donnée sont hachurés ; une journée avec des détections ne garantit pas une
journée entière d’écoute.

## Accès et confidentialité

Le code protège aussi les URL directes des statistiques et des enregistrements.
Une mauvaise entrée impose un délai de **2, 4, 8, 16, 32 puis 60 secondes**, par
adresse IP. Recharger la page ne supprime pas l’attente. Une connexion réussie
remet le compteur à zéro.

La session dure **12 heures**, ou jusqu’à la déconnexion. Le cookie est
`HttpOnly` et `SameSite=Strict`. Les sessions et délais sont conservés en mémoire
et réinitialisés au redémarrage du serveur. Le code n’est présent ni dans le
JavaScript, ni dans les URL ou les journaux.

> Ce serveur HTTP est destiné à un **réseau local de confiance**. Les échanges
> ne sont pas chiffrés : ne pas ouvrir directement son port sur Internet.

Pour changer le code, modifier `.env`, puis lancer :

```bash
sudo systemctl restart bark-dashboard
```

## Gérer le Pi

### Musique automatique

Dans `.env`, définir `BARK_MUSIC_ENABLED=true` pour jouer le morceau après
**20 détections en moins de 5 minutes**, ou `false` pour désactiver cette option
(désactivée par défaut). Redémarrer `bark-detector` après chaque changement.
Le seuil et la période sont également configurables dans `.env` :

```dotenv
BARK_MUSIC_ENABLED=true
BARK_MUSIC_BARK_COUNT=20
BARK_MUSIC_WINDOW_SECONDS=300
BARK_MUSIC_VOLUME_PERCENT=35
```

`BARK_MUSIC_BARK_COUNT` est le nombre de détections et
`BARK_MUSIC_WINDOW_SECONDS` la période en secondes (300 = 5 minutes).
Ces deux valeurs doivent être des entiers strictement positifs ; sans réglage,
elles valent respectivement 20 et 300.

Il s'agit de blocs audio positifs de 1,2 seconde, pas du nombre exact de « ouaf ».

À chaque déclenchement, le MP3 suivant de `data/music/` est lu, dans l'ordre
alphabétique des fichiers, puis la liste reprend au début. La position est
conservée dans `data/music/.last-track`, y compris après redémarrage.
Ajouter un MP3 dans ce dossier suffit pour l'inclure dans la rotation.
Les quatre morceaux installés sont Amberlight, Precious Memories, Spring Flowers
et Wintry.

Chaque morceau est lu une fois en entier, sans bloquer la détection ni superposer
les lectures. Les détections pendant la lecture ne comptent pas pour le prochain
déclenchement ; le comptage repart à zéro après la musique et au redémarrage.
Une erreur de lecture est journalisée sans arrêter la détection.

La lecture utilise `ffplay` (`sudo apt-get install ffmpeg`) et la sortie par
défaut de la session audio de l'utilisateur du service (PipeWire/PulseAudio).
Pour écouter sur l'Acton III, la connecter et la choisir comme sortie par défaut.
Avant chaque lecture, `BARK_MUSIC_VOLUME_PERCENT` (entier de 0 à 100,
35 par défaut) est appliqué à la sortie du système, qui est aussi démutée.
Le volume est relu après synchronisation Bluetooth, avec jusqu'à trois tentatives.
Si le réglage échoue ou ne correspond pas, la lecture est annulée et une erreur
apparaît dans les logs. Cette vérification ne bloque pas l'analyse du microphone.

Les fichiers locaux sont exclus de Git avec `data/`. Le morceau d'origine est
`data/music/precious-memories.mp3`. Pour le télécharger sur une autre installation :

```bash
mkdir -p data/music
curl --fail --location --user-agent 'Mozilla/5.0' --referer 'https://www.chosic.com/' \
  'https://www.chosic.com/wp-content/uploads/2021/02/precious-memories(chosic.com).mp3' \
  --output data/music/precious-memories.mp3
sudo systemctl restart bark-detector
```

```bash
# Vérifier les services
systemctl status bark-detector bark-dashboard

# Suivre les journaux techniques
journalctl -u bark-detector -u bark-dashboard -f

# Appliquer une modification du code
sudo systemctl restart bark-detector bark-dashboard

# Arrêter et désactiver le démarrage automatique
sudo systemctl disable --now bark-detector bark-dashboard
```

Relancer l’installateur après déplacement du dépôt ou modification des unités
systemd. Le cache du modèle est dans `/var/cache/bark-detector/yamnet`.

<details>
<summary>Lancement manuel et options du serveur</summary>

Arrêter d’abord les services correspondants pour éviter de lancer deux
détecteurs sur le même microphone. Utiliser ensuite deux terminaux :

```bash
.venv/bin/python -m app.cli detector
.venv/bin/python -m app.cli web
```

Le serveur peut consulter l’historique même si le détecteur est arrêté.

| Option | Usage |
| --- | --- |
| `--port 8080` | Changer le port web |
| `--host 127.0.0.1` | Limiter l’accès à la machine locale |
| `--data-dir /chemin/vers/les/donnees` | Lire un autre dossier contenant `logs/` et `recordings/` |

L’installateur accepte `--user NOM` pour un autre compte. Pour générer les
unités sans les installer :

```bash
.venv/bin/python -m app.cli install-services --output-dir /tmp/bark-services
```

</details>

<details>
<summary>Ajuster la sensibilité et les durées</summary>

Ces réglages peuvent être définis dans `.env` ; leur validation et leurs valeurs
par défaut se trouvent dans `app/config.py`. Après modification, redémarrer
`bark-detector`.

| Réglage | Valeur | Rôle |
| --- | --- | --- |
| `MIN_BARK_VOLUME` | `0.012` | Volume moyen minimal ; augmenter filtre davantage les sons faibles |
| `TOP_N_CLASSES` | `5` | La classe recherchée doit figurer parmi ces premiers résultats |
| `BARK_CLASS_NAME` | `Dog` | Catégorie recherchée |
| `CONSECUTIVE_BARKS` | `2` | Blocs positifs consécutifs nécessaires au déclenchement |
| `RECORD_DURATION` | `60` | Historique audio avant le déclenchement, en secondes |
| `RECORD_QUIET_SECONDS` | `10` | Délai sans détection avant la fin d’un enregistrement |
| `SESSION_GAP_SECONDS` | `90` | Délai sans détection avant la fin d’une session statistique |
| `MIN_BARKS_PER_SESSION` | `2` | Détections minimales pour journaliser une session |
| `MIN_SESSION_DURATION` | `0` | Durée minimale d’une session statistique, en secondes |

Le volume est un seuil numérique, pas une mesure en décibels. L’application ne
modifie pas le gain matériel du micro, qui dépend des réglages du système.
Aucun seuil minimal de confiance YAMNet n’est imposé en plus du classement.

</details>

## Architecture et développement

Le projet utilise **FastAPI, Jinja2, SQLAlchemy et Alembic**. Le frontend est
organisé en **Web Components natifs**, avec des modules JavaScript locaux.
Aucune compilation frontend ni ressource CDN n’est nécessaire.

- [Architecture, repères Laravel et conventions](docs/ARCHITECTURE.md)
- [Migration depuis la v1, vérifications et retour arrière](docs/MIGRATION.md)

```text
app/controllers/       Requêtes et réponses HTTP
app/schemas.py         Validation et contrats de l’API
app/models/            Modèles SQLAlchemy
app/services/          Règles métier : statistiques, audio, musique, séries
app/infrastructure/    SQLite, YAMNet et journaux systemd
app/templates/         Layout Jinja2 et fragments HTML par composant
app/static/js/         Composants interactifs et modules partagés
app/migrations/        Migrations Alembic
```

Pour travailler uniquement sur le dashboard, sans TensorFlow ni microphone :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
# Renseigner DASHBOARD_PIN dans .env
.venv/bin/python -m app.cli web --host 127.0.0.1
```

Le détecteur nécessite l’extra `detector` (installé par `requirements.txt`).
Après une modification Python, relancer le processus concerné. Les modules
JavaScript et les vues ne demandent pas de build. La documentation de l’API est
accessible sur `/docs` après connexion au dashboard.

## Données et commandes

```text
data/
├── bark.sqlite3       # Détections, séries, musique, audio indexé et monitoring
├── recordings/        # WAV terminés et fichiers temporaires .wav.part
├── music/             # Playlist locale et position de rotation
├── logs/              # Journaux historiques v1 conservés pour la migration
└── backups/before-v2/  # Métadonnées historiques sauvegardées avant import
```

Les fichiers audio restent sur disque. Le dashboard lit les statistiques dans
SQLite ; il ne reparcourt pas les anciens journaux à chaque actualisation.
Un WAV en cours d’écriture n’est publié et indexé qu’une fois terminé.

```bash
# Appliquer le schéma et importer l’historique sans doublons
.venv/bin/python -m app.cli migrate

# Comparer les données historiques aux données importées
.venv/bin/python -m app.cli verify

# Réindexer les WAV ajoutés ou supprimés manuellement
.venv/bin/python -m app.cli sync

# Lancer chaque processus séparément
.venv/bin/python -m app.cli web
.venv/bin/python -m app.cli detector
```

Le schéma et l’import sont aussi préparés au démarrage. Lors du passage d’une
installation v1 à la v2, utiliser l’installateur décrit dans le guide de migration
pour arrêter les anciens producteurs avant le dernier import.

Sauvegarder le dossier `data/` complet lorsque les services sont arrêtés, ou
utiliser la sauvegarde SQLite pour une base active. `.env` reste séparé et privé.

## Vérifications

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Les tests utilisent des données temporaires. Ils couvrent l’authentification,
les requêtes audio partielles, les statistiques, les sessions, les enregistrements,
la musique, la migration et le monitoring, sans microphone ni chargement de YAMNet.
Les tests audio nécessitent NumPy et SoundFile (extra `detector`). Pour les tests
web seuls : `python -m unittest discover -s tests -p test_web_server.py -v`.

Un test navigateur optionnel utilise Firefox sur Linux et des données de démonstration :

```bash
.venv/bin/python -m pip install -e '.[dev,browser]'
.venv/bin/python tests/browser_smoke.py
```

Il vérifie les composants, les filtres, les lecteurs et la connexion, puis met
à jour les captures de `docs/images/` sans utiliser les données réelles.

## Origine et licence

Ce projet est un fork de [SteveJ71/bark-detector](https://github.com/SteveJ71/bark-detector),
adapté à un usage quotidien sur Raspberry Pi avec une interface web mobile.
Il est distribué sous [licence MIT](LICENSE).

Les deux services redémarrent indépendamment. Le dashboard reste consultable
même lorsque le détecteur est arrêté.
Avant chaque musique, le lecteur vérifie la connexion Bluetooth à l’Acton III,
tente de la reconnecter, attend sa sortie PipeWire et la sélectionne par défaut.
Si l’enceinte est indisponible, la lecture est annulée et la cause apparaît dans
la chronologie du journal. Ces opérations se font dans le processus de lecture,
sans bloquer la détection. L’enceinte doit être allumée et déjà appairée.

La page « Diagnostic » (`/logs`), accessible depuis le journal et protégée par le
même accès, affiche les 200 dernières lignes du détecteur ou de l’interface web.
Elle s’actualise toutes les deux secondes, avec pause et suivi automatique.
Le service dashboard utilise le groupe `systemd-journal` pour lire ces journaux.

## Écouter la maison et parler en direct

L’onglet **Direct** utilise le micro déjà ouvert par le détecteur et l’enceinte
Bluetooth configurée par `BARK_SPEAKER_ADDRESS`. Clique sur **Écouter la maison**,
puis maintiens **Maintenir pour parler**. Le navigateur demande l’accès au micro
de ton appareil la première fois. Relâche le bouton pour reprendre l’écoute.
La voix interrompt la musique automatique en cours. Le direct ne crée aucun
fichier audio supplémentaire. Les enregistrements déclenchés par le détecteur
continuent à utiliser le micro de la maison.

1. Installe l’extension audio sur le Pi avec `.venv/bin/python -m pip install -e '.[live]'`.
   La sortie voix utilise `pw-cat` et l’enceinte doit être appairée dans la session
   PipeWire de l’utilisateur des services.
2. Ajoute `LIVE_AUDIO_ENABLED=true` dans `.env`. Le niveau de la voix est réglable
   avec `LIVE_VOICE_VOLUME_PERCENT` (30 par défaut).
3. Redémarre les services `bark-detector` et `bark-dashboard`. Une seule session
   audio est ouverte à la fois et elle prend fin après dix minutes.

### Accès à distance avec Cloudflare

- Si `cloudflared` tourne sur le Pi, configure le tunnel vers
  `http://127.0.0.1:8080` avec `HOST=127.0.0.1` et `COOKIE_SECURE=true` dans
  `.env`. Conserve le nom d’hôte public dans l’en-tête HTTP `Host` et protège
  l’ensemble du domaine avec Cloudflare Access. Le navigateur utilise l’URL
  HTTPS pour demander l’accès au micro du téléphone.
  [Tunnel](https://developers.cloudflare.com/tunnel/get-started/) ·
  [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
- Pour une connexion hors du Wi-Fi, configure aussi une clé **Cloudflare Realtime
  TURN** et renseigne `LIVE_TURN_KEY_ID` et `LIVE_TURN_KEY` côté Pi, puis redémarre
  le tableau de bord. Le tunnel fournit l’accès HTTPS et la signalisation.
  WebRTC utilise un chemin direct si possible ou fait passer l’audio par TURN.
  Le tableau de bord génère des identifiants temporaires, et la clé reste sur
  le Pi. [Cloudflare Realtime TURN](https://developers.cloudflare.com/realtime/turn/generate-credentials/)
