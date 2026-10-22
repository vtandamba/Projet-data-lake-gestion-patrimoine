#!/usr/bin/env bash
#
# Création des branches de travail par collaborateur
# Projet data lake - gestion patrimoniale
#
# À lancer UNE SEULE FOIS, par une seule personne, depuis la racine du dépôt.
# Chaque collaborateur travaillera ensuite sur sa propre branche.
#
# Usage :  bash creer_branches.sh
#

set -e  # arrête le script à la première erreur

echo "==> Mise à jour de main avant de créer les branches..."
git checkout main
git pull origin main

# Liste des collaborateurs (une branche par prénom)
collaborateurs=("noam" "sonia" "lucas" "douaa" "victoria")

for nom in "${collaborateurs[@]}"; do
    echo ""
    echo "==> Création de la branche : $nom"

    # Si la branche existe déjà en local, on ne la recrée pas
    if git show-ref --verify --quiet "refs/heads/$nom"; then
        echo "    (la branche '$nom' existe déjà en local, ignorée)"
    else
        git branch "$nom"          # crée la branche à partir de main
        echo "    branche '$nom' créée en local"
    fi

    # Pousse la branche sur GitHub (origin) et la relie
    git push -u origin "$nom"
    echo "    branche '$nom' publiée sur GitHub"
done

# On revient sur main à la fin
git checkout main

echo ""
echo "==> Terminé. Branches créées : ${collaborateurs[*]}"
echo "    Chaque personne peut maintenant récupérer sa branche avec :"
echo "        git checkout <son_prénom>"
