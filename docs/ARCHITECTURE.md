# Architecture et conventions

Le projet est un monolithe Python avec deux processus : le web et le détecteur.
Ils partagent une base SQLite et les fichiers audio, sans passer par HTTP pour
enregistrer les détections. Le web ne charge jamais TensorFlow.

## Repères pour un développeur Laravel

| Laravel | Ce projet |
| --- | --- |
| Routes / controllers | `app/controllers/` : routeurs FastAPI et fonctions courtes |
| Form Requests / API Resources | `app/schemas.py` : contrats Pydantic |
| Eloquent | `app/models/` : modèles SQLAlchemy ; requêtes explicites avec `select` |
| Services | `app/services/` : règles métier sans dépendance à HTTP |
| Blade / components | `app/templates/` : héritage Jinja2 et fragments HTML |
| Composants interactifs | `app/static/js/components/` : Web Components natifs |
| Container | `app/dependencies.py` et `Depends` |
| Configuration | `app/config.py` : Settings, variables d’environnement et `.env` |
| Artisan | `python -m app.cli` ou `bark` après installation |
| Migrations | Alembic dans `app/migrations/versions/` |

## Circulation d’une requête

1. Le middleware vérifie la session et l’origine des mutations.
2. FastAPI valide les paramètres ; le contrôleur choisit le service.
3. Le service applique les règles ou construit une vue des données via SQLAlchemy.
4. Le contrôleur renvoie un contrat JSON Pydantic ou une vue Jinja2.

Les contrôleurs ne lisent pas les journaux historiques pour calculer les statistiques.
`Dashboard.snapshot()` agrège les tables SQL. Les seules lectures de fichiers
pendant une requête concernent les ressources statiques et l’audio demandé.
Les journaux techniques passent par l’adaptateur `infrastructure/journal.py`,
limité aux deux unités systemd de l’application.

## Organisation

```text
app/
├── main.py                  # Composition, middleware, cycle de vie
├── config.py                # Configuration commune et validée
├── cli.py                   # Commandes web / detector / migrate / verify / sync
├── detector.py              # Boucle audio et coordination des services
├── music_player.py          # Sous-processus Bluetooth / volume / ffplay
├── dependencies.py          # Points d’injection HTTP
├── schemas.py               # Entrées et sorties HTTP
├── controllers/             # Auth, dashboard, audio, logs et pages
├── models/                  # Tables SQLAlchemy
├── services/                # Statistiques, historique, sessions, audio, musique
├── infrastructure/          # Connexions SQLite, YAMNet, journald
├── migrations/              # Versions du schéma Alembic
├── templates/components/    # Fragments Jinja2
└── static/js/components/    # Composants interactifs
```

## Frontend par composants

Le HTML initial est rendu par Jinja2, avec un layout partagé et des fragments
lisibles par section. Le navigateur améliore ces sections avec des composants
natifs : aucun CDN, gestionnaire Node ou compilation n’est nécessaire.

| Composant | Responsabilité |
| --- | --- |
| `bark-dashboard` | Filtres, requêtes et actualisation ; distribue les données |
| `bark-health` | État du détecteur |
| `bark-metrics` | Compteurs et durée d’écoute |
| `bark-activity` | Activité de la journée |
| `bark-recordings` | Liste des lecteurs, conservés par nom de fichier |
| `bark-recording` | Un lecteur, sa courbe, son curseur et son téléchargement |
| `bark-music` | Événements du lecteur de musique |
| `bark-history` | Choix d’une journée ; événement `select-date` |
| `bark-trends` | Graphiques et calendrier sur 7 / 30 jours |

Chaque composant de présentation reçoit ses données par `update(data)`.
Il ne modifie que son propre DOM. Les sélecteurs sont locaux au composant.
Les événements entre composants sont des `CustomEvent` ; les données circulent
depuis le coordinateur vers les composants enfants.

Les lecteurs ont une identité stable : un rafraîchissement ne recrée pas un
lecteur existant. La courbe est chargée à l’approche du viewport. Retirer un
lecteur arrête son audio, son observateur et sa requête.
Les requêtes de statistiques obsolètes sont annulées ; seules les réponses
correspondant aux filtres actuels peuvent mettre à jour la page.

Le CSS partagé reste dans `app/static/css/style.css`. Les composants utilisent
le DOM normal pour partager les styles et les règles d’accessibilité.

## Détection et stockage

- `Yamnet.classify()` isole le modèle et son chargement des règles métier.
- `SessionTracker` regroupe les détections avec une horloge monotone pour les délais.
- `History` écrit les événements métier dans des transactions courtes.
- `DetectorMonitor` comptabilise uniquement les échantillons traités et publie
  son état environ toutes les cinq secondes.
- `BarkRecorder` écrit progressivement un `.wav.part`, puis le publie par renommage.
  Son callback indexe uniquement le WAV terminé.
- Le processus de lecture vérifie Bluetooth et volume avant de lancer `ffplay`.

SQLite utilise WAL et un délai d’attente de dix secondes. Chaque opération
ouvre sa propre session SQLAlchemy ; aucune session n’est partagée entre threads.
Les mises à jour du schéma et les imports sont sérialisés par un verrou de fichier.
Un autre verrou empêche deux détecteurs v2 d’utiliser le même répertoire de données.

Les fichiers historiques sont importés au démarrage ou par commande. Ils restent
en place pour la sauvegarde et le retour arrière. Les nouvelles données sont
écrites uniquement dans `bark.sqlite3` ; les logs techniques restent dans journald.

## Ajouter une fonctionnalité

1. Écrire la règle dans un service, et la vérifier avec des données temporaires.
2. Ajouter un modèle et une migration uniquement si de nouvelles données persistent.
3. Définir le contrat HTTP dans `schemas.py`, puis une route courte dans `controllers/`.
4. Ajouter le fragment Jinja2 et, si nécessaire, son composant JavaScript.
5. Importer le composant depuis le point d’entrée de sa page.

Pour générer une migration après modification des modèles :

```bash
.venv/bin/python -m app.cli revision "ajouter une fonctionnalité"
```

Relire le fichier généré avant application, puis lancer `migrate` sur des données
de test. Les anciennes migrations décrivent leur propre schéma figé ; elles
n’importent pas les modèles courants.

Les anciens fichiers Python à la racine sont des lanceurs ou imports de
compatibilité. Toute nouvelle logique va dans `app/`.

Les commandes se lancent depuis le répertoire du projet : `.env` et `data/`
sont recherchés dans ce répertoire de travail. `DATA_DIR` permet de changer le
stockage. Les variables d’environnement prennent le pas sur `.env`.

Le serveur web est lancé avec un seul processus Uvicorn. Les sessions et délais
de connexion sont en mémoire, comme en v1. Ajouter plusieurs processus web
nécessiterait d’abord de partager ce stockage d’authentification entre eux.
