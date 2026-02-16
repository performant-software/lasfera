from import_export import resources, fields, widgets
from import_export.widgets import ForeignKeyWidget
from import_export.results import RowResult
from django.contrib import messages
from django.db.models import Q
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
)


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
    latitude = fields.Field(
        column_name="Latitude", attribute="latitude", widget=widgets.FloatWidget()
    )
    longitude = fields.Field(
        column_name="Longitude", attribute="longitude", widget=widgets.FloatWidget()
    )
    authority_file = fields.Field(column_name="WHG_Link", attribute="authority_file")
    modern_country = fields.Field(column_name="Country", attribute="modern_country")
    description = fields.Field(column_name="Toponym_Text", attribute="description")
    mod_name = fields.Field(column_name="Mod_Name", attribute="Mod_Name", readonly=True)
    anc_name = fields.Field(column_name="Anc_Name", attribute="Anc_Name", readonly=True)
    ex_name = fields.Field(column_name="Ex_Name", attribute="Ex_Name", readonly=True)

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

    def get_or_init_instance(self, instance_loader, row):
        """override to prevent 'update' highlight from showing up for
        every single instance due to non-model fields"""
        instance, created = super().get_or_init_instance(instance_loader, row)

        if not created:
            instance.Mod_Name = row.get("Mod_Name")
            instance.Anc_Name = row.get("Anc_Name")
            instance.Ex_Name = row.get("Ex_Name")

        return instance, created

    def import_field(self, field, obj, row, is_m2m=False, **kwargs):
        """attach the raw values to the python object for non-model fields,
        so dehydrate can see them"""
        if field.column_name in ["Mod_Name", "Anc_Name", "Ex_Name"]:
            setattr(obj, field.column_name, row.get(field.column_name))
        else:
            super().import_field(field, obj, row, is_m2m, **kwargs)

    def dehydrate_mod_name(self, instance):
        return getattr(instance, "Mod_Name", "")

    def dehydrate_anc_name(self, instance):
        return getattr(instance, "Anc_Name", "")

    def dehydrate_ex_name(self, instance):
        return getattr(instance, "Ex_Name", "")

    def after_import_row(self, row, row_result, **kwargs):
        """Create alias records for modern and ancient names if they exist"""
        # check dry_run to prevent creating LocationAlias records during preview
        dry_run = kwargs.get("dry_run", False)
        if dry_run:
            return
        location = row_result.instance
        if not location or not location.pk:
            return
        try:
            location = Location.objects.get(placename_id=row.get("Place_ID"))

            # Get the values
            modern_name = row.get("Mod_Name")
            ancient_name = row.get("Anc_Name")
            mss_name = row.get("Ex_Label")

            if modern_name:
                _, created = LocationAlias.objects.get_or_create(
                    location=location,
                    placename_modern=modern_name,
                )
                if created:
                    self.aliases_created += 1

            if ancient_name:
                _, created = LocationAlias.objects.get_or_create(
                    location=location,
                    placename_ancient=ancient_name,
                )
                if created:
                    self.aliases_created += 1

            if mss_name:
                _, created = LocationAlias.objects.get_or_create(
                    location=location,
                    placename_from_mss=mss_name,
                )
                if created:
                    self.aliases_created += 1

        except Location.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error creating alias for {row.get('Place_ID')}: {str(e)}")

    def after_import(self, dataset, result, **kwargs):
        """Add custom toponym alias summary to the import result"""
        if not kwargs.get("dry_run", False):
            count = getattr(self, "aliases_created", 0)
            request = kwargs.get("request")
            if request and count > 0:
                messages.success(
                    request,
                    f"Import successful. In addition to toponyms, {count} new Toponym Aliases were created/linked.",
                )
            elif request:
                messages.info(
                    request, "Import successful. No new Toponym Aliases were required."
                )

    class Meta:
        model = Location
        import_id_fields = ["placename_id"]
        skip_unchanged = True
        report_skipped = True
        fields = (
            "placename_id",
            "name",
            "place_type",
            "mod_name",
            "anc_name",
            "ex_name",
            "latitude",
            "longitude",
            "authority_file",
            "modern_country",
            "description",
        )


class LocationAliasResource(resources.ModelResource):
    location = fields.Field(
        column_name="Place_ID",
        attribute="location",
        widget=ForeignKeyWidget(Location, "placename_id"),
    )
    placename_alias = fields.Field(column_name="Label", attribute="placename_alias")
    ms_siglum = fields.Field(column_name="MS", attribute="ms_siglum", readonly=True)
    folio_number = fields.Field(column_name="Folio", attribute="folio_number", readonly=True)

    class Meta:
        model = LocationAlias
        fields = ("location", "placename_alias", "ms_siglum", "folio_number")
        import_id_fields = ["location", "placename_alias"]
        skip_unchanged = True
        report_skipped = True

    # cache manuscripts by siglum to prevent unnecessary sql queries
    _ms_cache = None
    # and locations by placename_id
    _location_cache = None

    @property
    def ms_cache(self):
        """lazy-loaded manuscript cache by siglum"""
        if self._ms_cache is None:
            self._ms_cache = {
                m.siglum.strip(): m
                for m in SingleManuscript.objects.filter(siglum__isnull=False)
            }
        return self._ms_cache

    @property
    def location_cache(self):
        if self._location_cache is None:
            self._location_cache = {
                l.placename_id: l
                for l in Location.objects.filter(placename_id__isnull=False)
            }
        return self._location_cache

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

    def before_import_row(self, row, **kwargs):
        """skip rows with uncertain Place_ID / manuscripts that don't exist"""
        if row.get("Label"):
            row["Label"] = str(row["Label"]).strip()

        pid = row.get("Place_ID")
        if not pid or "?" in str(pid):
            row["_skip"] = True
            return

        ms_siglum = str(row.get("MS", "")).strip()
        if ms_siglum not in self.ms_cache:
            row["_skip"] = True
            return

        # ensure location is created if it doesn't exist
        if pid in self.location_cache:
            row["_related_location"] = self.location_cache[pid]
        else:
            location, _ = Location.objects.get_or_create(
                placename_id=pid,
                defaults={"name": row.get("HistEng_Name", "").strip()},
            )
            self.location_cache[pid] = location
            row["_related_location"] = location

    def skip_row(self, instance, original, row, import_validation_errors=None):
        """skip a row if marked _skip"""
        if row.get("_skip"):
            return True
        return super().skip_row(
            instance, original, row, import_validation_errors=import_validation_errors
        )

    def get_instance(self, instance_loader, row):
        """find LocationAlias by Place_ID + Label, prevent IntegrityError"""
        related_location = row.get("_related_location")
        label = row.get("Label")
        if not related_location or not label:
            return None
        return LocationAlias.objects.filter(
            location=related_location, placename_alias=label
        ).first()

    def get_or_init_instance(self, instance_loader, row):
        """override to prevent 'update' highlight from showing up for
        every single instance due to non-model fields"""
        instance, created = super().get_or_init_instance(instance_loader, row)

        instance.ms_siglum = row.get("MS")
        instance.folio_number = row.get("Folio")

        return instance, created
    
    def dehydrate_ms_siglum(self, instance):
        return getattr(instance, "ms_siglum", "")

    def dehydrate_folio_number(self, instance):
        return getattr(instance, "folio_number", "")

    def import_instance(self, instance, row, **kwargs):
        """handle created Location"""
        instance.location = row.get("_related_location")
        # must now manually handle Label
        instance.placename_alias = row.get("Label")

    def after_import_row(self, row, row_result, **kwargs):
        if (
            not kwargs.get("dry_run", False)
            and row_result.import_type != row_result.IMPORT_TYPE_SKIP
        ):
            alias = row_result.instance
            if not alias or not alias.pk:
                return

            # associate MS
            ms_siglum = row.get("MS").strip()
            manuscript = self.ms_cache.get(ms_siglum)
            alias.manuscripts.add(manuscript)

            # associate folio
            folio_number = str(row.get("Folio", "")).strip()
            if folio_number:
                folio, _ = Folio.objects.get_or_create(
                    manuscript=manuscript, folio_number=folio_number
                )
                alias.folios.add(folio)


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
