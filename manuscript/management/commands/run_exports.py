import csv
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from manuscript.resources import (
    LocationResource,
    LocationAliasResource,
    FolioResource,
    SingleManuscriptResource,
    StanzaResource,
    StanzaTranslatedResource,
)


class Command(BaseCommand):
    help = "Export records to storage backend for public download"

    def handle(self, *args, **options):
        export_targets = [
            (FolioResource(), "exports/folios.csv"),
            (SingleManuscriptResource(), "exports/manuscripts.csv"),
            (StanzaResource(), "exports/stanzas.csv"),
            (StanzaTranslatedResource(), "exports/translated_stanzas.csv"),
            (LocationResource(), "exports/toponyms.csv"),
            (LocationAliasResource(), "exports/toponym_variants.csv"),
        ]

        for resource_class, file_path in export_targets:
            self.stdout.write(f"Exporting {file_path}...")
            dataset = resource_class.export()
            csv_data = dataset.csv

            # since AWS_S3_FILE_OVERWRITE = False, delete the old version first
            if default_storage.exists(file_path):
                default_storage.delete(file_path)

            # save to default storage
            default_storage.save(file_path, ContentFile(csv_data))

        self.stdout.write(
            self.style.SUCCESS("Successfully updated all public exports.")
        )
