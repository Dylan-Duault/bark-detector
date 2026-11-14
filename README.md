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
sudo .venv/bin/python install_services.py
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
Les jours sans journal sont hachurés ; un journal présent ne garantit pas une
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
.venv/bin/python bark_session_logger.py
.venv/bin/python web_server.py
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
python3 install_services.py --output-dir /tmp/bark-services
```

</details>

<details>
<summary>Ajuster la sensibilité et les durées</summary>

Les constantes se trouvent dans `bark_session_logger.py`. Après modification,
redémarrer `bark-detector`.

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

## Organisation du projet

| Fichier ou dossier | Usage |
| --- | --- |
| `bark_session_logger.py` | Détection et journaux utilisés par les statistiques |
| `audio_recording.py` | Tampon audio et écriture des enregistrements |
| `web_server.py` | Serveur HTTP, statistiques et lecture audio |
| `dashboard_auth.py` | Code d’accès, sessions et délais |
| `storage.py` | Emplacement commun des journaux et enregistrements |
| `detector_monitor.py` | État du détecteur et durée d’écoute mesurée |
| `web/` | Interface mobile, connexion et graphiques |
| `install_services.py`, `systemd/` | Installation et démarrage automatique |
| `yamnet_class_map.csv` | Les 521 catégories du modèle |
| `tests/` | Vérifications audio, statistiques, authentification et installation |
| `docs/images/` | Captures d’écran de l’interface |

L’historique est regroupé dans `data/`, créé automatiquement au démarrage et
entièrement exclu de Git :

```text
data/
├── logs/         # Historique des extraits et séries, un journal par jour
├── recordings/   # Fichiers audio WAV
└── monitoring.sqlite3  # État du détecteur et durées d’écoute par jour et heure
```

Sauvegarder ce dossier pour conserver l’historique en cas de panne de la carte.
Le code d’accès reste dans `.env`, séparé de l’historique et lui aussi exclu de Git :

- `.env` : code d’accès ;
- `data/logs/bark_log_YYYY-MM-DD.txt` : extraits reconnus et séries ;
- `data/recordings/bark_audio_YYYY-MM-DD_HH-MM-SS.wav` : audio terminé, nommé à l’heure
  du déclenchement ;
- `data/recordings/*.wav.part` : enregistrement temporaire, absent de l’interface ;
- `data/monitoring.sqlite3` : état du détecteur et durées d’écoute, conservés après redémarrage.

Le suivi est enregistré environ toutes les 5 secondes, et lors d’un arrêt propre.
Une coupure brutale peut perdre les dernières secondes de mesure.

## Vérifications

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Les tests utilisent des données et serveurs temporaires, sans microphone ni
chargement de YAMNet. TensorFlow est nécessaire au détecteur ; le serveur web
et l’authentification utilisent uniquement Python standard.

## Origine et licence

Ce projet est un fork de [SteveJ71/bark-detector](https://github.com/SteveJ71/bark-detector),
adapté à un usage quotidien sur Raspberry Pi avec une interface web mobile.
Il est distribué sous [licence MIT](LICENSE).
