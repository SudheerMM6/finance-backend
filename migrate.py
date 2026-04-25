#!/usr/bin/env python3
"""
Database migration helper for production.

Usage:
  python migrate.py          # Run pending migrations (used in Render postdeploy)
  python migrate.py init     # Initialize migrations (first time only, local)
  python migrate.py migrate  # Create a new migration after model changes (local)
"""

import os
import sys
from app import create_app, migrate
from flask_migrate import upgrade, init, migrate as migrate_cmd

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        command = sys.argv[1] if len(sys.argv) > 1 else 'upgrade'
        
        if command == 'init':
            # Only run this once to create the migrations folder
            init(directory='migrations', multidb=False)
            print("Migrations initialized. Now run: python migrate.py migrate")
        elif command == 'migrate':
            # Create a new migration after model changes
            migrate_cmd(directory='migrations', message='auto')
            print("Migration created. Review in migrations/versions/")
        elif command == 'upgrade':
            # Run pending migrations - this is the production command
            upgrade(directory='migrations')
            print("Database migrations applied successfully.")
        else:
            print(f"Unknown command: {command}")
            print("Use: init | migrate | upgrade (default)")
            sys.exit(1)
