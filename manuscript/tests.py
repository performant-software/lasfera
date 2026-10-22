import json
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from manuscript.canvas_linking import clean_canvas_rows, link_canvases
from manuscript.models import (
    Folio,
    Location,
    LocationAlias,
    SingleManuscript,
    Stanza,
    StanzaTranslated,
)
from manuscript.utils import get_canvases, normalize_folio_label

MANIFEST_URL = "https://example.org/iiif/ms/manifest.json"
User = get_user_model()


def v2_canvas(number, label):
    return {
        "@id": f"https://example.org/iiif/ms/canvas/p{number:04d}",
        "label": label,
        "images": [
            {
                "resource": {
                    "@id": f"https://example.org/image/{number}/full/full/0/default.jpg",
                    "service": {"@id": f"https://example.org/image/{number}"},
                }
            }
        ],
    }


def v2_manifest(labels):
    return {
        "sequences": [
            {"canvases": [v2_canvas(i + 1, label) for i, label in enumerate(labels)]}
        ]
    }


class NormalizeFolioLabelTest(SimpleTestCase):
    def test_equivalent_forms(self):
        for value in ["12r", "12R", "f. 12r", "fol.12r", "Carta: 12r", "12 recto"]:
            self.assertEqual(normalize_folio_label(value), "12r", value)
        self.assertEqual(normalize_folio_label("12 verso"), "12v")

    def test_distinct_forms(self):
        self.assertEqual(normalize_folio_label("Ir"), "ir")
        self.assertEqual(normalize_folio_label("piatto.anteriore"), "piattoanteriore")
        self.assertEqual(normalize_folio_label(None), "")


class GetCanvasesTest(SimpleTestCase):
    def test_v2(self):
        canvases = get_canvases(v2_manifest(["1r", "1v"]))
        self.assertEqual(
            canvases[1],
            {
                "index": 1,
                "id": "https://example.org/iiif/ms/canvas/p0002",
                "label": "1v",
                "image_id": "https://example.org/image/2",
            },
        )

    def test_v3(self):
        manifest = {
            "items": [
                {
                    "id": "https://example.org/canvas/1",
                    "label": {"none": ["57r"]},
                    "items": [
                        {
                            "items": [
                                {
                                    "body": {
                                        "id": "https://example.org/image/1/full/max/0/default.jpg",
                                        "service": [
                                            {"id": "https://example.org/image/1"}
                                        ],
                                    }
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        self.assertEqual(
            get_canvases(manifest),
            [
                {
                    "index": 0,
                    "id": "https://example.org/canvas/1",
                    "label": "57r",
                    "image_id": "https://example.org/image/1",
                }
            ],
        )


class LinkFolioCanvasesTest(TestCase):
    def setUp(self):
        self.manuscript = SingleManuscript.objects.create(
            item_id=1, siglum="Test1", iiif_url=MANIFEST_URL
        )

    def add_folios(self, *numbers):
        return [
            Folio.objects.create(manuscript=self.manuscript, folio_number=number)
            for number in numbers
        ]

    def run_command(self, labels, *args):
        out = StringIO()
        with mock.patch(
            "manuscript.management.commands.link_folio_canvases.fetch_manifest",
            return_value=v2_manifest(labels),
        ):
            call_command("link_folio_canvases", *args, stdout=out)
        return out.getvalue()

    def test_links_unique_matches(self):
        folio_1r, folio_1v = self.add_folios("1r", "1v")
        self.run_command(["piatto.anteriore", "Carta: 1r", "Carta: 1v"])

        folio_1r.refresh_from_db()
        self.assertEqual(folio_1r.canvas_id, "https://example.org/iiif/ms/canvas/p0002")
        self.assertEqual(folio_1r.canvas_index, 1)
        self.assertEqual(folio_1r.canvas_label, "Carta: 1r")
        self.assertEqual(folio_1r.image_id, "https://example.org/image/2")
        folio_1v.refresh_from_db()
        self.assertEqual(folio_1v.canvas_index, 2)

    def test_skips_duplicate_canvas_labels(self):
        (folio,) = self.add_folios("1r")
        out = self.run_command(["1r", "1v", "1r", "1v"])

        folio.refresh_from_db()
        self.assertIsNone(folio.canvas_id)
        self.assertIn("several canvases with this label: 1r", out)

    def test_skips_duplicate_folio_numbers(self):
        folios = self.add_folios("20r", "20r")
        out = self.run_command(["20r"])

        for folio in folios:
            folio.refresh_from_db()
            self.assertIsNone(folio.canvas_id)
        self.assertIn("folio number used more than once: 20r", out)

    def test_skips_bare_numbers(self):
        (folio,) = self.add_folios("2")
        out = self.run_command(["1", "2", "3"])

        folio.refresh_from_db()
        self.assertIsNone(folio.canvas_id)
        self.assertIn("not a recto/verso folio number: 2", out)

    def test_links_and_renames_viewer_page_references(self):
        (folio,) = self.add_folios("3 : 1v")
        out = self.run_command(["piatto.anteriore", "1r", "1v"])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_id, "https://example.org/iiif/ms/canvas/p0003")
        self.assertEqual(folio.folio_number, "1v")
        self.assertIn("renamed: 3 : 1v → 1v", out)

    def test_viewer_page_reference_without_folio_label(self):
        (folio,) = self.add_folios("1 : Front cover")
        out = self.run_command(["Front cover", "1r"])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_index, 0)
        self.assertEqual(folio.folio_number, "1 : Front cover")
        self.assertIn(
            "linked, but the folio number needs correcting: 1 : Front cover", out
        )

    def test_viewer_page_reference_not_renamed_onto_existing_folio(self):
        existing, folio = self.add_folios("1r", "3 : 1r")
        # existing 1r is ambiguous, so stays unlinked; canvas 3 is still a 1r
        self.run_command(["1r", "1v", "1r"])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_index, 2)
        self.assertEqual(folio.folio_number, "3 : 1r")
        existing.refresh_from_db()
        self.assertIsNone(existing.canvas_id)

    def test_viewer_page_reference_must_match_manifest(self):
        (folio,) = self.add_folios("2 : 1r")
        out = self.run_command(["1r", "1v"])

        folio.refresh_from_db()
        self.assertIsNone(folio.canvas_id)
        self.assertEqual(folio.folio_number, "2 : 1r")
        self.assertIn("viewer page reference does not match the manifest: 2 : 1r", out)

    def test_dry_run_does_not_rename(self):
        (folio,) = self.add_folios("1 : 1r")
        self.run_command(["1r"], "--dry-run")

        folio.refresh_from_db()
        self.assertEqual(folio.folio_number, "1 : 1r")
        self.assertIsNone(folio.canvas_id)

    def test_keeps_existing_links(self):
        (folio,) = self.add_folios("1r")
        folio.canvas_id = "https://example.org/iiif/ms/canvas/p0002"
        folio.save()
        self.run_command(["1r", "1v"])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_id, "https://example.org/iiif/ms/canvas/p0002")
        # canvas details are filled in for the hand-entered canvas ID
        self.assertEqual(folio.canvas_label, "1v")
        self.assertEqual(folio.canvas_index, 1)

    def test_dry_run_does_not_save(self):
        (folio,) = self.add_folios("1r")
        self.run_command(["1r"], "--dry-run")

        folio.refresh_from_db()
        self.assertIsNone(folio.canvas_id)

    def test_canvas_unique_per_manuscript(self):
        canvas_id = "https://example.org/iiif/ms/canvas/p0001"
        Folio.objects.create(manuscript=self.manuscript, canvas_id=canvas_id)
        with self.assertRaises(IntegrityError):
            Folio.objects.create(manuscript=self.manuscript, canvas_id=canvas_id)


def canvas_row(number, folio="", label=None):
    return {
        "id": f"https://example.org/iiif/ms/canvas/p{number:04d}",
        "index": number - 1,
        "label": label if label is not None else f"label {number}",
        "image_id": f"https://example.org/image/{number}",
        "folio": folio,
    }


class LinkCanvasesTest(TestCase):
    def setUp(self):
        self.manuscript = SingleManuscript.objects.create(
            item_id=1, siglum="Test1", iiif_url=MANIFEST_URL
        )

    def add_folio(self, number, canvas=None):
        folio = Folio.objects.create(manuscript=self.manuscript, folio_number=number)
        if canvas:
            folio.canvas_id = canvas_row(canvas)["id"]
            folio.canvas_index = canvas - 1
            folio.save()
        return folio

    def link(self, rows, **kwargs):
        counts, created = link_canvases(
            self.manuscript, clean_canvas_rows(rows), **kwargs
        )
        self.created = created
        return counts

    def test_links_existing_and_creates_new_folios(self):
        folio_1r = self.add_folio("1r")
        counts = self.link([canvas_row(1, "f. 1r"), canvas_row(2, "1v"), canvas_row(3)])

        self.assertEqual(counts, {"linked": 2, "created": 1})
        self.assertEqual([folio.folio_number for folio in self.created], ["1v"])
        folio_1r.refresh_from_db()
        self.assertEqual(folio_1r.folio_number, "1r")
        self.assertEqual(folio_1r.canvas_id, canvas_row(1)["id"])
        self.assertEqual(folio_1r.canvas_label, "label 1")
        self.assertEqual(folio_1r.image_id, "https://example.org/image/1")
        folio_1v = Folio.objects.get(manuscript=self.manuscript, folio_number="1v")
        self.assertEqual(folio_1v.canvas_index, 1)

    def test_clearing_unlinks_but_keeps_folio(self):
        folio = self.add_folio("1r", canvas=1)
        counts = self.link([canvas_row(1, ""), canvas_row(2)])

        self.assertEqual(counts, {"unlinked": 1})
        folio.refresh_from_db()
        self.assertEqual(folio.folio_number, "1r")
        self.assertIsNone(folio.canvas_id)
        self.assertIsNone(folio.canvas_index)

    def test_swapping_canvases(self):
        folio_1r = self.add_folio("1r", canvas=1)
        folio_1v = self.add_folio("1v", canvas=2)
        counts = self.link([canvas_row(1, "1v"), canvas_row(2, "1r")])

        self.assertEqual(counts, {"linked": 2})
        folio_1r.refresh_from_db()
        folio_1v.refresh_from_db()
        self.assertEqual(folio_1r.canvas_index, 1)
        self.assertEqual(folio_1v.canvas_index, 0)

    def test_replacing_a_linked_folio_unlinks_it(self):
        old = self.add_folio("1 : 1r", canvas=1)
        new = self.add_folio("1r")
        counts = self.link([canvas_row(1, "1r")])

        self.assertEqual(counts, {"linked": 1, "unlinked": 1})
        old.refresh_from_db()
        new.refresh_from_db()
        self.assertIsNone(old.canvas_id)
        self.assertEqual(new.canvas_index, 0)

    def test_no_changes(self):
        self.add_folio("1r", canvas=1)
        Folio.objects.filter(folio_number="1r").update(
            canvas_label="label 1", image_id="https://example.org/image/1"
        )
        self.assertEqual(self.link([canvas_row(1, "1r"), canvas_row(2)]), {})

    def test_leaves_links_to_canvases_not_submitted(self):
        folio = self.add_folio("9r", canvas=9)
        self.link([canvas_row(1, "1r")])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_id, canvas_row(9)["id"])

    def test_same_folio_on_two_canvases_is_rejected(self):
        folio = self.add_folio("1r", canvas=1)
        with self.assertRaisesMessage(ValidationError, "more than one image (1, 2)"):
            self.link(
                [canvas_row(1, "1r"), canvas_row(2, "f. 1r"), canvas_row(3, "2r")]
            )

        # nothing was saved
        folio.refresh_from_db()
        self.assertEqual(folio.canvas_index, 0)
        self.assertFalse(Folio.objects.filter(folio_number="2r").exists())

    def test_ambiguous_folio_number_is_rejected(self):
        self.add_folio("197r")
        self.add_folio("197r.")
        with self.assertRaisesMessage(ValidationError, "matches several folio records"):
            self.link([canvas_row(1, "197r")])

    def test_creating_needs_permission(self):
        with self.assertRaisesMessage(
            ValidationError, "permission to add folio records"
        ):
            self.link([canvas_row(1, "1r")], can_create=False)

    def test_bad_rows_are_rejected(self):
        for rows in [None, [{"index": 0}], [canvas_row(1), canvas_row(1)]]:
            with self.assertRaises(ValidationError):
                clean_canvas_rows(rows)


class LinkCanvasesViewTest(TestCase):
    def setUp(self):
        self.manuscript = SingleManuscript.objects.create(
            item_id=1, siglum="Test1", iiif_url=MANIFEST_URL
        )
        self.url = reverse(
            "admin:manuscript_singlemanuscript_canvases", args=[self.manuscript.pk]
        )
        self.user = User.objects.create_superuser("admin", "admin@example.org", "pw")
        self.client.force_login(self.user)

    def test_page_lists_folios(self):
        Folio.objects.create(manuscript=self.manuscript, folio_number="1r")
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="canvas-folios"')
        self.assertContains(response, '"number": "1r"')

    def test_change_form_links_to_page(self):
        response = self.client.get(
            reverse(
                "admin:manuscript_singlemanuscript_change", args=[self.manuscript.pk]
            )
        )
        self.assertContains(response, self.url)

    def test_change_form_lists_folios_compactly(self):
        folio = Folio.objects.create(
            manuscript=self.manuscript,
            folio_number="1r",
            canvas_id=canvas_row(3)["id"],
            canvas_index=2,
            canvas_label="Carta: 1r",
        )
        response = self.client.get(
            reverse(
                "admin:manuscript_singlemanuscript_change", args=[self.manuscript.pk]
            )
        )
        self.assertContains(response, 'name="folio_set-0-line_code_range_start"')
        self.assertContains(
            response, f'{self.url}#folio-{folio.pk}">Image 3 · Carta: 1r'
        )
        self.assertContains(
            response, reverse("admin:manuscript_folio_change", args=[folio.pk])
        )
        self.assertNotContains(response, 'name="folio_set-0-canvas_id"')
        self.assertNotContains(response, 'name="folio_set-0-DELETE"')
        self.assertNotContains(response, 'name="folio_set-__prefix__-folio_number"')

    def test_folio_page_shows_image_and_toponyms(self):
        folio = Folio.objects.create(
            manuscript=self.manuscript,
            folio_number="1r",
            canvas_id=canvas_row(3)["id"],
            canvas_index=2,
            canvas_label="Carta: 1r",
            image_id="https://example.org/image/3",
        )
        location = Location.objects.create(placename_id="T001", name="Rodi")
        LocationAlias.objects.create(
            placename_alias="Rhodes",
            location=location,
            manuscript=self.manuscript,
            folio=folio,
        )
        response = self.client.get(
            reverse("admin:manuscript_folio_change", args=[folio.pk])
        )
        self.assertContains(response, f"{self.url}#folio-{folio.pk}")
        self.assertContains(response, "https://example.org/image/3/full/!200,200/")
        self.assertContains(response, "Image 3 · Carta: 1r")
        self.assertContains(response, "Rhodes")
        self.assertContains(
            response, reverse("admin:manuscript_location_change", args=[location.pk])
        )
        self.assertContains(response, "Rodi</a> (T001)")

    def test_folio_list_links_by_manuscript_and_folio(self):
        folio = Folio.objects.create(manuscript=self.manuscript, folio_number="1r")
        Folio.objects.create(manuscript=self.manuscript)
        response = self.client.get(reverse("admin:manuscript_folio_changelist"))

        folio_url = reverse("admin:manuscript_folio_change", args=[folio.pk])
        self.assertContains(
            response, f'<a href="{folio_url}">Test1 · 1r</a>', html=True
        )
        self.assertContains(response, "Test1 · (no folio number)")
        # sorting by the combined column and by folio number alone both work
        for column in ["1", "2"]:
            self.assertEqual(
                self.client.get(
                    reverse("admin:manuscript_folio_changelist"), {"o": column}
                ).status_code,
                200,
            )

    def test_folio_page_edits_notes(self):
        folio = Folio.objects.create(manuscript=self.manuscript, folio_number="1r")
        response = self.client.get(
            reverse("admin:manuscript_folio_change", args=[folio.pk])
        )
        self.assertContains(response, 'name="folio_includes_map"')
        self.assertContains(response, 'name="folio_notes"')

    def test_saving(self):
        rows = json.dumps([canvas_row(1, "1r"), canvas_row(2)])
        response = self.client.post(self.url, {"rows": rows})

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        folio = Folio.objects.get(manuscript=self.manuscript, folio_number="1r")
        self.assertEqual(folio.canvas_index, 0)

    def test_saving_lists_new_folios_needing_line_ranges(self):
        rows = json.dumps([canvas_row(1, "1r"), canvas_row(2)])
        response = self.client.post(self.url, {"rows": rows}, follow=True)

        folio = Folio.objects.get(manuscript=self.manuscript, folio_number="1r")
        folio_url = reverse("admin:manuscript_folio_change", args=[folio.pk])
        self.assertContains(response, "Add a line range to the new folio records")
        self.assertContains(response, f'<a href="{folio_url}">1r</a>', html=True)

    def test_errors_keep_entries(self):
        rows = json.dumps([canvas_row(1, "1r"), canvas_row(2, "1r")])
        response = self.client.post(self.url, {"rows": rows})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "more than one image")
        self.assertEqual(response.context["submitted"][canvas_row(2)["id"]], "1r")
        self.assertFalse(Folio.objects.exists())

    def test_needs_folio_permission(self):
        staff = User.objects.create_user("staff", password="pw", is_staff=True)
        staff.user_permissions.add(
            Permission.objects.get(codename="change_singlemanuscript")
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)


def custom_manifest(canvases):
    """A v2 manifest from (canvas id suffix, label, image id suffix) tuples"""
    return {
        "sequences": [
            {
                "canvases": [
                    {
                        "@id": f"https://example.org/iiif/ms/canvas/{canvas_id}",
                        "label": label,
                        "images": [
                            {
                                "resource": {
                                    "service": {
                                        "@id": f"https://example.org/image/{image}"
                                    }
                                }
                            }
                        ],
                    }
                    for canvas_id, label, image in canvases
                ]
            }
        ]
    }


class VerifyCanvasLinksTest(TestCase):
    def setUp(self):
        self.manuscript = SingleManuscript.objects.create(
            item_id=1, siglum="Test1", iiif_url=MANIFEST_URL
        )

    def add_folio(self, number, canvas_id, index, label, image):
        return Folio.objects.create(
            manuscript=self.manuscript,
            folio_number=number,
            canvas_id=f"https://example.org/iiif/ms/canvas/{canvas_id}",
            canvas_index=index,
            canvas_label=label,
            image_id=f"https://example.org/image/{image}",
        )

    def run_command(self, canvases, *args):
        out = StringIO()
        with mock.patch(
            "manuscript.management.commands.verify_canvas_links.fetch_manifest",
            return_value=custom_manifest(canvases),
        ):
            call_command("verify_canvas_links", *args, stdout=out)
        return out.getvalue()

    def test_unchanged_links(self):
        folio = self.add_folio("1r", "a", 0, "1r", "img-a")
        out = self.run_command([("a", "1r", "img-a")])

        self.assertIn("1 unchanged", out)
        folio.refresh_from_db()
        self.assertEqual(folio.canvas_index, 0)

    def test_moved_and_relabelled_canvas_is_updated(self):
        folio = self.add_folio("1r", "a", 0, "1r", "img-a")
        out = self.run_command([("cover", "Cover", "img-c"), ("a", "f. 1r", "img-a")])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_index, 1)
        self.assertEqual(folio.canvas_label, "f. 1r")
        self.assertIn("position or label changed: 1r", out)

    def test_relinks_by_image_id(self):
        folio = self.add_folio("1r", "a", 0, "1r", "img-a")
        out = self.run_command([("new-b", "1v", "img-b"), ("new-a", "1r", "img-a")])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_id, "https://example.org/iiif/ms/canvas/new-a")
        self.assertEqual(folio.canvas_index, 1)
        self.assertIn("re-linked by image ID: 1r", out)

    def test_relinks_by_position_and_label(self):
        folio = self.add_folio("1r", "a", 1, "1r", "img-a")
        self.run_command([("x", "Cover", "img-x"), ("y", "1r", "img-y")])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_id, "https://example.org/iiif/ms/canvas/y")
        self.assertEqual(folio.image_id, "https://example.org/image/img-y")

    def test_reports_links_it_cannot_fix(self):
        folio = self.add_folio("1r", "a", 0, "1r", "img-a")
        out = self.run_command([("x", "Cover", "img-x")])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_id, "https://example.org/iiif/ms/canvas/a")
        self.assertIn("canvas gone, and no replacement found: 1r", out)
        self.assertIn("1 could not be re-linked", out)

    def test_does_not_take_a_canvas_linked_to_another_folio(self):
        self.add_folio("1v", "b", 1, "1v", "img-b")
        folio = self.add_folio("1r", "a", 0, "1r", "img-b")
        out = self.run_command([("b", "1v", "img-b")])

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_id, "https://example.org/iiif/ms/canvas/a")
        self.assertIn("its replacement is linked to another folio: 1r", out)

    def test_dry_run_does_not_save(self):
        folio = self.add_folio("1r", "a", 0, "1r", "img-a")
        self.run_command([("new-a", "1r", "img-a")], "--dry-run")

        folio.refresh_from_db()
        self.assertEqual(folio.canvas_id, "https://example.org/iiif/ms/canvas/a")

    def test_reports_manifests_it_cannot_load(self):
        self.add_folio("1r", "a", 0, "1r", "img-a")
        out = StringIO()
        with mock.patch(
            "manuscript.management.commands.verify_canvas_links.fetch_manifest",
            side_effect=Exception("403 Forbidden"),
        ):
            call_command("verify_canvas_links", stdout=out)
        self.assertIn("Test1: could not load manifest (403 Forbidden)", out.getvalue())
        self.assertIn("1 manifests could not be loaded", out.getvalue())


class StanzaFolioDividerTest(TestCase):
    """Folio dividers on the text page, between stanzas and mid-stanza."""

    def setUp(self):
        self.manuscript = SingleManuscript.objects.create(item_id=1, siglum="Test1")
        # Book 1, stanzas 1-4, each with a stanza number (.00) and 8 lines,
        # translated line by line
        for stanza in range(1, 5):
            for line in range(9):
                code = f"01.{stanza:02d}.{line:02d}"
                original = Stanza.objects.create(
                    stanza_line_code_starts=code,
                    stanza_text=f"Original {code}",
                    is_rubric=line == 0,
                )
                StanzaTranslated.objects.create(
                    stanza=original,
                    stanza_line_code_starts=code,
                    stanza_text=f"Translated {code}",
                )

    def add_folios(self, *ranges):
        for number, start, end in ranges:
            Folio.objects.create(
                manuscript=self.manuscript,
                folio_number=number,
                line_code_range_start=start,
                line_code_range_end=end,
                canvas_id=f"https://example.org/iiif/ms/canvas/{number}",
            )

    def get_page(self):
        response = self.client.get(
            reverse("manuscript_stanzas", args=[self.manuscript.siglum])
        )
        self.assertEqual(response.status_code, 200)
        return response

    def stanza_dividers(self, response):
        return [
            (
                group["original"][0]["stanza_line_code_starts"],
                group["current_folio"].folio_number,
            )
            for group in response.context["paired_books"][1]
            if group.get("new_folio")
        ]

    def line_breaks(self, response, column="original"):
        return [
            (line["stanza_line_code_starts"], line["folio_break"].folio_number)
            for group in response.context["paired_books"][1]
            for line in group[column]
            if line.get("folio_break")
        ]

    def test_breaks_between_stanzas(self):
        self.add_folios(("1r", "01.01.00", "01.02.08"), ("1v", "01.03.00", "01.04.08"))

        response = self.get_page()

        self.assertEqual(
            self.stanza_dividers(response), [("01.01.00", "1r"), ("01.03.00", "1v")]
        )
        self.assertEqual(self.line_breaks(response), [])
        self.assertNotContains(response, "folio-divider-inline")

    def segments(self, response, stanza):
        """(folio starting the segment, original codes, translated codes) for
        each segment of a stanza"""
        group = response.context["paired_books"][1][stanza - 1]
        return [
            (
                segment["folio_break"].folio_number if segment["folio_break"] else None,
                [line["stanza_line_code_starts"] for line in segment["original"]],
                [line["stanza_line_code_starts"] for line in segment["translated"]],
            )
            for segment in group["segments"]
        ]

    def test_break_mid_stanza(self):
        # Like Vat1, where 240r starts at line 6 of stanza 6
        self.add_folios(("1r", "01.01.00", "01.02.05"), ("1v", "01.02.06", "01.04.08"))

        response = self.get_page()

        self.assertEqual(self.stanza_dividers(response), [("01.01.00", "1r")])
        self.assertEqual(self.line_breaks(response), [("01.02.06", "1v")])
        lines = [f"01.02.{line:02d}" for line in range(9)]
        self.assertEqual(
            self.segments(response, 2),
            [(None, lines[:6], lines[:6]), ("1v", lines[6:], lines[6:])],
        )

        # One full-width marker between the two parts of the stanza, carrying
        # what tify-sync.js needs to turn the viewer
        html = response.content.decode()
        marker = html.index('data-folio-number="1v"')
        self.assertLess(html.index("Translated 01.02.05"), marker)
        self.assertLess(marker, html.index("Original 01.02.06"))
        self.assertContains(
            response,
            'class="relative flex items-center my-2 text-sm folio-divider '
            'folio-divider-inline" data-folio-number="1v" '
            'data-canvas-id="https://example.org/iiif/ms/canvas/1v"',
        )
        self.assertContains(response, "Folio 1v", count=1)

    def test_break_mid_stanza_without_matching_translation_line(self):
        # The translation has no line 01.02.06, so it's split at the next line
        StanzaTranslated.objects.filter(stanza_line_code_starts="01.02.06").delete()
        self.add_folios(("1r", "01.01.00", "01.02.05"), ("1v", "01.02.06", "01.04.08"))

        response = self.get_page()

        self.assertEqual(
            [
                (folio, translated)
                for folio, _, translated in self.segments(response, 2)
            ],
            [
                (None, [f"01.02.{line:02d}" for line in range(6)]),
                ("1v", ["01.02.07", "01.02.08"]),
            ],
        )

    def test_break_at_first_verse_line_is_between_stanzas(self):
        # The stanza number (.00) falls in the gap before the folio's range
        self.add_folios(("1r", "01.01.00", "01.02.08"), ("1v", "01.03.01", "01.04.08"))

        response = self.get_page()

        self.assertEqual(
            self.stanza_dividers(response), [("01.01.00", "1r"), ("01.03.00", "1v")]
        )
        self.assertEqual(self.line_breaks(response), [])

    def test_ranges_sharing_a_line(self):
        # Like Urb1, where each range ends on the line the next one starts on
        self.add_folios(
            ("9v", "01.01.01", "01.03.01"),
            ("10r", "01.03.01", "01.04.08"),
        )

        response = self.get_page()

        self.assertEqual(
            self.stanza_dividers(response), [("01.01.00", "9v"), ("01.03.00", "10r")]
        )
        self.assertEqual(self.line_breaks(response), [])

    def test_folio_holding_only_the_stanza_number(self):
        # Like NYPL2, where 1v holds only 01.01.00
        self.add_folios(("1v", "01.01.00", "01.01.00"), ("2r", "01.01.01", "01.04.08"))

        response = self.get_page()

        self.assertEqual(self.stanza_dividers(response), [("01.01.00", "1v")])
        self.assertEqual(self.line_breaks(response), [("01.01.01", "2r")])
