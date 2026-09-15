"""Genealogy data model.

People are connected in two ways:

* ``Union`` - a couple (marriage, customary marriage or partnership). A person
  can have several unions, which is how remarriage is represented.
* ``ParentChild`` - a parent/child link, optionally tied to the union the child
  was born into. Linking children to unions lets us tell full siblings from
  half-siblings and draw the tree with couples above their children.

Around each person sit the details of a life: places (``Place``, nested from
village up to country), where they lived, studied and worked (``Residence``,
``Education``, ``Employment``), free-form ``Tag``s and ``LifeEvent``s.
"""
from collections import defaultdict
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils.text import slugify


def ordinal(number):
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


class Place(models.Model):
    class Kind(models.TextChoices):
        COUNTRY = "country", "Country"
        REGION = "region", "Region / province"
        COUNTY = "county", "County"
        SUBCOUNTY = "subcounty", "Sub-county / district"
        LOCATION = "location", "Location / ward"
        TOWN = "town", "Town / city"
        VILLAGE = "village", "Village"
        OTHER = "other", "Other"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        help_text="The larger place this one is part of, e.g. the county a village is in.",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(fields=["name", "parent"], name="unique_place_name_in_parent")]

    def __str__(self):
        return ", ".join(place.name for place in self.hierarchy()[:2])

    def get_absolute_url(self):
        return reverse("genealogy:place_detail", args=[self.pk])

    def clean(self):
        if self.pk and self.parent_id and self.pk in {place.pk for place in self.parent.hierarchy()}:
            raise ValidationError({"parent": "A place cannot be inside itself."})

    def hierarchy(self):
        """This place followed by each larger place containing it."""
        chain, seen, place = [], set(), self
        while place is not None and place.pk not in seen:
            chain.append(place)
            seen.add(place.pk)
            place = place.parent
        return chain

    @property
    def full_name(self):
        return ", ".join(place.name for place in self.hierarchy())

    def descendant_ids(self):
        """Primary keys of this place and every place inside it."""
        ids, frontier = {self.pk}, [self.pk]
        while frontier:
            frontier = list(Place.objects.filter(parent_id__in=frontier).exclude(pk__in=ids).values_list("pk", flat=True))
            ids.update(frontier)
        return ids

    @classmethod
    def from_text(cls, text):
        """Find or create a place from text such as ``"Othaya, Nyeri, Kenya"``, smallest place first."""
        parts = [part.strip() for part in (text or "").split(",") if part.strip()]
        parent = None
        for name in reversed(parts):
            matches = cls.objects.filter(name__iexact=name)
            if parent is not None:
                matches = matches.filter(parent=parent)
            parent = matches.first() or cls.objects.create(name=name, parent=parent)
        return parent


class Tag(models.Model):
    class Category(models.TextChoices):
        ROLE = "role", "Role or title"
        OCCUPATION = "occupation", "Occupation"
        FAITH = "faith", "Faith & church"
        COMMUNITY = "community", "Community & groups"
        HERITAGE = "heritage", "Heritage & tradition"
        OTHER = "other", "Other"

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("genealogy:tag_detail", args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "tag"
            slug, number = base, 2
            while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, number = f"{base}-{number}", number + 1
            self.slug = slug
        super().save(*args, **kwargs)

    @classmethod
    def from_names(cls, text):
        """Tags for comma-separated names, creating any that don't exist yet."""
        tags = []
        for name in dict.fromkeys(part.strip() for part in (text or "").split(",") if part.strip()):
            tags.append(cls.objects.filter(name__iexact=name).first() or cls.objects.create(name=name))
        return tags


class PersonQuerySet(models.QuerySet):
    def search(self, query):
        """Match every word of ``query`` against any of the name fields."""
        qs = self
        for term in (query or "").split():
            qs = qs.filter(
                Q(first_name__icontains=term)
                | Q(middle_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(maiden_name__icontains=term)
                | Q(nickname__icontains=term)
            )
        return qs


class Person(models.Model):
    class Gender(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"
        OTHER = "O", "Other"
        UNKNOWN = "U", "Unknown"

    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    maiden_name = models.CharField(
        max_length=80, blank=True, help_text="Family name before marriage, if different."
    )
    nickname = models.CharField(
        max_length=80,
        blank=True,
        help_text="Helps tell apart people who share a name, e.g. “Sr.” or “Mama Wanjiru”.",
    )
    gender = models.CharField(max_length=1, choices=Gender.choices, default=Gender.UNKNOWN)

    birth_date = models.DateField(null=True, blank=True)
    birth_date_approx = models.BooleanField("birth date is approximate", default=False)
    birth_place = models.ForeignKey(
        Place, null=True, blank=True, on_delete=models.SET_NULL, related_name="births", verbose_name="place of birth"
    )
    is_living = models.BooleanField(default=True)
    death_date = models.DateField(null=True, blank=True)
    death_place = models.ForeignKey(
        Place, null=True, blank=True, on_delete=models.SET_NULL, related_name="deaths", verbose_name="place of death"
    )
    birth_order = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Position among their parents' children (1 = firstborn). Leave empty to use birth dates.",
    )
    named_after = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="namesakes",
        help_text="The relative this person was named after.",
    )
    homeland = models.ForeignKey(
        Place,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="homeland_of",
        verbose_name="ancestral home",
        help_text="Where their family's roots or land are (mũciĩ).",
    )

    lineage = models.CharField(
        "clan / lineage", max_length=80, blank=True, help_text="Clan or lineage (mbarĩ / mũhĩrĩga)."
    )
    biography = models.TextField(blank=True)
    photo = models.ImageField(upload_to="people/%Y/", blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="people")
    needs_review = models.BooleanField(
        default=False, help_text="Flag records whose details still need to be confirmed."
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PersonQuerySet.as_manager()

    class Meta:
        ordering = ["last_name", "first_name", "middle_name", "pk"]
        verbose_name_plural = "people"
        indexes = [models.Index(fields=["last_name", "first_name"])]

    def __str__(self):
        return self.display_name

    def get_absolute_url(self):
        return reverse("genealogy:person_detail", args=[self.pk])

    def clean(self):
        if self.birth_date and self.birth_date > date.today():
            raise ValidationError({"birth_date": "Date of birth cannot be in the future."})
        if self.birth_date and self.death_date and self.death_date < self.birth_date:
            raise ValidationError({"death_date": "Date of death cannot be before date of birth."})
        if self.pk and self.named_after_id == self.pk:
            raise ValidationError({"named_after": "A person cannot be named after themselves."})
        if self.death_date:
            self.is_living = False

    def save(self, *args, **kwargs):
        if self.death_date:
            self.is_living = False
        super().save(*args, **kwargs)

    # -- Names -------------------------------------------------------------
    @property
    def full_name(self):
        return " ".join(part for part in (self.first_name, self.middle_name, self.last_name) if part)

    @property
    def display_name(self):
        return f"{self.full_name} ({self.nickname})" if self.nickname else self.full_name

    @property
    def initials(self):
        parts = [part for part in (self.first_name, self.last_name) if part]
        return "".join(part[0] for part in parts).upper() or "?"

    # -- Dates -------------------------------------------------------------
    @property
    def birth_year(self):
        return self.birth_date.year if self.birth_date else None

    @property
    def death_year(self):
        return self.death_date.year if self.death_date else None

    def lifespan_text(self, hide_living_birth=False):
        """Short lifespan such as ``1931 – 2008``, ``b. 1990`` or ``Deceased``.

        ``hide_living_birth`` hides birth years of living people, used for
        visitors who are not signed in.
        """
        birth = ""
        if self.birth_date and not (hide_living_birth and self.is_living):
            birth = f"c. {self.birth_year}" if self.birth_date_approx else str(self.birth_year)
        if self.is_living:
            return f"b. {birth}" if birth else ""
        if not birth and not self.death_date:
            return "Deceased"
        return f"{birth or '?'} – {self.death_year or '?'}"

    @property
    def lifespan(self):
        return self.lifespan_text()

    @property
    def age(self):
        if not self.birth_date:
            return None
        end = self.death_date or (date.today() if self.is_living else None)
        if end is None:
            return None
        before_birthday = (end.month, end.day) < (self.birth_date.month, self.birth_date.day)
        return end.year - self.birth_date.year - before_birthday

    # -- Relatives ---------------------------------------------------------
    def parents(self):
        return Person.objects.filter(child_links__child=self).distinct()

    def children(self):
        return Person.objects.filter(parent_links__parent=self).distinct()

    def unions(self):
        return Union.objects.filter(Q(partner_a=self) | Q(partner_b=self)).select_related(
            "partner_a", "partner_b"
        )

    def partners(self):
        return Person.objects.filter(
            Q(unions_as_a__partner_b=self) | Q(unions_as_b__partner_a=self)
        ).distinct()

    @property
    def birth_order_label(self):
        """Such as ``"2nd son · 3rd child"``, ``"1st daughter · Firstborn"`` or ``"Only child"``."""
        from .services.relations import birth_order_labels

        return birth_order_labels([self.pk]).get(self.pk, "")

    @property
    def marital_status(self):
        return marital_status_for(self.unions())

    @property
    def current_residence(self):
        return self.residences.filter(is_current=True).select_related("place").first()

    def record_gaps(self):
        """Details still missing from this record, in plain words."""
        gaps = []
        if not self.birth_date:
            gaps.append("birth date")
        if not self.birth_place_id:
            gaps.append("birthplace")
        if not self.is_living and not self.death_date:
            gaps.append("date of death")
        if not self.photo:
            gaps.append("photo")
        if not self.biography.strip():
            gaps.append("story")
        return gaps


class Union(models.Model):
    class Type(models.TextChoices):
        MARRIAGE = "marriage", "Marriage"
        CUSTOMARY = "customary", "Customary / traditional marriage"
        PARTNERSHIP = "partnership", "Partnership"

    class EndReason(models.TextChoices):
        DIVORCE = "divorce", "Divorce"
        SEPARATION = "separation", "Separation"
        DEATH = "death", "Death of a partner"

    partner_a = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="unions_as_a")
    partner_b = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="unions_as_b",
        help_text="Leave empty if the other partner is unknown.",
    )
    union_type = models.CharField(max_length=20, choices=Type.choices, default=Type.MARRIAGE)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    end_reason = models.CharField(max_length=20, choices=EndReason.choices, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["start_date", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["partner_a", "partner_b"], name="unique_union_pair"),
            models.CheckConstraint(condition=~Q(partner_a=F("partner_b")), name="union_partners_differ"),
        ]

    def __str__(self):
        other = self.partner_b if self.partner_b_id else "unknown partner"
        return f"{self.partner_a} & {other}"

    def clean(self):
        if self.partner_a_id and self.partner_a_id == self.partner_b_id:
            raise ValidationError("A person cannot be in a union with themselves.")
        if (
            self.partner_a_id
            and self.partner_b_id
            and Union.objects.filter(partner_a_id=self.partner_b_id, partner_b_id=self.partner_a_id)
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError("A union between these two people is already recorded.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "The end date cannot be before the start date."})

    @property
    def is_current(self):
        return not self.end_date and not self.end_reason

    def other(self, person):
        """The partner of ``person`` in this union (``None`` if unknown)."""
        person_id = getattr(person, "pk", person)
        return self.partner_b if person_id == self.partner_a_id else self.partner_a


class ParentChild(models.Model):
    class Type(models.TextChoices):
        BIOLOGICAL = "biological", "Biological"
        ADOPTED = "adopted", "Adopted"
        STEP = "step", "Step"
        FOSTER = "foster", "Foster"

    parent = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="child_links")
    child = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="parent_links")
    relationship_type = models.CharField(max_length=20, choices=Type.choices, default=Type.BIOLOGICAL)
    union = models.ForeignKey(
        Union,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_links",
        help_text="The couple this child belongs to, if known.",
    )

    class Meta:
        verbose_name = "parent–child link"
        constraints = [
            models.UniqueConstraint(fields=["parent", "child"], name="unique_parent_child"),
            models.CheckConstraint(condition=~Q(parent=F("child")), name="parent_is_not_child"),
        ]

    def __str__(self):
        return f"{self.parent} → {self.child}"

    def clean(self):
        from .services.relations import ancestors

        if not (self.parent_id and self.child_id):
            return
        if self.parent_id == self.child_id:
            raise ValidationError("A person cannot be their own parent.")
        if self.child_id in ancestors(self.parent_id):
            raise ValidationError(
                f"{self.child} is already an ancestor of {self.parent}, so this link would create a loop."
            )
        if self.relationship_type == self.Type.BIOLOGICAL:
            other_biological = (
                ParentChild.objects.filter(child_id=self.child_id, relationship_type=self.Type.BIOLOGICAL)
                .exclude(pk=self.pk)
                .exclude(parent_id=self.parent_id)
            )
            if other_biological.count() >= 2:
                raise ValidationError(f"{self.child} already has two biological parents recorded.")
        if self.union_id and self.parent_id not in (self.union.partner_a_id, self.union.partner_b_id):
            raise ValidationError({"union": "The parent must be one of the partners in this union."})

    @classmethod
    def attach_unions(cls, child):
        """Tie a child's parent links to the union between their two parents, if one exists."""
        links = list(cls.objects.filter(child=child).select_related("union"))
        parent_ids = {link.parent_id for link in links}
        if len(parent_ids) != 2:
            return
        a, b = parent_ids
        union = Union.objects.filter(
            Q(partner_a_id=a, partner_b_id=b) | Q(partner_a_id=b, partner_b_id=a)
        ).first()
        if union:
            cls.objects.filter(child=child, union__isnull=True).update(union=union)


def marital_status_for(unions, person=None):
    """"Married", "Widowed", "Divorced" and so on, from someone's unions.

    Pass ``person`` so that a marriage which ended with that person's own death
    still reads as "Married" rather than "Widowed".
    """
    unions = list(unions)
    if not unions:
        return ""

    def still_married(union):
        if union.is_current:
            return True
        died = person is not None and person.death_date and union.end_date
        return bool(died and union.end_reason == Union.EndReason.DEATH and union.end_date >= person.death_date)

    current = next((union for union in unions if still_married(union)), None)
    if current:
        return "Partnered" if current.union_type == Union.Type.PARTNERSHIP else "Married"
    reasons = {union.end_reason for union in unions}
    if Union.EndReason.DEATH in reasons:
        return "Widowed"
    if Union.EndReason.DIVORCE in reasons:
        return "Divorced"
    return "Separated"


class YearRange(models.Model):
    """A stretch of someone's life measured in years, which is often all a family remembers."""

    start_year = models.PositiveSmallIntegerField(null=True, blank=True)
    end_year = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = [F("start_year").asc(nulls_last=True), "pk"]

    def clean(self):
        if self.start_year and self.end_year and self.end_year < self.start_year:
            raise ValidationError({"end_year": "The end year cannot be before the start year."})

    @property
    def years(self):
        current = getattr(self, "is_current", False)
        if self.start_year and (self.end_year or current):
            return f"{self.start_year} – {'present' if current and not self.end_year else self.end_year}"
        if self.start_year:
            return f"from {self.start_year}"
        if self.end_year:
            return f"until {self.end_year}"
        return "present" if current else ""


class Residence(YearRange):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="residences")
    place = models.ForeignKey(Place, on_delete=models.PROTECT, related_name="residences")
    is_current = models.BooleanField("lives here now", default=False)
    notes = models.CharField(max_length=200, blank=True)

    class Meta(YearRange.Meta):
        verbose_name = "home"

    def __str__(self):
        return f"{self.person} lived in {self.place}"


class Education(YearRange):
    class Level(models.TextChoices):
        PRIMARY = "primary", "Primary school"
        SECONDARY = "secondary", "Secondary school"
        VOCATIONAL = "vocational", "Vocational / technical"
        COLLEGE = "college", "College"
        UNIVERSITY = "university", "University"
        POSTGRADUATE = "postgraduate", "Postgraduate"
        OTHER = "other", "Other"

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="education")
    institution = models.CharField(max_length=160)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.OTHER)
    field_of_study = models.CharField(max_length=120, blank=True)
    place = models.ForeignKey(Place, null=True, blank=True, on_delete=models.SET_NULL, related_name="education")
    notes = models.CharField(max_length=200, blank=True)

    class Meta(YearRange.Meta):
        verbose_name_plural = "education"

    def __str__(self):
        return f"{self.person} at {self.institution}"


class Employment(YearRange):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="employment")
    employer = models.CharField(max_length=160)
    role = models.CharField(max_length=120, blank=True)
    place = models.ForeignKey(Place, null=True, blank=True, on_delete=models.SET_NULL, related_name="employment")
    is_current = models.BooleanField("works here now", default=False)
    notes = models.CharField(max_length=200, blank=True)

    class Meta(YearRange.Meta):
        verbose_name = "work"
        verbose_name_plural = "work"

    def __str__(self):
        return f"{self.person}: {self.role or 'worked'} at {self.employer}"


class LifeEvent(models.Model):
    class Type(models.TextChoices):
        BIRTH = "birth", "Birth"
        BAPTISM = "baptism", "Baptism / naming"
        EDUCATION = "education", "Education / graduation"
        MARRIAGE = "marriage", "Marriage"
        CAREER = "career", "Career"
        MIGRATION = "migration", "Move / migration"
        ACHIEVEMENT = "achievement", "Achievement"
        DEATH = "death", "Death"
        OTHER = "other", "Other"

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=20, choices=Type.choices, default=Type.OTHER)
    title = models.CharField(max_length=120, blank=True)
    date = models.DateField(null=True, blank=True)
    place = models.ForeignKey(Place, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    description = models.TextField(blank=True)

    class Meta:
        ordering = [F("date").asc(nulls_last=True), "pk"]

    def __str__(self):
        return f"{self.person}: {self.heading}"

    @property
    def heading(self):
        return self.title or self.get_event_type_display()


class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="bookmarked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "person"], name="unique_bookmark")]

    def __str__(self):
        return f"{self.user} ★ {self.person}"


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    message = models.TextField()
    handled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.created_at:%Y-%m-%d})"
