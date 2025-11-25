#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from django.core.management import execute_from_command_line

def main():

    from argparse import ArgumentParser

    parser = ArgumentParser(description="Django management command with custom parameters")
    parser.add_argument('--home', dest='home', default=None, help='Specify the home parameter')

    # Parse the command line arguments
    args, unknown = parser.parse_known_args()

    # Set the value of the home parameter in an environment variable
    if args.home:
        os.environ['DJANGO_HOME'] = args.home

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIADUNGPLUS.settings')
    
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
