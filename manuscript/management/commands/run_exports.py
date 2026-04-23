import csv
import tempfile

from django.core.management.base import BaseCommand
from django.core.files.base import File
from django.core.files.storage import default_storage
from manuscript.resources import (
    LocationResource,
    LocationAliasResource,
    FolioResource,
    SingleManuscriptResource,
    StanzaResource,
    StanzaTranslatedResource,
)
from textannotation.resources import TextualVariantResource


class Command(BaseCommand):
    help = "Export records to storage backend for public download"

    def handle(self, *args, **options):
        export_targets = [
            (SingleManuscriptResource, "exports/manuscripts.csv"),
            (FolioResource, "exports/folios.csv"),
            (StanzaResource, "exports/stanzas.csv"),
            (StanzaTranslatedResource, "exports/translated_stanzas.csv"),
            (TextualVariantResource, "exports/textual_variants.csv"),
            (LocationResource, "exports/toponyms.csv"),
            (LocationAliasResource, "exports/toponym_variants.csv"),
        ]

        for resource_class, file_path in export_targets:
            self.stdout.write(f"Exporting {file_path}...")

            resource = resource_class()

            # stream CSV file to disk instead of RAM
            with tempfile.NamedTemporaryFile(
                mode="w+", newline="", encoding="utf-8"
            ) as temp_file:
                # write headers
                writer = csv.writer(temp_file)
                export_fields = resource.get_export_fields()
                writer.writerow([field.column_name for field in export_fields])

                # chunk queryset to csvwriter
                queryset = resource.get_queryset().iterator(chunk_size=2000)
                for obj in queryset:
                    row_data = [
                        resource.export_field(field, obj) for field in export_fields
                    ]
                    writer.writerow(row_data)

                # at the end, reset file pointer
                temp_file.seek(0)

                # since AWS_S3_FILE_OVERWRITE = False, delete the old version first
                if default_storage.exists(file_path):
                    default_storage.delete(file_path)

                # save the temp file to default storage
                default_storage.save(file_path, File(temp_file))

        self.stdout.write(
            self.style.SUCCESS("Successfully updated all public exports.")
        )
