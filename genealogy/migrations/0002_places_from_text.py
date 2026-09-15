"""Turn the free-text place fields into links to ``Place`` records.

Existing text such as "Nyeri" becomes one ``Place`` per distinct name
(ignoring case), so records typed the same way end up pointing at the same
place. The reverse migration copies the place names back into text.
"""
import django.db.models.deletion
from django.db import migrations, models

TEXT_FIELDS = [("Person", "birth_place"), ("Person", "death_place"), ("LifeEvent", "place")]


def text_to_places(apps, schema_editor):
    Place = apps.get_model("genealogy", "Place")
    places = {}

    def place_for(text):
        name = (text or "").strip()
        if not name:
            return None
        key = name.lower()
        if key not in places:
            places[key] = Place.objects.create(name=name)
        return places[key]

    for model_name, field in TEXT_FIELDS:
        Model = apps.get_model("genealogy", model_name)
        for obj in Model.objects.exclude(**{field: ""}):
            setattr(obj, f"{field}_record", place_for(getattr(obj, field)))
            obj.save(update_fields=[f"{field}_record"])


def places_to_text(apps, schema_editor):
    for model_name, field in TEXT_FIELDS:
        Model = apps.get_model("genealogy", model_name)
        for obj in Model.objects.exclude(**{f"{field}_record": None}).select_related(f"{field}_record"):
            setattr(obj, field, getattr(obj, f"{field}_record").name[:120])
            obj.save(update_fields=[field])


def place_link():
    return models.ForeignKey(
        null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="genealogy.place"
    )


class Migration(migrations.Migration):
    dependencies = [("genealogy", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Place",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
            ],
        ),
        migrations.AddField(model_name="person", name="birth_place_record", field=place_link()),
        migrations.AddField(model_name="person", name="death_place_record", field=place_link()),
        migrations.AddField(model_name="lifeevent", name="place_record", field=place_link()),
        migrations.RunPython(text_to_places, places_to_text),
        migrations.RemoveField(model_name="person", name="birth_place"),
        migrations.RemoveField(model_name="person", name="death_place"),
        migrations.RemoveField(model_name="lifeevent", name="place"),
        migrations.RenameField(model_name="person", old_name="birth_place_record", new_name="birth_place"),
        migrations.RenameField(model_name="person", old_name="death_place_record", new_name="death_place"),
        migrations.RenameField(model_name="lifeevent", old_name="place_record", new_name="place"),
    ]
