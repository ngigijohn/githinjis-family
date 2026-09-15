"""Load the family members and photographs from the original 2021 concept site."""
import re
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image, ImageOps

from gallery.models import Photo
from genealogy.models import ParentChild, Person, Union

SEED_PHOTOS = Path(__file__).resolve().parents[2] / "seed" / "photos"
REVIEW_NOTE = "Imported from the original 2021 family website. Please confirm names, dates and relationships."


def _resized_jpeg(path, max_side=1600):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((max_side, max_side))
        buffer = BytesIO()
        image.convert("RGB").save(buffer, "JPEG", quality=85, optimize=True)
    return ContentFile(buffer.getvalue())


class Command(BaseCommand):
    help = "Seed the database with the family from the original concept site (flagged for review)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete all people and photos before seeding.")
        parser.add_argument("--no-photos", action="store_true", help="Skip importing the concept photographs.")

    @transaction.atomic
    def handle(self, *args, reset=False, no_photos=False, **options):
        if reset:
            Photo.objects.all().delete()
            Person.objects.all().delete()
        elif Person.objects.exists():
            self.stdout.write(self.style.WARNING("People already exist. Re-run with --reset to replace them."))
            return

        def person(first, last, gender, nickname="", living=True):
            return Person.objects.create(
                first_name=first,
                last_name=last,
                gender=gender,
                nickname=nickname,
                is_living=living,
                needs_review=True,
                biography=REVIEW_NOTE,
            )

        def family(partner_a, partner_b, children):
            union = Union.objects.create(partner_a=partner_a, partner_b=partner_b)
            for child in children:
                for parent in (partner_a, partner_b):
                    ParentChild.objects.create(parent=parent, child=child, union=union)

        # Generation 1: great-grandparents
        peter_sr = person("Peter", "Mburu", "M", nickname="Sr.", living=False)
        wangui = person("Wangui", "", "F", living=False)
        # Generation 2: grandparents
        john_sr = person("John", "Ngigi", "M", nickname="Sr.")
        esther_mbaire = person("Esther", "Mbaire", "F")
        # Generation 3: parents, uncle and aunt
        george = person("George", "Githinji", "M")
        peter = person("Peter", "Mburu", "M")
        wambui = person("Wambui", "", "F")
        esther_wangui = person("Esther", "Wangui", "F")
        # Generation 4: John and his siblings
        john = person("John", "Ngigi", "M")
        peter_miringu = person("Peter", "Miringu", "M")
        victor = person("Victor", "Karanja", "M")
        michelle = person("Michelle", "Mbaire", "F")

        family(peter_sr, wangui, [john_sr])
        family(john_sr, esther_mbaire, [george, peter, wambui])
        family(george, esther_wangui, [john, peter_miringu, victor, michelle])

        self.stdout.write(self.style.SUCCESS(f"Created {Person.objects.count()} people across 4 generations."))

        if no_photos:
            return
        if not SEED_PHOTOS.exists():
            self.stdout.write(self.style.WARNING(f"No seed photos found in {SEED_PHOTOS}."))
            return
        paths = sorted(SEED_PHOTOS.glob("*.jpg"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
        for number, path in enumerate(paths, start=1):
            photo = Photo(caption=f"Family moments #{number}", description="From the original family website.")
            photo.image.save(f"family-{number:02d}.jpg", _resized_jpeg(path), save=True)
        self.stdout.write(self.style.SUCCESS(f"Imported {len(paths)} photos."))
