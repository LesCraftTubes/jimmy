"""Commande pour Claude : demander un travail de lecture / recherche à l'IA locale de Jimmy.  Usage : jimmy_local.py ask "question" """
import sys

import local_server

if __name__ == "__main__":
    sys.exit(local_server.main())
