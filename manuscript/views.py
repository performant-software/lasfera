from itertools import chain
import logging
import os
import random
from collections import defaultdict
from html import unescape

import requests
from django.contrib.contenttypes.models import ContentType
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.db.models import Exists, OuterRef, Q, Prefetch
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.utils.text import slugify
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView
from rest_framework import viewsets

from manuscript.models import (
    Folio,
    Location,
    LocationAlias,
    SingleManuscript,
    Stanza,
    StanzaTranslated,
    line_code_to_numeric,
)
from manuscript.serializers import SingleManuscriptSerializer, ToponymSerializer
from pages.models import AboutPage, SitePage
from textannotation.models import CrossReference, EditorialNote, TextualVariant

logger = logging.getLogger(__name__)


def get_manifest_data(manifest_url):
    """Fetch and cache IIIF manifest data."""
    cache_key = f"iiif_manifest_{manifest_url}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return cached_data

    # Fetch and cache for 24 hours if not in cache
    response = requests.get(manifest_url)
    response.raise_for_status()
    manifest_data = response.json()
    cache.set(cache_key, manifest_data, 60 * 60 * 24)

    return manifest_data


def manuscript_stanzas(request, siglum):
    # Get the requested manuscript
    manuscript = get_object_or_404(SingleManuscript, siglum=siglum)
    logger.info(f"Loading manuscript_stanzas for {siglum}")

    # Get all folios for this manuscript
    folios = manuscript.folio_set.all().order_by("folio_number")
    logger.info(f"Found {folios.count()} folios for manuscript {siglum}")

    # Check if this is Urb1
    is_urb1 = siglum == "Urb1"

    # Special handling for the Urb1 manuscript which we know works
    if is_urb1:
        # For Urb1, use the well-tested filtering approach
        stanzas = Stanza.objects.filter(
            folios__in=folios, folios__manuscript=manuscript
        ).distinct()
        logger.info(f"Found {stanzas.count()} stanzas for Urb1 using direct filtering")
    else:
        # For all other manuscripts
        if folios.exists():
            # If we have folios, try to use them to find matching stanzas
            logger.info(f"Using folios to find stanzas for {siglum}")
            stanzas = Stanza.objects.filter(
                folios__in=folios, folios__manuscript=manuscript
            ).distinct()

            if stanzas.count() == 0:
                logger.info(
                    f"No stanzas found using folios for {siglum}, using all stanzas with line codes"
                )
                stanzas = Stanza.objects.exclude(stanza_line_code_starts__isnull=True)
        else:
            # No folios, so just use all stanzas with line codes
            logger.info(
                f"No folios found for {siglum}, using all stanzas with line codes"
            )
            stanzas = Stanza.objects.exclude(stanza_line_code_starts__isnull=True)

    # Prefetch for efficiency
    stanzas = stanzas.prefetch_related(
        "folios",
        "editorial_notes",
        "cross_references",
        Prefetch(
            "textual_variants", 
            queryset=TextualVariant.objects.filter(manuscript=manuscript).select_related("manuscript"),
        )
    )
    logger.info(f"Found {stanzas.count()} total stanzas")

    # Get translated stanzas for all stanzas
    translated_stanzas = StanzaTranslated.objects.filter(stanza__in=stanzas).distinct()
    translated_stanzas = translated_stanzas.prefetch_related(
        "editorial_notes",
        "cross_references",
        Prefetch(
            "textual_variants", 
            queryset=TextualVariant.objects.filter(manuscript=manuscript).select_related("manuscript"),
        )
    )
    logger.info(f"Found {translated_stanzas.count()} translated stanzas")


    # Process stanzas into books structure
    books = process_stanzas(stanzas)
    translated_books = process_stanzas(translated_stanzas, is_translated=True)
    logger.info(f"Processed stanzas into {len(books)} books")

    # Build paired books structure (will be sorted by book number)
    paired_books = {}

    # Prepare folio mapping if we have folios
    has_folio_mapping = False
    line_code_to_folio = {}

    if folios.exists():
        # Try to build a map of line codes to folios
        for folio in folios:
            if folio.line_code_range_start and folio.line_code_range_end:
                try:
                    start_code = line_code_to_numeric(folio.line_code_range_start)
                    end_code = line_code_to_numeric(folio.line_code_range_end)

                    # Skip if we couldn't parse the codes
                    if start_code is None or end_code is None:
                        continue

                    # Add codes to the map
                    for code in range(start_code, end_code + 1):
                        line_code_to_folio[code] = folio

                    has_folio_mapping = True
                    logger.info(
                        f"Mapped codes {start_code}-{end_code} to folio {folio.folio_number}"
                    )
                except Exception as e:
                    logger.warning(f"Error mapping folio {folio.folio_number}: {e}")

    # Process each book
    for book_number, stanza_dict in books.items():
        paired_books[book_number] = []
        current_folio = None

        # Sort stanza numbers for consistent ordering
        sorted_stanza_numbers = sorted(stanza_dict.keys())

        for stanza_number in sorted_stanza_numbers:
            original_stanzas = stanza_dict[stanza_number]

            # Get corresponding translated stanzas
            translated_stanza_group = translated_books.get(book_number, {}).get(
                stanza_number, []
            )

            # If no translations found or this is Yale3 manuscript, use FK relationship instead
            if (not translated_stanza_group or siglum == "Yale3") and original_stanzas:
                # Create a map of original stanza IDs
                original_ids = [s.id for s in original_stanzas]
                # Find translations directly linked to these stanzas
                linked_translations = [
                    ts for ts in translated_stanzas if ts.stanza_id in original_ids
                ]
                if linked_translations:
                    # Override the translations with the directly linked ones
                    translated_stanza_group = linked_translations
                    
            # Ensure translations are always sorted by line code
            if translated_stanza_group:
                translated_stanza_group = sorted(
                    translated_stanza_group, 
                    key=lambda s: line_code_to_numeric(s.stanza_line_code_starts)
                )

            # Create the stanza group - we'll show all stanzas for now
            # This ensures manuscripts without folios still show stanzas
            stanza_group = {
                "original": original_stanzas,
                "translated": translated_stanza_group,
            }

            # If we have a folio mapping, try to add folio information
            if has_folio_mapping and original_stanzas:
                first_stanza = original_stanzas[0]
                if first_stanza.stanza_line_code_starts:
                    try:
                        stanza_code = line_code_to_numeric(
                            first_stanza.stanza_line_code_starts
                        )
                        if stanza_code in line_code_to_folio:
                            matching_folio = line_code_to_folio[stanza_code]

                            # If this is a new folio, mark it in the stanza group
                            existing_folio_ids = {f.id for f in first_stanza.folios.all()}
                            if current_folio is None or matching_folio != current_folio:
                                current_folio = matching_folio
                                stanza_group["new_folio"] = True
                                stanza_group["current_folio"] = current_folio
                                logger.info(
                                    f"New folio for stanza {stanza_number}: {current_folio.folio_number}"
                                )

                                # Associate the stanza with this folio if not already done
                                if matching_folio.id not in existing_folio_ids:
                                    first_stanza.folios.add(matching_folio)
                    except Exception as e:
                        logger.warning(
                            f"Error determining folio for stanza {first_stanza.id}: {e}"
                        )

            # Add the stanza group to the book
            paired_books[book_number].append(stanza_group)

    # Get all manuscripts for the dropdown
    manuscripts = SingleManuscript.objects.select_related("library").annotate(
        has_variants=Exists(
            TextualVariant.objects.filter(manuscript=OuterRef('pk'))
        )
    ).all()

    # Count the total stanzas we're sending to the template
    total_stanzas = sum(len(book) for book in paired_books.values())
    logger.info(f"Rendering template with {total_stanzas} stanza pairs")

    return render(
        request,
        "stanzas.html",
        {
            "paired_books": paired_books,
            "manuscripts": manuscripts,
            "default_manuscript": manuscript,
            "manuscript": {
                "iiif_url": manuscript.iiif_url if manuscript.iiif_url else None
            },
            "folios": folios,
            "has_known_folios": True,
        },
    )


@require_POST
@ensure_csrf_cookie
def create_annotation(request):
    try:
        if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
            raise ValueError("AJAX required")

        # Get required fields
        object_id = request.POST.get("stanza_id")
        selected_text = request.POST.get("selected_text")
        annotation_text = request.POST.get("annotation")
        annotation_type = request.POST.get("annotation_type")
        model_type = request.POST.get("model_type", "stanza")
        notes = request.POST.get("notes")

        TYPE_MAP = {
            "note": EditorialNote,
            "reference": CrossReference,
            "variant": TextualVariant,
        }
        AnnotationModel = TYPE_MAP.get(annotation_type)
        if not AnnotationModel:
            return JsonResponse(
                {"success": False, "error": "Invalid annotation type"}, status=400
            )

        # Validate required fields
        if not all([object_id, selected_text, annotation_type]):
            return JsonResponse(
                {"success": False, "error": "Missing core required fields"}, status=400
            )

        if annotation_type == "variant":
            # variant: need either annotation_text OR notes
            if not annotation_text and not notes:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Variants require either variant text or notes.",
                    },
                    status=400,
                )
        else:
            # otherwise: need annotation_text
            if not annotation_text:
                return JsonResponse(
                    {"success": False, "error": "Annotation text is required."},
                    status=400,
                )

        # Get the appropriate model and object
        if model_type == "stanzatranslated":
            content_type = ContentType.objects.get_for_model(StanzaTranslated)
            get_object_or_404(StanzaTranslated, id=object_id)
        else:
            content_type = ContentType.objects.get_for_model(Stanza)
            get_object_or_404(Stanza, id=object_id)

        try:
            from_pos = int(request.POST.get("from_pos", 0))
            to_pos = int(request.POST.get("to_pos", 0))
        except (ValueError, TypeError):
            from_pos, to_pos = 0, 0

        # Create the annotation
        annotation_fields = {
            "content_type": content_type,
            "object_id": object_id,
            "selected_text": selected_text,
            "annotation": annotation_text,
            "from_pos": from_pos,
            "to_pos": to_pos,
        }
        # special fields for Variant type
        if annotation_type == "variant":
            annotation_fields["notes"] = notes
            annotation_fields["editor_initials"] = request.POST.get("editor_initials", "")
            try:
                annotation_fields["significance"] = int(request.POST.get("significance", 0))
            except (ValueError, TypeError):
                annotation_fields["significance"] = 0
            variant_id = request.POST.get("variant_id", "").strip()
            annotation_fields["variant_id"] = variant_id if variant_id else None

            manuscript_id = request.POST.get("manuscript_id")
            
            if manuscript_id:
                # Optional: specific validation that the ID is valid integer
                try:
                    annotation_fields["manuscript_id"] = int(manuscript_id)
                except (ValueError, TypeError):
                     return JsonResponse(
                        {"success": False, "error": "Invalid Manuscript"}, 
                        status=400
                    )
            else:
                # Decide if manuscript is required. If so, return error here.
                annotation_fields["manuscript_id"] = None

        annotation = AnnotationModel.objects.create(
            **annotation_fields
        )

        return JsonResponse(
            {
                "success": True,
                "annotation_id": annotation.id,
                "message": "Annotation saved successfully",
            }
        )

    except Exception as e:
        logger.exception("Error creating annotation")
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@require_GET
def get_annotations(request, stanza_id):
    try:
        stanza = Stanza.objects.get(id=stanza_id)
        notes = stanza.editorial_notes.all()
        refs = stanza.cross_references.all()
        variants = stanza.textual_variants.all()

        annotations = chain(notes, refs, variants)

        return JsonResponse(
            [
                {
                    "id": ann.id,
                    "selected_text": ann.selected_text,
                    "annotation": ann.annotation,
                    "annotation_type": ann.annotation_type,
                    "from_pos": ann.from_pos,
                    "to_pos": ann.to_pos,
                }
                for ann in annotations
            ],
            safe=False,
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def get_annotation(request, annotation_type, annotation_id):
    TYPE_MAP = {
        "note": EditorialNote,
        "reference": CrossReference,
        "variant": TextualVariant,
    }
    try:
        AnnotationModel = TYPE_MAP.get(annotation_type)
        annotation = get_object_or_404(AnnotationModel, id=annotation_id)

        data = {
            "id": annotation.id,
            "selected_text": annotation.selected_text,
            "annotation": annotation.annotation,
            "annotation_type": annotation_type,
        }

        if annotation_type == "variant":
            data["manuscript"] = annotation.manuscript.siglum
            data["line_code"] = str(annotation.content_object)
            data["notes"] = annotation.notes

        return JsonResponse(data)

    except AnnotationModel.DoesNotExist:
        logger.error(f"Annotation {annotation_id} not found")
        return JsonResponse({"error": "Annotation not found"}, status=404)
    except Exception as e:
        logger.error(f"Error retrieving annotation: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


def process_stanzas(stanzas, is_translated=False):
    books = defaultdict(lambda: defaultdict(list))
    for stanza in stanzas:
        book_number = int(stanza.stanza_line_code_starts.split(".")[0])
        stanza_number = int(stanza.stanza_line_code_starts.split(".")[1])

        if is_translated:
            stanza.unescaped_stanza_text = unescape(stanza.stanza_text)
        else:
            stanza.unescaped_stanza_text = unescape(stanza.stanza_text)

        books[book_number][stanza_number].append(stanza)
        
        # Sort stanzas within each stanza number by line code for proper ordering
        books[book_number][stanza_number].sort(
            key=lambda s: line_code_to_numeric(s.stanza_line_code_starts)
        )

    # Return books with keys sorted by book number
    return {k: dict(v) for k, v in sorted(books.items())}


def index(request: HttpRequest):
    from pages.models import HomeIntroduction

    intro = HomeIntroduction.objects.first()

    # Prefetch image URLs
    image_directory = "images/home/"
    image_urls = []
    static_dir = finders.find(image_directory)
    if static_dir and os.path.exists(static_dir):
        images = [
            f for f in os.listdir(static_dir) 
            if os.path.isfile(os.path.join(static_dir, f))
        ]
        for image in images:
            image_urls.append(static(f"images/home/{image}"))

    # Shuffle the image URLs to simulate randomness
    random.shuffle(image_urls)

    context = {
        "manuscript_images": image_urls,
        "intro": intro,  # via Wagtail
        "nav_items": [
            {
                "name": "Edition",
                "url": "/manuscripts/Urb1/stanzas/",
                "thumbnail": static("images/home/wellcome230_p44.webp"),
            },
            {
                "name": "Gazetteer",
                "url": "/toponyms",
                "thumbnail": static("images/home/bncf_csopp2618_m1b.webp"),
            },
            {
                "name": "Resources",
                "url": "#",
                "thumbnail": static("images/home/basel_cl194_p59.webp"),
            },
            {
                "name": "Gallery",
                "url": "/pages/gallery/",
                "thumbnail": static("images/home/nypl_f1v_ship.webp"),
            },
            {
                "name": "About",
                "url": "/about/",
                "thumbnail": static("images/home/oxford74_jerusalem.webp"),
            },
        ],
    }
    return render(request, "index.html", context)


def about(request):
    about_page = AboutPage.objects.live().first()

    return render(
        request,
        "pages/about_page.html",
        {
            "about_page": about_page,
        },
    )


def education(request):
    education_page = (
        SitePage.objects.live().filter(title="La Sfera in the Classroom").first()
    )

    return render(
        request,
        "pages/site_page.html",
        {
            "page": education_page,
        },
    )


def data(request):
    data_page = SitePage.objects.live().filter(title="Data").first()

    return render(
        request,
        "pages/site_page.html",
        {
            "page": data_page,
        },
    )


def talks(request):
    talks_page = SitePage.objects.live().filter(title="Talks and Presentations").first()

    return render(
        request,
        "pages/site_page.html",
        {
            "page": talks_page,
        },
    )


def mirador_view(request, manuscript_id, page_number):
    try:
        manuscript = SingleManuscript.objects.get(id=manuscript_id)
    except SingleManuscript.DoesNotExist:
        manuscript = SingleManuscript.objects.get(siglum="Urb1")

    if not manuscript.iiif_url:
        manuscript = SingleManuscript.objects.get(siglum="Urb1")

    try:
        get_manifest_data(manuscript.iiif_url)
    except requests.RequestException:
        # Fallback to default manuscript if manifest can't be fetched
        manuscript = SingleManuscript.objects.get(siglum="Urb1")

    return render(
        request,
        "manuscript/mirador.html",
        {
            "manifest_url": manuscript.iiif_url,
        },
    )


def get_canvas_url_for_folio(manuscript_manifest, folio):
    """
    Find the correct canvas URL from the manifest for a given folio
    """
    folio_label = folio.folio_number

    # Find the matching canvas in the manifest
    for canvas in manuscript_manifest["sequences"][0]["canvases"]:
        if canvas["label"].lower() == folio_label.lower():
            return canvas["@id"]

    return None


def stanzas(request: HttpRequest):
    folios = Folio.objects.all()
    stanzas = (
        Stanza.objects.prefetch_related(
            "editorial_notes",
            "cross_references",
            Prefetch(
                "textual_variants", 
                queryset=TextualVariant.objects.select_related("manuscript")
            )
        )
        .all()
        .order_by("stanza_line_code_starts")
    )

    translated_stanzas = (
        StanzaTranslated.objects.prefetch_related(
            "editorial_notes",
            "cross_references",
            Prefetch(
                "textual_variants", 
                queryset=TextualVariant.objects.select_related("manuscript")
            )
        )
        .all()
        .order_by("stanza_line_code_starts")
    )
    manuscripts = SingleManuscript.objects.all()
    default_manuscript = SingleManuscript.objects.get(siglum="Urb1")

    books = process_stanzas(stanzas)
    translated_books = process_stanzas(translated_stanzas)

    # Group stanzas by folio within each book
    paired_books = {}
    for book_number, stanza_dict in sorted(books.items()):  # Sort by book number
        paired_books[book_number] = []
        current_folio = None

        for stanza_number, original_stanzas in stanza_dict.items():
            # Get corresponding translated stanzas
            translated_stanza_group = translated_books.get(book_number, {}).get(
                stanza_number, []
            )

            # If we can't find translations by line code, try using the FK relationship
            if not translated_stanza_group and original_stanzas:
                original_ids = [s.id for s in original_stanzas]
                linked_translations = [
                    ts for ts in translated_stanzas if ts.stanza_id in original_ids
                ]
                if linked_translations:
                    translated_stanza_group = linked_translations
                    
            # Ensure translations are always sorted by line code
            if translated_stanza_group:
                translated_stanza_group = sorted(
                    translated_stanza_group, 
                    key=lambda s: line_code_to_numeric(s.stanza_line_code_starts)
                )

            # Add folio information
            stanza_group = {
                "original": original_stanzas,
                "translated": translated_stanza_group,
            }

            # Check if this is a new folio by looking at the first stanza's folios
            if original_stanzas:
                # Get the first stanza's folios ordered by folio_number
                stanza_folios = sorted(original_stanzas[0].folios.all(), key=lambda f: f.folio_number)

                # If the stanza has any folios and the current folio has changed
                if stanza_folios and (current_folio is None or stanza_folios[0] != current_folio):
                    current_folio = stanza_folios[0]
                    stanza_group["new_folio"] = True
                    stanza_group["show_viewer"] = (
                        True  # Only show viewer for new folios
                    )
                    # Optionally add information about all folios this stanza appears on
                    stanza_group["folios"] = [f.folio_number for f in stanza_folios]
                else:
                    stanza_group["new_folio"] = False

            paired_books[book_number].append(stanza_group)

    manuscript_data = {
        "iiif_url": (
            default_manuscript.iiif_url
            if hasattr(default_manuscript, "iiif_url")
            else None
        )
    }

    return render(
        request,
        "stanzas.html",
        {
            "paired_books": paired_books,
            "manuscripts": manuscripts,
            "default_manuscript": default_manuscript,
            "manuscript": manuscript_data,
            "folios": folios,
        },
    )


class ManuscriptViewer(DetailView):
    model = Stanza
    template_name = "manuscript/viewer.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stanza = self.get_object()

        if stanza.related_folio:
            manuscript = stanza.get_manuscript()

            related_stanzas = (
                Stanza.objects.filter(related_folio=stanza.related_folio)
                .exclude(id=stanza.id)
                .order_by("stanza_line_code_starts")
            )

            context.update(
                {
                    "manifest_url": manuscript.iiif_url if manuscript else None,
                    "canvas_id": (
                        stanza.related_folio.get_canvas_id()
                        if stanza.related_folio
                        else None
                    ),
                    "related_stanzas": related_stanzas,
                    "folio_number": stanza.related_folio.number,
                    "line_range": {
                        "start": stanza.parse_line_code(stanza.stanza_line_code_starts),
                        "end": stanza.parse_line_code(stanza.stanza_line_code_ends),
                    },
                }
            )

            return context


def manuscripts(request: HttpRequest):
    """View for displaying all manuscripts with proper folio grouping"""
    folios = Folio.objects.all()
    stanzas = (
        Stanza.objects.prefetch_related(
            "folios",
            "editorial_notes",
            "cross_references",
            "textual_variants"
        )
        .all()
        .order_by("stanza_line_code_starts")
    )

    # Remove the translated stanzas
    manuscripts = SingleManuscript.objects.all()
    default_manuscript = SingleManuscript.objects.get(siglum="Urb1")

    # Process stanzas into books structure (same as in stanzas view)
    books = defaultdict(lambda: defaultdict(list))
    for stanza in stanzas:
        if stanza.stanza_line_code_starts:
            parts = stanza.stanza_line_code_starts.split(".")
            if len(parts) >= 2:
                book_number = int(parts[0])
                stanza_number = int(parts[1])

                # Process text for display
                if hasattr(stanza, "stanza_text"):
                    stanza.unescaped_stanza_text = unescape(stanza.stanza_text)

                books[book_number][stanza_number].append(stanza)

    # Group stanzas by book and track folios - using same approach as stanzas view
    paired_books = {}
    for book_number, stanza_dict in sorted(books.items()):  # Sort by book number
        paired_books[book_number] = []
        current_folio = None

        # Sort stanza numbers to ensure correct order
        stanza_numbers = sorted(stanza_dict.keys())

        for stanza_number in stanza_numbers:
            original_stanzas = stanza_dict[stanza_number]

            # Create a stanza pair dictionary with just original stanzas
            stanza_pair = {
                "original": original_stanzas,
                "new_folio": False,
            }

            # Check if this is a new folio by looking at the first stanza's folios
            if original_stanzas:
                # Get the first stanza's folios ordered by folio_number
                stanza_folios = sorted(original_stanzas[0].folios.all(), key=lambda f: f.folio_number)

                # If the stanza has any folios and the current folio has changed
                if stanza_folios and (current_folio is None or stanza_folios[0] != current_folio):
                    current_folio = stanza_folios[0]
                    stanza_pair["new_folio"] = True
                    # Add information about all folios this stanza appears on
                    stanza_pair["folios"] = [f.folio_number for f in stanza_folios]

            paired_books[book_number].append(stanza_pair)

    manuscript_data = {
        "iiif_url": (
            default_manuscript.iiif_url
            if hasattr(default_manuscript, "iiif_url")
            else None
        )
    }

    return render(
        request,
        "manuscripts.html",
        {
            "stanza_pairs": paired_books,
            "manuscripts": manuscripts,
            "default_manuscript": default_manuscript,
            "manuscript": manuscript_data,
            "folios": folios,
        },
    )


def manuscript(request: HttpRequest, siglum: str):
    get_manuscript = get_object_or_404(
        SingleManuscript.objects.select_related("library").prefetch_related(
            "codex_set", "textdecoration_set", "editorialstatus_set"
        ),
        siglum=siglum,
    )

    # Get folios and create custom sort
    def folio_sort_key(folio):
        # Extract number and suffix from folio_number
        # Handle potential missing or malformed folio numbers
        if not folio.folio_number:
            return (float("inf"), "z")  # Put empty/null values at the end

        # Find the number part
        import re

        number_match = re.match(r"(\d+)", folio.folio_number)
        if not number_match:
            return (float("inf"), "z")

        number = int(number_match.group(1))

        # Get the suffix (r or v), default to 'z' if neither
        suffix = folio.folio_number[-1].lower()
        # Make 'v' sort before 'r' by converting to sorting value
        suffix_val = {"v": "a", "r": "b"}.get(suffix, "z")

        return (number, suffix_val)

    # Get folios and sort them
    folios = sorted(get_manuscript.folio_set.all(), key=folio_sort_key)

    # Rest of your existing code for handling locations...
    for folio in folios:
        location_aliases = LocationAlias.objects.filter(folios=folio).select_related(
            "location"
        )
        locations = {alias.location for alias in location_aliases}

        folio.related_locations = []
        for location in locations:
            primary_alias = location_aliases.filter(location=location).first()
            display_name = (
                primary_alias.placename_modern
                or primary_alias.placename_from_mss
                or location.name
                or location.modern_country
                or ""
            ).strip()

            folio.related_locations.append(
                {
                    "location": location,
                    "alias": primary_alias,
                    "display_name": display_name,
                    "sort_name": display_name.lower(),
                }
            )

        folio.related_locations.sort(key=lambda x: x["sort_name"])

    return render(
        request,
        "manuscript_single.html",
        {
            "manuscript": get_manuscript,
            "folios": folios,
            "iiif_manifest": get_manuscript.iiif_url,
        },
    )



# Add this utility function to generate toponym slugs consistently
def get_toponym_slug(toponym_name):
    """Generate a slug from a toponym name"""
    return slugify(toponym_name)


def toponym_by_slug(request: HttpRequest, toponym_slug: str):
    """View a toponym by its slugified name"""
    # Try to find the toponym based on slugified name
    location = None

    # First try to find by name
    locations = Location.objects.all()
    for loc in locations:
        if slugify(loc.name) == toponym_slug:
            location = loc
            break

    # If not found by name, check aliases
    if location is None:
        aliases = LocationAlias.objects.all()
        for alias in aliases:
            # Check all the possible name fields
            name_fields = [
                alias.placename_from_mss,
                alias.placename_standardized,
                alias.placename_modern,
                alias.placename_alias,
                alias.placename_ancient,
            ]

            for name in name_fields:
                if name and slugify(name) == toponym_slug:
                    location = alias.location
                    break

            if location:
                break

    if location is None:
        # If still not found, return 404
        from django.http import Http404

        raise Http404(f"No toponym found with slug: {toponym_slug}")

    # Redirect to existing view using placename_id
    return toponym(request, location.placename_id)


def toponyms(request: HttpRequest):
    """View for displaying all toponyms with proper slugs"""
    # Get unique and sorted Location objects
    toponym_objects = (
        Location.objects.exclude(placename_id__isnull=True)
        .exclude(placename_id="")
        .exclude(name__isnull=True)
        .exclude(name="")
        .order_by("name")
        .distinct("name", "placename_id")
    )

    return render(
        request, "gazetteer/gazetteer_index.html", {"locations": toponym_objects}
    )


def toponym(request: HttpRequest, placename_id: str):
    filtered_toponym = get_object_or_404(Location, placename_id=placename_id)
    filtered_manuscripts = SingleManuscript.objects.filter(
        folio__locations_mentioned=filtered_toponym.id
    ).distinct()
    filtered_folios = filtered_toponym.folio_set.all()
    filtered_linecodes = filtered_toponym.line_codes.all()

    manuscripts_with_iiif = filtered_manuscripts.exclude(
        Q(iiif_url__isnull=True) | Q(iiif_url="")
    ).values_list("siglum", "iiif_url")

    iiif_urls = dict(manuscripts_with_iiif)

    iiif_manifest = {
        siglum: get_manifest_data(url) for siglum, url in manuscripts_with_iiif
    }

    # First get aliases with related data
    aliases = filtered_toponym.locationalias_set.all().prefetch_related(
        "manuscripts", "folios"
    )

    # Then process aggregations
    aggregated_aliases = {
        "name": filtered_toponym.name,
        "aliases": [
            {
                "placename_alias": alias.placename_alias,
                "manuscripts": alias.manuscripts.all(),
                "folios": alias.folios.all(),
            }
            for alias in aliases
        ],
        "placename_moderns": [],
        "placename_standardizeds": [],
        "placename_from_msss": [],
        "placename_ancients": [],
    }

    # Process aggregations
    for alias in aliases:
        if alias.placename_modern:
            aggregated_aliases["placename_moderns"].extend(
                name.strip() for name in alias.placename_modern.split(",")
            )
        if alias.placename_standardized:
            aggregated_aliases["placename_standardizeds"].extend(
                name.strip() for name in alias.placename_standardized.split(",")
            )
        if alias.placename_from_mss:
            aggregated_aliases["placename_from_msss"].extend(
                name.strip() for name in alias.placename_from_mss.split(",")
            )
        if alias.placename_ancient:
            aggregated_aliases["placename_ancients"].extend(
                name.strip() for name in alias.placename_ancient.split(",")
            )

    # After aliases are processed, then handle IIIF URLs and manifests
    manuscripts_with_iiif = filtered_manuscripts.exclude(
        Q(iiif_url__isnull=True) | Q(iiif_url="")
    ).values_list("siglum", "iiif_url")

    iiif_urls = dict(manuscripts_with_iiif)
    iiif_manifest = {
        siglum: get_manifest_data(url) for siglum, url in manuscripts_with_iiif
    }

    # Process line codes
    line_codes = [{"line_code": lc.code} for lc in filtered_linecodes]

    context = {
        "toponym": filtered_toponym,
        "manuscripts": filtered_manuscripts,
        "aggregated_aliases": aggregated_aliases,
        "folios": filtered_folios,
        "iiif_manifest": iiif_manifest,
        "iiif_urls": iiif_urls,
        "line_codes": line_codes,
    }

    return render(request, "gazetteer/gazetteer_single.html", context)


def search_toponyms(request):
    """Given a search qury, return Location objects, based on
    Location name and associated LocationAlias placenames."""
    query = request.GET.get("q", "").strip()
    locations = Location.objects.all()
    if query:
        # use subquery with EXISTS on LocationAlias names for efficiency (no JOIN)
        alias_subquery = LocationAlias.objects.filter(
            # ensure we only return related Locations
            location=OuterRef("pk")
        ).filter(
            Q(placename_modern__icontains=query)
            | Q(placename_ancient__icontains=query)
            | Q(placename_from_mss__icontains=query)
            | Q(placename_alias__icontains=query)
        )
        locations = locations.filter(
            Q(name__icontains=query) | Exists(alias_subquery)
        )

    # sort so it matches "all locations" queryset
    locations = locations.order_by("name")

    return render(
        request, "gazetteer/gazetteer_results.html", {"locations": locations}
    )


class ToponymViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ToponymSerializer

    def get_queryset(self):
        """
        Optionally filters the queryset based on the 'q' query parameter
        and returns all objects if no specific filter is applied.
        """
        queryset = Location.objects.all()
        query = self.request.query_params.get("q", None)
        if query is not None:
            queryset = queryset.filter(country__icontains=query)
        return queryset


class SingleManuscriptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SingleManuscriptSerializer
    lookup_field = "siglum"

    def get_queryset(self):
        """
        Optionally filters the queryset based on the 'q' query parameter
        and returns all objects if no specific filter is applied.
        """
        queryset = SingleManuscript.objects.all()
        query = self.request.query_params.get("q", None)
        if query is not None:
            queryset = queryset.filter(siglum__icontains=query)
        return queryset
