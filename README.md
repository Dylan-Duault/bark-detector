# Bark Detector

A Python tool for real-time dog bark detection and logging using the [YAMNet](https://tfhub.dev/google/yamnet/1) audio classification model. Listens continuously to a microphone, detects and logs bark events, saves audio recordings of bark sessions, and includes scripts for visualising the data.

## How it works

- Captures audio from a microphone in 1.2-second chunks at 16kHz
- Classifies each chunk using YAMNet (a TensorFlow audio model)
- Detects bark events by volume threshold and class confidence
- Groups individual barks into sessions separated by quiet gaps
- Logs bark events and sessions to a daily text file
- Records after two consecutive positive chunks, including 60 seconds of history, until 10 seconds without detection

## Scripts

| Script | Description |
|---|---|
| `bark_session_logger.py` | Main script — runs real-time detection and logging |
| `diary_writer.py` | Parses log files and writes a human-readable daily summary |
| `diary_plots.py` | Generates heatmap and bar charts from log files |
| `plot_bark_graph.py` | Plots bark frequency over time from log files |
| `batch_waveforms.py` | Generates waveform PNG images from WAV recordings |

## Requirements

- Python 3.10–3.12 (TensorFlow does not yet support Python 3.13+)
- A working microphone
- Git
- ffmpeg (see below)
- Microsoft Visual C++ Redistributable (see below)

## Installing Microsoft Visual C++ Redistributable (Windows)

TensorFlow requires this to be installed on Windows. If you see a DLL load error when running the script, this is the cause.

1. Search Google for **"Microsoft Visual C++ Redistributable latest"** and go to the Microsoft download page
2. Download and install the **x64** version
3. Restart your computer and try again

## Installing ffmpeg (Windows)

1. Go to [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) and download **ffmpeg-release-essentials.zip**
2. Extract the zip to a permanent location, e.g. `C:\ffmpeg`
3. Add the `bin` folder to your system PATH:
   - Search Windows for **"Edit the system environment variables"**
   - Click **Environment Variables**
   - Under **System variables**, select **Path** → **Edit**
   - Click **New** and add the path to the bin folder, e.g. `C:\ffmpeg\ffmpeg-7.x-essentials_build\bin`
   - Click OK on all dialogs
4. Open a new terminal and verify:
   ```bash
   ffmpeg -version
   ```

## Installation

```bash
git clone https://github.com/SteveJ71/bark-detector.git
cd bark-detector
py -3.12 -m venv .venv
```

Then activate the virtual environment by typing the following directly in your terminal (this is a terminal command, not a Python command).

Check which terminal you are using — in VS Code look at the dropdown in the top right of the terminal panel:

```bash
# Windows Command Prompt (cmd)
.venv\Scripts\activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Mac / Linux
source .venv/bin/activate
```

Your terminal prompt will change to show `(.venv)` once active. Then install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Real-time bark detection

```bash
python bark_session_logger.py
```

Press `Ctrl+C` to stop. Logs are written to `bark_log_YYYY-MM-DD.txt` in the same folder. WAV recordings are saved in `recordings/` as `bark_audio_YYYY-MM-DD_HH-MM-SS.wav`.

### Daily diary summary

```bash
python diary_writer.py "path/to/log/files"
```

Writes `bark_diary_summary.txt` into the specified folder.

### Heatmap and bar charts

```bash
python diary_plots.py "path/to/logs/2025" "path/to/logs/2026"
```

Saves plots as PNG files in a `Plots/` subfolder. Change `HEATMAP_METRIC` at the top of the file between `"minutes"` and `"barks"` to switch what is graphed.

### Bark frequency graph

```bash
python plot_bark_graph.py "path/to/log/files"
```

Displays an interactive plot of bark frequency over time across all logged days.

### Waveform images

```bash
python batch_waveforms.py "path/to/wav/files"
```

Generates a `_waveform.png` alongside each WAV file. Skips files that already have a PNG.

## Configuration

Key constants in `bark_session_logger.py` can be adjusted to suit your environment:

| Constant | Default | Description |
|---|---|---|
| `MIN_BARK_VOLUME` | `0.012` | Minimum audio volume to count as a bark — increase to filter out distant dogs |
| `SESSION_GAP_SECONDS` | `90` | Quiet gap (seconds) that ends a bark session |
| `MIN_SESSION_DURATION` | `0` | Minimum session length (seconds) to be logged |
| `MIN_BARKS_PER_SESSION` | `2` | Minimum bark count for a session to be logged |
| `RECORD_DURATION` | `60` | Audio history retained before the trigger (seconds) |
| `RECORD_QUIET_SECONDS` | `10` | Quiet gap before saving a complete recording (seconds) |
| `CONSECUTIVE_BARKS` | `2` | Consecutive positive 1.2-second chunks required to save audio |

## Output files

| File | Description |
|---|---|
| `bark_log_YYYY-MM-DD.txt` | Daily log of individual barks and sessions |
| `recordings/bark_audio_YYYY-MM-DD_HH-MM-SS.wav` | Audio recording of a bark session |
| `bark_diary_summary.txt` | Human-readable summary of bark sessions |
| `Plots/bark_heatmap_*.png` | Heatmap of barking by day and hour |
| `Plots/bark_daily_totals_*.png` | Bar chart of daily barking totals |
| `Plots/bark_hourly_profile_*.png` | Bar chart of barking by hour across all days |

### Configuration locale : deux détections consécutives

Lancer avec `.venv/bin/python bark_session_logger.py` sous Linux. Le premier
lancement télécharge YAMNet et nécessite Internet. Sous Linux, PortAudio doit
être installé (paquet `libportaudio2` sous Debian/Ubuntu).

Deux blocs consécutifs de 1,2 seconde classés comme chien déclenchent
l’enregistrement. Celui-ci inclut jusqu’aux 60 secondes précédentes et se poursuit
jusqu’à 10 secondes sans détection. Chaque nouvelle détection, même isolée,
repousse cette échéance. Une pause plus courte reste dans le même fichier.
Le WAV final apparaît dans `recordings/` une fois terminé, sans limite horaire.
L’audio est écrit progressivement sur disque ; seuls l’historique et les blocs
en attente restent en mémoire. Un arrêt propre du service sauvegarde aussi
l’enregistrement en cours. Les fichiers temporaires `.wav.part` sont masqués dans
l’interface ; une coupure de courant peut laisser un fichier temporaire incomplet.
Le modèle détecte des blocs contenant un chien, pas chaque aboiement individuel :
deux aboiements dans un seul bloc peuvent ne pas déclencher la sauvegarde.

## Tableau de bord web (mobile)

Le détecteur conserve **la dernière minute avant le déclenchement**, puis toute
la série d’aboiements et les 10 secondes sans détection qui la terminent.
Si le programme tourne depuis moins d’une minute, seul l’historique disponible
est inclus. Le nom du fichier indique l’heure du déclenchement. Les anciens
fichiers restent consultables, avec leur durée et leur contenu d’origine.

Dans un premier terminal, lancer le détecteur :

```bash
.venv/bin/python bark_session_logger.py
```

Avant le premier lancement, copier `.env.example` vers `.env`, puis définir
`DASHBOARD_PIN` avec un code de quatre chiffres. Le serveur refuse de démarrer
sans un code valide. Ne jamais publier `.env`.

Dans un second terminal, lancer la page web (Python standard, sans dépendance web) :

```bash
.venv/bin/python web_server.py
```

Sur cette machine : **http://localhost:8080**.
Sur le téléphone connecté au **même Wi-Fi** : **http://IP-DE-LA-MACHINE:8080**.
Sous Linux, `hostname -I` permet de trouver l’adresse locale, par exemple
`192.168.1.42`, soit `http://192.168.1.42:8080`. Autoriser le port TCP 8080 sur le
réseau local dans le pare-feu si nécessaire. Les deux programmes doivent rester
lancés et la machine éveillée.

La page propose :

- les détections, sessions terminées, durée des sessions et nombre de fichiers ;
- les détections heure par heure, un sélecteur de date et l’historique des jours ;
- l’écoute audio avec déplacement dans le fichier et téléchargement ;
- une actualisation toutes les 30 secondes qui préserve la lecture en cours.

Les détections sont des blocs audio de 1,2 seconde, pas un comptage exact des
aboiements. Les durées concernent les sessions terminées et incluent les pauses
entre aboiements d’une même session. Une session apparaît après 90 secondes de
calme. Les anciens fichiers WAV restent consultables avec leur durée d’origine.

Le serveur lit les logs et WAV existants à chaque actualisation ; il peut donc
être utilisé sans lancer le détecteur pour consulter l’historique. Aucun fichier
n’est envoyé vers un service externe. L’accès exige le code défini dans `.env`,
y compris pour les statistiques et les fichiers audio. Le serveur HTTP est prévu
pour un réseau local de confiance : ne pas ouvrir ce port sur Internet.
Pour un accès limité à cette machine :

```bash
.venv/bin/python web_server.py --host 127.0.0.1
```

Options : `--port 8080`, `--data-dir /chemin/vers/le/dossier-de-donnees`.
Vérifications : `python3 -m unittest discover -s tests -v`.

## Démarrage automatique sur Raspberry Pi

Après installation des dépendances dans `.venv` et configuration du code dans `.env`, exécuter depuis le dépôt :

```bash
sudo .venv/bin/python install_services.py
```

L’installateur utilise le compte qui a lancé `sudo`, le chemin réel du dépôt et
son environnement `.venv`. Il active et démarre deux services indépendants :
`bark-detector` (microphone) et `bark-dashboard` (page web sur le port 8080).
Ils démarrent sans ouverture de session et redémarrent automatiquement en cas
d’arrêt. Le compte du service a accès au groupe `audio`. Un micro USB/ALSA est
recommandé pour fonctionner sans session graphique. Le premier démarrage
nécessite Internet pour télécharger YAMNet ; le modèle est ensuite mis en cache
dans `/var/cache/bark-detector/yamnet`.

Ne pas lancer une deuxième instance manuelle du détecteur en parallèle.

```bash
# État et journaux
systemctl status bark-detector bark-dashboard
journalctl -u bark-detector -u bark-dashboard -f

# Redémarrer après une modification du code
sudo systemctl restart bark-detector bark-dashboard

# Arrêter et désactiver le démarrage automatique
sudo systemctl disable --now bark-detector bark-dashboard
```

Après déplacement du dépôt, relancer l’installateur. Pour choisir un autre
compte : `sudo .venv/bin/python install_services.py --user NOM`.
Pour générer les unités sans les installer :
`python3 install_services.py --output-dir /tmp/bark-services`.
La page est accessible via `http://raspberrypi.local:8080` si le réseau prend en
charge mDNS, ou via l’adresse IP locale du Pi.

Les fichiers audio sont stockés dans `recordings/`, créé automatiquement par le
détecteur. Le serveur lit les journaux à la racine du dossier de données et les
WAV dans son sous-dossier `recordings/`.

### Graphiques sur 7 ou 30 jours

Les graphiques couvrent la période qui se termine à la date sélectionnée :
barres du temps quotidien en sessions terminées, calendrier des détections par
jour et heure, et détections horaires cumulées. Toucher une barre ou une case
sur mobile affiche le détail. Le calendrier se fait défiler horizontalement.
Les jours sans journal sont hachurés ; la présence d’un journal ne garantit pas
une journée complète d’écoute. La journée en cours et ses sessions sont partielles.

### Code d’accès à l’interface

Définir `DASHBOARD_PIN` dans `.env` à la racine du dépôt : exactement quatre
chiffres, y compris les éventuels zéros initiaux. `.env` est ignoré par Git.
Le code n’est transmis ni dans les URL, ni dans le JavaScript ou les journaux.
Après modification : `sudo systemctl restart bark-dashboard`.

Chaque échec impose une attente par adresse IP de 2, 4, 8, 16, 32 puis 60 secondes.
Le serveur refuse aussi un code correct tant que le délai n’est pas écoulé.
Une connexion réussie remet le compteur à zéro. Les délais et sessions sont
conservés en mémoire et réinitialisés au redémarrage du serveur.

La session expire après 12 heures ou lors de la déconnexion. Le cookie est
`HttpOnly` et `SameSite=Strict`. La page, les statistiques et les enregistrements
exigent une session valide ; l’écran de connexion et son style restent publics.
Sur le serveur HTTP local, le code et le cookie ne sont pas chiffrés en transit.
