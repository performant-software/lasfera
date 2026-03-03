from import_export import resources, fields, widgets
from import_export.widgets import ForeignKeyWidget, Widget
from import_export.results import RowResult
from django.contrib import messages
from django.db.models import Q
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)

from .models import (
    EditorialStatus,
    Reference,
    SingleManuscript,
    Folio,
    Stanza,
    Location,
    LocationAlias,
    LineCode,
    StanzaTranslated,
)


class ExportOnlyResource(resources.ModelResource):
    """reusable base class to disable import functionality"""

    def before_import(self, dataset, **kwargs):
        raise NotImplementedError("Importing is disabled for this resource.")

    def import_data(self, dataset, **kwargs):
        raise NotImplementedError("Importing is disabled for this resource.")


class FolioResource(resources.ModelResource):
    """Resource for importing Folio data with proper object logging"""

    manuscript = fields.Field(
        column_name="manuscript",
        attribute="manuscript",
        widget=ForeignKeyWidget(SingleManuscript, "siglum"),
    )

    folio = fields.Field(column_name="folio", attribute="folio_number")

    line_code_range_start = fields.Field(
        column_name="line_code_starts", attribute="line_code_range_start"
    )

    line_code_range_end = fields.Field(
        column_name="next_start_line", attribute="line_code_range_end"
    )

    class Meta:
        model = Folio
        import_id_fields = ["manuscript", "folio"]
        fields = ("manuscript", "folio", "line_code_range_start", "line_code_range_end")
        skip_unchanged = False
        report_skipped = True

    def get_instance(self, instance_loader, row):
        """Get existing instance for a row if it exists"""
        try:
            manuscript = SingleManuscript.objects.get(siglum=row["manuscript"])
            return Folio.objects.get(manuscript=manuscript, folio_number=row["folio"])
        except (SingleManuscript.DoesNotExist, Folio.DoesNotExist):
            return None

    def import_row(
        self, row, instance_loader, using_transactions=True, dry_run=False, **kwargs
    ):
        """Process a single row of folio data"""
        try:
            # Get or create the instance for diff comparison
            instance = self.get_instance(instance_loader, row)

            # Get the manuscript
            manuscript = SingleManuscript.objects.get(siglum=row["manuscript"])

            if not dry_run:
                # Create or update the folio
                folio, created = Folio.objects.update_or_create(
                    manuscript=manuscript,
                    folio_number=row["folio"],
                    defaults={
                        "line_code_range_start": row["line_code_starts"],
                        "line_code_range_end": (
                            row["next_start_line"]
                            if row.get("next_start_line")
                            and row["next_start_line"].strip() != "-"
                            else None
                        ),
                    },
                )

                # Handle stanza associations
                start_line = row["line_code_starts"]
                end_line = row["next_start_line"]

                stanza_query = Q(stanza_line_code_starts__gte=start_line)
                if end_line and end_line.strip() != "-":
                    stanza_query &= Q(stanza_line_code_starts__lt=end_line)

                stanzas = Stanza.objects.filter(stanza_query).order_by(
                    "stanza_line_code_starts"
                )

                folio.stanzas.clear()
                folio.stanzas.add(*stanzas)
            else:
                # For dry run, we still need a folio object for proper logging
                folio = instance or Folio(
                    manuscript=manuscript,
                    folio_number=row["folio"],
                    line_code_range_start=row["line_code_starts"],
                    line_code_range_end=(
                        row["next_start_line"]
                        if row.get("next_start_line")
                        and row["next_start_line"].strip() != "-"
                        else None
                    ),
                )

            # Create result with proper object information
            result = RowResult()

            if instance:
                result.import_type = RowResult.IMPORT_TYPE_UPDATE
                result.diff = [
                    f"{instance.manuscript.siglum}",
                    f"{instance.folio_number}",
                    f"{instance.line_code_range_start or ''} → {row['line_code_starts']}",
                    f"{instance.line_code_range_end or ''} → {row.get('next_start_line', '')}",
                ]
            else:
                result.import_type = RowResult.IMPORT_TYPE_NEW
                result.diff = [
                    row["manuscript"],
                    row["folio"],
                    row["line_code_starts"],
                    row.get("next_start_line", ""),
                ]

            # Set object_id and object_repr for proper logging
            result.object_id = folio.pk if not dry_run else None
            result.object_repr = str(folio)

            return result

        except Exception as e:
            logger.error(f"Error importing folio row: {str(e)}", exc_info=True)
            result = RowResult()
            result.import_type = RowResult.IMPORT_TYPE_ERROR
            result.errors.append(str(e))
            return result

    def get_diff_headers(self):
        """Define headers for the diff display"""
        return ["Manuscript", "Folio", "Start Line", "End Line"]


class SingleManuscriptResource(resources.ModelResource):
    class Meta:
        model = SingleManuscript

    def before_import_row(self, row, **kwargs):
        manuscript = {
            "shelfmark": row.get("shelfmark"),
        }
        manuscript_instance, _ = SingleManuscript.objects.get_or_create(**manuscript)


class ReferenceResource(resources.ModelResource):
    class Meta:
        model = Reference

    def before_import_row(self, row, **kwargs):
        references = {
            "bert": row.get("bert"),
            "reference": row.get("reference"),
            "manuscript": row.get("siglum"),
        }
        references_instance, _ = Reference.objects.get_or_create(**references)


class EditorialStatusResource(resources.ModelResource):
    class Meta:
        model = EditorialStatus
        import_id_fields = ["siglum"]

    def before_import_row(self, row, **kwargs):
        ed_status = {
            "siglum": row.get("siglum"),
            "editorial_priority": row.get("editorial_priority"),
            "collated": row.get("collated"),
            "manuscript": row.get("siglum"),
        }
        ed_status_instance, _ = EditorialStatus.objects.get_or_create(**ed_status)


class LocationResource(resources.ModelResource):
    """Resource for importing main Location/Toponym records"""

    placename_id = fields.Field(column_name="Place_ID", attribute="placename_id")
    name = fields.Field(column_name="HistEng_Name", attribute="name")
    place_type = fields.Field(column_name="Place_Type", attribute="place_type")
    placename_modern = fields.Field(column_name="Mod_Name", attribute="placename_modern")
    placename_ancient = fields.Field(column_name="Anc_Name", attribute="placename_ancient")
    latitude = fields.Field(
        column_name="Latitude", attribute="latitude", widget=widgets.FloatWidget()
    )
    longitude = fields.Field(
        column_name="Longitude", attribute="longitude", widget=widgets.FloatWidget()
    )
    authority_file = fields.Field(column_name="WHG_Link", attribute="authority_file")
    modern_country = fields.Field(column_name="Country", attribute="modern_country")
    description = fields.Field(column_name="Toponym_Text", attribute="description")

    def before_import(self, dataset, **kwargs):
        """Clean the dataset if double headers are detected."""
        self.aliases_created = 0
        if len(dataset) > 0:
            # detect if the first header is the descriptive title row
            first_header = str(dataset.headers[0]) if dataset.headers else ""
            if "SFERA SITE DATA" in first_header or "Place_ID" not in dataset.headers:
                # real headers are in the second row (first "dataset" row)
                dataset.headers = dataset[0]
                # remove them from being read
                del dataset[0]

    def before_import_row(self, row, **kwargs):
        """convert - or N/A to None"""
        null_strings = ["N/A", "n/a", "-"]
        for key in row:
            if isinstance(row[key], str) and row[key].strip() in null_strings:
                row[key] = None

    class Meta:
        model = Location
        import_id_fields = ["placename_id"]
        skip_unchanged = True
        report_skipped = True
        fields = (
            "placename_id",
            "name",
            "place_type",
            "placename_modern",
            "placename_ancient",
            "latitude",
            "longitude",
            "authority_file",
            "modern_country",
            "description",
        )


class UniqueIDWidget(Widget):
    """checks for empty IDs / duplicates within a single imported file"""

    def clean(self, value, row=None, **kwargs):
        if value is None or str(value).strip() == "":
            if row:
                label = str(row.get("Label", "")).strip()
                pid = str(row.get("Place_ID", "")).strip().replace("?", "")
                ms = str(row.get("MS", "")).strip()
                folio = str(row.get("Folio", "")).strip()
                raise ValueError(
                    f"Row is missing an ID. ({label}, place {pid}, ms {ms}, folio {folio})"
                )
            raise ValueError(f"Row is missing an ID.")
        val = str(value).strip()
        if self.resource:
            if row and row.get("_row_seen"):
                return val
            if val in self.resource.seen_import_ids:
                raise ValueError(f"Duplicate ID '{val}' found in this file.")
            self.resource.seen_import_ids.add(val)
            if row:
                row["_row_seen"] = True

        return val


class LocationForeignKeyWidget(ForeignKeyWidget):
    """custom ForeignKeyWidget widget to show a better error message for
    missing locations"""

    def clean(self, value, row=None, **kwargs):
        if value is None or str(value).strip() == "":
            return None
        val = str(value).strip()
        location = self.resource.location_cache.get(val)
        if not location:
            id = row.get("ID")
            raise self.model.DoesNotExist(f'Location not found for ID {id}: "{val}"')
        return location


class ManuscriptForeignKeyWidget(ForeignKeyWidget):
    """custom ForeignKeyWidget widget to show a better error message for
    missing MSS"""

    def clean(self, value, row=None, **kwargs):
        if value is None or str(value).strip() == "":
            return None
        val = str(value).strip()
        ms = self.resource.ms_cache.get(val)
        if not ms:
            id = row.get("ID")
            raise self.model.DoesNotExist(f'Manuscript not found for ID {id}: "{val}"')
        return ms


class FolioForeignKeyWidget(ForeignKeyWidget):
    """custom ForeignKeyWidget widget to ensure we get the folio belonging to
    the correct manuscript"""

    def get_queryset(self, value, row, *args, **kwargs):
        siglum = str(row.get("MS", "")).strip()
        return self.model.objects.filter(folio_number=value, manuscript__siglum=siglum)

    def clean(self, value, row=None, **kwargs):
        if value is None or str(value).strip() == "":
            return None
        val = str(value).strip()
        ms_siglum = str(row.get("MS", "")).strip()
        folio = self.resource.folio_cache.get((ms_siglum, val))
        if not folio:
            ms = row.get("MS")
            id = row.get("ID")
            raise self.model.DoesNotExist(
                f'Folio "{val}" not found for ID {id} (MS "{ms}")'
            )
        return folio


class LocationAliasResource(resources.ModelResource):
    id = fields.Field(column_name="ID", attribute="id", widget=UniqueIDWidget())
    location = fields.Field(
        column_name="Place_ID",
        attribute="location",
        widget=LocationForeignKeyWidget(Location, "placename_id"),
    )
    placename_alias = fields.Field(column_name="Label", attribute="placename_alias")
    manuscript = fields.Field(
        column_name="MS",
        attribute="manuscript",
        widget=ManuscriptForeignKeyWidget(SingleManuscript, "siglum"),
    )
    folio = fields.Field(
        column_name="Folio",
        attribute="folio",
        widget=FolioForeignKeyWidget(Folio, "folio_number"),
    )

    class Meta:
        model = LocationAlias
        fields = ("id", "location", "placename_alias", "manuscript", "folio")
        import_id_fields = ["id"]
        skip_unchanged = True
        report_skipped = True
        use_bulk = True
        batch_size = 500

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # cache manuscripts by siglum to prevent unnecessary sql queries
        self.ms_cache = {}
        # and locations by placename_id
        self.location_cache = {}
        # and folios by a tuple of (ms_siglum, folio_number)
        self.folio_cache = {}
        # allow better error handling for duplicate IDs
        self.seen_import_ids = set()
        for field in self.fields.values():
            field.widget.resource = self

    def before_import(self, dataset, **kwargs):
        """Clean extra rows above the header"""
        found_header = False
        while len(dataset) > 0:
            # look for Place_ID in headers
            if "Place_ID" in dataset.headers:
                found_header = True
                break
            # if the first 'dataset' row contains Place_ID, promote row to headers
            if "Place_ID" in [str(cell) for cell in dataset[0]]:
                dataset.headers = dataset[0]
                del dataset[0]
                found_header = True
                break
            # otherwise, delete row and keep looking
            del dataset[0]
        if not found_header:
            raise ValueError("Could not find a valid header row containing 'Place_ID'.")

        self.seen_import_ids = set()
        self.ms_cache = {m.siglum: m for m in SingleManuscript.objects.all()}
        self.location_cache = {l.placename_id: l for l in Location.objects.all()}
        self.folio_cache = {
            (f.manuscript.siglum, f.folio_number): f
            for f in Folio.objects.select_related("manuscript").all()
        }

        missing_locations = []
        missing_folios = []

        seen_locations = set(self.location_cache.keys())
        seen_folios = set(self.folio_cache.keys())

        for row in dataset.dict:
            pid = str(row.get("Place_ID", "")).strip().replace("?", "")
            ms = str(row.get("MS", "")).strip()
            fol = str(row.get("Folio", "")).strip()
            name = str(row.get("HistEng_Name", "")).strip()

            if pid and pid not in seen_locations:
                missing_locations.append(Location(placename_id=pid, name=name))
                seen_locations.add(pid)

            if fol and ms in self.ms_cache and (ms, fol) not in seen_folios:
                missing_folios.append(
                    Folio(manuscript=self.ms_cache[ms], folio_number=fol)
                )
                seen_folios.add((ms, fol))

        # bulk create missing locations and folios
        # ensure location is created if it doesn't exist
        if missing_locations:
            Location.objects.bulk_create(missing_locations)
            self.location_cache = {l.placename_id: l for l in Location.objects.all()}

        # ensure folio is created if it doesn't exist
        if missing_folios:
            Folio.objects.bulk_create(missing_folios)
            self.folio_cache = {
                (f.manuscript.siglum, f.folio_number): f
                for f in Folio.objects.select_related("manuscript").all()
            }

    def before_import_row(self, row, **kwargs):
        """clean values, skip rows with uncertain Place_ID"""

        # clean values
        label = str(row.get("Label", "")).strip()
        pid = str(row.get("Place_ID", "")).strip().replace("?", "")
        ms_siglum = str(row.get("MS", "")).strip()
        folio_num = str(row.get("Folio", "")).strip()

        row["Label"] = label
        row["Place_ID"] = pid
        row["MS"] = ms_siglum
        row["Folio"] = folio_num

        if not pid:
            row["_skip"] = True
            return

    def skip_row(self, instance, original, row, import_validation_errors=None):
        """skip a row if marked _skip"""
        if row.get("_skip"):
            return True
        return super().skip_row(
            instance, original, row, import_validation_errors=import_validation_errors
        )


class LineCodeResource(resources.ModelResource):
    """Resource for importing and exporting LineCode data"""

    code = fields.Field(column_name="Code", attribute="code")
    toponyms = fields.Field(column_name="Toponyms")

    class Meta:
        model = LineCode
        import_id_fields = ["code"]
        fields = ("code", "toponyms")
        export_order = fields
        skip_unchanged = True
        report_skipped = True

    def dehydrate_toponyms(self, line_code):
        """Export the associated toponyms as a comma-separated list of placename IDs"""
        toponyms = line_code.associated_toponyms.all()
        return ", ".join([t.placename_id for t in toponyms]) if toponyms else ""

    def before_import(self, dataset, using_transactions=True, dry_run=False, **kwargs):
        """Log the data being imported to diagnose issues"""
        logger.info(f"Importing LineCode data: {len(dataset)} rows")
        logger.info(f"Columns: {dataset.headers}")
        if len(dataset) > 0:
            logger.info(f"First row: {dataset[0]}")

    def hydrate_toponyms(self, value):
        """This method is called during import but we handle the relationship in after_import_row"""
        return value

    def get_instance(self, instance_loader, row):
        """Get existing instance for a row if it exists"""
        try:
            return LineCode.objects.get(code=row["Code"])
        except LineCode.DoesNotExist:
            return None

    def before_import_row(self, row, **kwargs):
        """Process a row before import - ensure we have the required fields"""
        # Log the incoming row data
        logger.info(f"Processing row: {row}")

        # Make sure all necessary fields are present or create default values
        if "Code" not in row:
            logger.warning("Skipping row without Code field")
            return False

        # Make sure Toponyms is present even if empty
        if "Toponyms" not in row:
            logger.warning(f"Row is missing Toponyms field: {row}")
            row["Toponyms"] = ""

        return True

    def after_import_row(self, row, row_result, **kwargs):
        """Process a row after import to handle M2M relationships"""
        if row_result.import_type in [
            row_result.IMPORT_TYPE_NEW,
            row_result.IMPORT_TYPE_UPDATE,
        ]:
            try:
                # Get the line code instance
                line_code = LineCode.objects.get(code=row.get("Code"))

                # Handle associated toponyms if present in the import
                toponyms = row.get("Toponyms")
                logger.info(f"Processing toponyms for {line_code.code}: {toponyms}")

                if toponyms:
                    # Clear existing toponyms first to avoid duplicates
                    line_code.associated_toponyms.clear()

                    # Split the toponyms string by comma and strip whitespace
                    toponym_list = [t.strip() for t in toponyms.split(",")]

                    # Add each toponym to the line code
                    for toponym_id in toponym_list:
                        if not toponym_id:  # Skip empty strings
                            continue

                        try:
                            location = Location.objects.get(placename_id=toponym_id)
                            line_code.associated_toponyms.add(location)
                            logger.info(
                                f"Added toponym {toponym_id} to line code {line_code.code}"
                            )
                        except Location.DoesNotExist:
                            logger.warning(
                                f"Toponym {toponym_id} not found for line code {line_code.code}"
                            )

            except LineCode.DoesNotExist:
                logger.error(
                    f"LineCode {row.get('Code')} not found during after_import_row"
                )
            except Exception as e:
                logger.error(
                    f"Error processing toponyms for {row.get('Code')}: {str(e)}",
                    exc_info=True,
                )

    def import_row(self, row, instance_loader, **kwargs):
        """Override import_row to better handle the import process for LineCode objects"""
        dry_run = kwargs.get("dry_run", False)
        logger.info(f"Import row (dry_run={dry_run}): {row}")

        import_result = super().import_row(row, instance_loader, **kwargs)

        # Log the import result for debugging
        logger.info(
            f"Import result: {import_result.import_type}, errors: {import_result.errors}"
        )

        # Add the toponyms to the diff display to show what's being imported
        if "Toponyms" in row and row["Toponyms"]:
            import_result.diff.append(row["Toponyms"])
        else:
            import_result.diff.append("")

        # If we're not in dry run mode and the import was successful,
        # double check that toponyms were properly processed
        if not dry_run and import_result.import_type not in [
            import_result.IMPORT_TYPE_ERROR,
            import_result.IMPORT_TYPE_SKIP,
        ]:
            try:
                # Get the line code instance
                line_code = LineCode.objects.get(code=row.get("Code"))

                # If there are no toponyms already assigned but we have them in the row,
                # try to assign them again
                if not line_code.associated_toponyms.exists() and row.get("Toponyms"):
                    # Split the toponyms string by comma and strip whitespace
                    toponym_list = [t.strip() for t in row.get("Toponyms").split(",")]

                    # Add each toponym to the line code
                    for toponym_id in toponym_list:
                        if not toponym_id:  # Skip empty strings
                            continue

                        try:
                            location = Location.objects.get(placename_id=toponym_id)
                            line_code.associated_toponyms.add(location)
                            logger.info(
                                f"Added toponym {toponym_id} to line code {line_code.code} in double-check"
                            )
                        except Location.DoesNotExist:
                            logger.warning(
                                f"Toponym {toponym_id} not found for line code {line_code.code}"
                            )

            except Exception as e:
                logger.error(
                    f"Error in import_row double-check for {row.get('Code')}: {str(e)}",
                    exc_info=True,
                )

        return import_result

    def get_diff_headers(self):
        """Define headers for the diff display"""
        return ["Code", "Toponyms"]


class StanzaResource(ExportOnlyResource):
    class Meta:
        model = Stanza
        fields = (
            "id",
            "stanza_line_code_starts",
            "stanza_line_code_ends",
            "stanza_text",
            "stanza_notes",
            "language",
            "is_rubric",
        )
        export_order = fields

    def dehydrate_stanza_text(self, instance):
        return strip_tags(instance.stanza_text) if instance.stanza_text else ""

    def dehydrate_stanza_notes(self, instance):
        return strip_tags(instance.stanza_notes) if instance.stanza_notes else ""


class StanzaTranslatedResource(ExportOnlyResource):
    # export the line code of the parent stanza instead of just the id
    parent_stanza_code = fields.Field(
        attribute="stanza__stanza_line_code_starts", column_name="original_stanza_code"
    )

    class Meta:
        model = StanzaTranslated
        fields = (
            "id",
            "parent_stanza_code",
            "stanza_line_code_starts",
            "stanza_line_code_ends",
            "stanza_text",
            "language",
            "is_rubric",
        )
        export_order = fields

    def dehydrate_stanza_text(self, instance):
        return strip_tags(instance.stanza_text) if instance.stanza_text else ""
