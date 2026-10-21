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
from manuscript.models import Folio, SingleManuscript
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
