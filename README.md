# La Sfera

A Django-based digital humanities application for analyzing and presenting manuscript variations of historical texts, developed by the [Roy Rosenzweig Center for History and New Media](https://rrchnm.org).

## Features

- **Manuscript Management**: Track and compare textual variations across multiple manuscript sources
- **Line Code System**: Hierarchical numbering system for precise text referencing (Book.Stanza.Line format)
- **Translation Support**: Multi-language manuscript versions with variant tracking
- **Image Viewer**: Integrated Mirador viewer for manuscript images
- **Geographic Data**: Location tracking for manuscript origins and holdings
- **Content Management**: Wagtail CMS for managing static pages and content

## Technology Stack

- **Backend**: Django 5.0.2 with Python 3.11
- **Database**: PostgreSQL
- **Frontend**: Django templates with Tailwind CSS
- **CMS**: Wagtail
- **Authentication**: Django Allauth
- **API**: Django REST Framework

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL
- Node.js (for Tailwind CSS)
- Poetry

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd lasfera-app
   ```

2. Install dependencies:
   ```bash
   poetry install
   poetry shell
   ```
   > Note: In Poetry version 2+, it is required to install the [shell plugin](https://github.com/python-poetry/poetry-plugin-shell) before using `poetry shell`.

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your database and other settings
   ```

4. Run migrations:
   ```bash
   python manage.py migrate
   ```

5. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

6. Start the development server:
   ```bash
   python manage.py runserver
   ```

7. In another terminal, install NPM dependencies and start Tailwind CSS watcher:
   ```bash
   npm install
   cd theme/static_src
   npm install
   cd ../..
   python manage.py tailwind start
   ```

Visit `http://localhost:8000` to see the application.

## Documentation

For detailed development documentation, see [DEVNOTES.rst](DEVNOTES.rst).

Database schema documentation is available at: https://dbdocs.io/hepplerj/lasfera

## License

This project is developed for academic research purposes at the Roy Rosenzweig Center for History and New Media.
