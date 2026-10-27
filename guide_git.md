# Guide Git du projet

**`main` = la version de référence, toujours propre et qui marche.** On n'y travaille
jamais directement. Chacun travaille sur SA branche, et on fait remonter vers `main`
seulement ce qui est fini et testé. Ta branche reste ton espace sûr tant que tu n'as
pas poussé.

## Le cycle de travail (à partager au groupe)

**1. Avant de commencer à travailler — toujours partir à jour**

```
git checkout main
git pull
git checkout victoria      # ta branche (remplace par ton prénom)
git merge main             # tu récupères le travail des autres dans ta branche
```

Ce réflexe évite 90 % des conflits : tu travailles toujours sur une base récente.

**2. Pendant le travail — committe souvent sur ta branche**

```
git add .
git commit -m "message clair"
git push                   # sauvegarde ta branche sur GitHub (sécurité)
```

Pousser ta branche régulièrement = ton travail est sauvegardé même si ton PC lâche.

**3. Quand une partie est finie et testée — la faire remonter dans main**

```
git checkout main
git pull                   # au cas où quelqu'un a poussé entre-temps
git merge victoria         # tu intègres ton travail (remplace par ton prénom)
git push
```

## Les 4 règles d'or pour la sécurité

1. **Ne jamais coder directement sur `main`.** On y arrive seulement par un `merge`
   depuis une branche. `main` reste ainsi toujours fonctionnelle.
2. **Ne remonter dans `main` que du travail qui marche.** Un script à moitié fini
   reste sur ta branche. `main` ne doit jamais être cassée — c'est la base commune.
3. **`git pull` avant chaque `merge` vers main.** Quelqu'un a peut-être poussé
   entre-temps. Tu pars toujours de la dernière version.
4. **Chacun ne touche qu'à ses fichiers.** Répartis par source (FSI, BCE,
   World Bank…), vous modifiez des fichiers différents → quasi aucun conflit.

## Dépannage (messages fréquents)

**Un éditeur s'ouvre pendant un merge** (« please enter a commit message ») :
le message par défaut suffit. Si c'est l'éditeur **Vim** dans le terminal, appuie
sur **Échap**, tape **`:wq`** puis **Entrée**. Si c'est un onglet VS Code, ferme-le.

**« Deletion of directory 'scripts' failed. Should I try again? »** au changement
de branche : réponds **non**, ce n'est pas grave. Ça arrive quand un dossier existe
sur une branche mais pas sur l'autre (souvent bloqué par OneDrive ou VS Code).
Le message disparaît une fois que les deux branches ont le même dossier
(fais `git merge main` dans ta branche).

**Vérifier où tu en es à tout moment :**

```
git status
```

« nothing to commit, working tree clean » = tout est propre et à jour.
