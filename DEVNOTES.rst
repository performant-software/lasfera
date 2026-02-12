La Sfera Development Documentation
===================================

La Sfera is a Django-based digital humanities application for analyzing and presenting manuscript variations of historical texts. The project is built for the Roy Rosenzweig Center for History and New Media.

Project Architecture
====================

Technology Stack
----------------
- **Backend**: Django 5.0.2 with Python 3.11
- **Database**: PostgreSQL
- **Frontend**: Django templates with Tailwind CSS
- **Content Management**: Wagtail CMS
- **Authentication**: Django Allauth
- **API**: Django REST Framework
- **Development Tools**: Poetry for dependency management

Core Applications
=================

manuscript/
-----------
The heart of the application, handling manuscript data and textual variants.

**Key Models**:

- ``LineCode``: Manages line numbering system (format: "BB.SS.LL")
- ``Library``: Manuscript holding institutions
- ``Codex``: Individual manuscript records
- ``Stanza``: Text units with versioning
- ``StanzaTranslated``: Translated versions of stanzas
- ``Folio``: Manuscript page/folio information
- ``SingleManuscript``: Complete manuscript entities
- ``Location``: Geographic data for manuscript origins
- ``AuthorityFile``: Controlled vocabulary management

**Key Features**:

- Line code validation and parsing
- Manuscript-to-manuscript variation tracking
- Multi-language support for translations
- Tify viewer integration for manuscript images

accounts/
---------
User authentication and account management using Django's built-in auth system extended with Allauth.

gallery/
--------
Image gallery functionality for manuscript images and other visual materials.

pages/
------
Wagtail-powered CMS pages for static content management.

textannotation/
---------------
Text annotation and markup functionality.

theme/
------
Tailwind CSS theme and static asset management.

Configuration & Settings
========================

config/
-------
**settings.py**: Main Django configuration

- PostgreSQL database configuration
- Wagtail CMS setup
- REST Framework configuration
- Tailwind CSS integration
- Authentication backends
- Media and static file handling

**urls.py**: URL routing configuration

- Admin interface routes
- API endpoints
- Wagtail CMS routes
- Application-specific URL includes

Data Management
===============

Database Schema
---------------
An auto-generated documentation for the database is hosted on dbdocs.io at: https://dbdocs.io/hepplerj/lasfera

Key Data Concepts:

- **Line Codes**: Hierarchical numbering system (Book.Stanza.Line format)
- **Manuscript Variants**: Tracks differences between manuscript versions
- **Geographic Data**: Location information with authority control
- **Translation Management**: Multiple language versions of texts

Import/Export
-------------
The application includes Django Import/Export functionality for data management, particularly useful for bulk manuscript data operations.

Templates & Frontend
====================

Template Structure
------------------
- ``base.html``: Main template with navigation and layout
- ``index.html``: Homepage with image grid and project overview
- ``manuscripts.html``: Manuscript browse and search interface
- ``manuscript_single.html``: Individual manuscript detail view
- ``stanzas.html``: Text comparison and variant display
- Wagtail templates for CMS pages

Static Assets
-------------
- Tailwind CSS for styling
- FontAwesome icons
- Custom JavaScript for interactive features
- Tify viewer for manuscript images

Development Workflow
====================

Environment Setup
-----------------
1. Python 3.11 with Poetry for dependency management
2. PostgreSQL database
3. Node.js for Tailwind CSS compilation
4. Environment variables in ``.env`` file

Key Commands
------------
- ``python manage.py runserver``: Start development server
- ``python manage.py migrate``: Apply database migrations
- ``python manage.py collectstatic``: Collect static files
- ``python manage.py tailwind start``: Start Tailwind CSS watcher
- ``python manage.py createsuperuser``: Create admin user

Data Import
-----------
The ``manuscript/fixtures/`` directory contains various JSON files for seeding the database with manuscript data.

It can be used with ``python manage.py loaddata``, with a few steps to perform first.

First, after running migrations with ``python manage.py migrate``, run ``flush`` to completely empty the database:

.. code-block:: bash

    python manage.py flush

Then, the "en" locale must be created for Wagtail:

.. code-block:: bash

    python manage.py shell

.. code-block:: python

    from wagtail.models import Locale
    Locale.objects.get_or_create(language_code="en")

Finally, run ``loaddata``:

.. code-block:: bash
    
    python manage.py loaddata manuscript/fixtures/all_data.json -v 3


Production Considerations
=========================

Deployment
----------
- Docker configuration available (``Dockerfile``, ``docker-compose.yml``)
- Static file collection for production
- PostgreSQL database required
- Environment-specific settings via environment variables

Security
--------
- SECRET_KEY management via environment variables
- CSRF protection configured
- Authentication required for admin functions
- Proper static file handling

Performance
-----------
- Database indexing on key fields
- Static file optimization
- Tailwind CSS purging for production builds
