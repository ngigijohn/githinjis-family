"""Fill the database with a large, fictional extended family for developing and demonstrating the site.

Everyone and everything created here is invented. The family spans six
generations from three founding couples and deliberately includes the
situations the site has to handle: marriages between branches, in-laws whose
own parents are recorded, divorce, widowhood, remarriage and half-siblings,
adoption, fostering, a step-parent, a single parent, incomplete records,
relatives living abroad, photos and oral-history recordings.

Children are named following Kikuyu custom: the first son after the father's
father, the second after the mother's father, the first daughter after the
father's mother, the second after the mother's mother, and later children
after their parents' brothers and sisters.
"""
import math
import random
import struct
import wave
from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image, ImageDraw, ImageFont

from accounts.groups import FAMILY_EDITORS
from gallery.models import Photo, Recording
from genealogy.models import (
    Bookmark,
    Education,
    Employment,
    LifeEvent,
    ParentChild,
    Person,
    Place,
    Residence,
    Tag,
    Union,
)

# (name, kind, parent, latitude, longitude)
PLACES = [
    ("Kenya", "country", None, 0.0236, 37.9062),
    ("Nyeri", "county", "Kenya", -0.4197, 36.9476),
    ("Othaya", "town", "Nyeri", -0.5467, 36.9434),
    ("Gatugi", "village", "Othaya", -0.5200, 36.9700),
    ("Karatina", "town", "Nyeri", -0.4833, 37.1333),
    ("Mukurwe-ini", "town", "Nyeri", -0.5606, 37.0489),
    ("Murang'a", "county", "Kenya", -0.7210, 37.1526),
    ("Kangema", "town", "Murang'a", -0.6853, 36.9667),
    ("Kiriaini", "village", "Murang'a", -0.6167, 36.9333),
    ("Kahuro", "village", "Murang'a", -0.6970, 37.0680),
    ("Kiambu", "county", "Kenya", -1.1714, 36.8356),
    ("Limuru", "town", "Kiambu", -1.1136, 36.6422),
    ("Githunguri", "town", "Kiambu", -1.0580, 36.7770),
    ("Thika", "town", "Kiambu", -1.0333, 37.0693),
    ("Kirinyaga", "county", "Kenya", -0.6591, 37.3827),
    ("Kerugoya", "town", "Kirinyaga", -0.4989, 37.2803),
    ("Kagio", "village", "Kirinyaga", -0.6100, 37.2700),
    ("Nairobi", "county", "Kenya", -1.2921, 36.8219),
    ("Kilimani", "location", "Nairobi", -1.2890, 36.7856),
    ("Kasarani", "location", "Nairobi", -1.2210, 36.8990),
    ("Karen", "location", "Nairobi", -1.3190, 36.7073),
    ("Nakuru", "county", "Kenya", -0.3031, 36.0800),
    ("Nakuru Town", "town", "Nakuru", -0.2833, 36.0667),
    ("Njoro", "town", "Nakuru", -0.3290, 35.9440),
    ("Laikipia", "county", "Kenya", 0.3606, 36.7820),
    ("Nanyuki", "town", "Laikipia", 0.0167, 37.0667),
    ("Mombasa", "county", "Kenya", -4.0435, 39.6682),
    ("Nyali", "location", "Mombasa", -4.0226, 39.7200),
    ("United Kingdom", "country", None, 55.3781, -3.4360),
    ("London", "town", "United Kingdom", 51.5072, -0.1276),
    ("Leeds", "town", "United Kingdom", 53.8008, -1.5491),
    ("United States", "country", None, 37.0902, -95.7129),
    ("Boston", "town", "United States", 42.3601, -71.0589),
    ("Dallas", "town", "United States", 32.7767, -96.7970),
    ("Canada", "country", None, 56.1304, -106.3468),
    ("Toronto", "town", "Canada", 43.6532, -79.3832),
    ("United Arab Emirates", "country", None, 23.4241, 53.7781),
    ("Dubai", "town", "United Arab Emirates", 25.2048, 55.2708),
    ("South Africa", "country", None, -30.5595, 22.9375),
    ("Johannesburg", "town", "South Africa", -26.2041, 28.0473),
]
RURAL = ["Gatugi", "Othaya", "Mukurwe-ini", "Kiriaini", "Kahuro", "Kangema", "Githunguri", "Kagio", "Kerugoya"]
TOWNS = ["Karatina", "Nyeri", "Thika", "Limuru", "Nakuru Town", "Nanyuki", "Njoro"]
CITY = ["Kilimani", "Kasarani", "Karen", "Nyali"]
ABROAD = ["London", "Leeds", "Boston", "Dallas", "Toronto", "Dubai", "Johannesburg"]
CLANS = ["Anjirũ", "Ambui", "Angare", "Aithaga", "Aitherandũ", "Agacikũ", "Airimũ", "Ethaga", "Aceera"]

KIKUYU_NAMES = {
    "M": ["Kamau", "Njoroge", "Mwangi", "Kariuki", "Githinji", "Wachira", "Maina", "Ndung'u", "Muriuki", "Kinyua",
          "Waweru", "Gitau", "Macharia", "Mureithi", "Kimani", "Njuguna", "Karanja", "Mbugua", "Ngugi", "Gachoka"],
    "F": ["Wanjiru", "Wambui", "Njeri", "Nyambura", "Wairimu", "Wanjiku", "Wangari", "Wangui", "Muthoni", "Njoki",
          "Wacera", "Wahu", "Waithira", "Wamaitha", "Nduta", "Mumbi", "Nyokabi", "Wanja", "Waceke", "Gathoni"],
}
GIVEN_NAMES = {
    "M": ["John", "Peter", "Joseph", "James", "Samuel", "David", "Daniel", "Paul", "Stephen", "Francis", "Simon", "Charles"],
    "F": ["Mary", "Grace", "Esther", "Lucy", "Margaret", "Jane", "Ruth", "Faith", "Joyce", "Mercy", "Agnes", "Beatrice"],
}
MODERN_NAMES = {
    "M": ["Brian", "Kevin", "Dennis", "Ian", "Ethan", "Liam", "Victor", "Allan", "Mark", "Nathan", "Joel", "Tony"],
    "F": ["Sharon", "Michelle", "Caroline", "Lilian", "Zawadi", "Wendy", "Natalie", "Joy", "Tracy", "Abigail", "Maya", "Ivy"],
    "O": ["Amani", "Imani", "Baraka", "Neema"],
}

MISSION_SCHOOLS = [("Tumutumu Mission School", "Karatina"), ("Mathari Mission School", "Nyeri")]
SECONDARY_SCHOOLS = {
    "M": [("Kagumo High School", "Nyeri"), ("Mang'u High School", "Thika"), ("Nyeri High School", "Nyeri"),
          ("Murang'a High School", "Murang'a"), ("Kiambu High School", "Kiambu")],
    "F": [("Kenya High School", "Nairobi"), ("Loreto Convent Limuru", "Limuru"), ("Bishop Gatimu Ngandu Girls", "Karatina"),
          ("Kahuhia Girls High School", "Murang'a"), ("Othaya Girls High School", "Othaya")],
}
COLLEGES = [("Kagumo Teachers College", "Nyeri", "Education"), ("Kenya Medical Training College", "Nairobi", "Nursing"),
            ("Thika Technical Training Institute", "Thika", "Electrical Engineering"), ("Kenya Polytechnic", "Nairobi", "Accounting")]
UNIVERSITIES = [("University of Nairobi", "Nairobi"), ("Kenyatta University", "Kasarani"), ("Egerton University", "Njoro"),
                ("Dedan Kimathi University of Technology", "Nyeri"), ("Strathmore University", "Karen")]
ABROAD_UNIVERSITIES = {"London": "University of London", "Leeds": "University of Leeds", "Boston": "Northeastern University",
                       "Dallas": "University of Texas at Dallas", "Toronto": "University of Toronto",
                       "Johannesburg": "University of the Witwatersrand", "Dubai": "Dubai Aviation College"}
FIELDS = ["Medicine", "Civil Engineering", "Commerce", "Computer Science", "Agriculture", "Architecture", "Law", "Education"]

# (employer, role, place — "home", "town" or a place name — and the tag it earns)
JOBS = {
    "farm": [("Family farm", "Farmer", "home", "Farmer")],
    "primary": [("Family farm", "Coffee farmer", "home", "Farmer"), ("Othaya Tea Factory", "Tea clerk", "Othaya", "Tea industry"),
                ("Karatina Market", "Trader", "Karatina", "Entrepreneur")],
    "secondary": [("Kenya Railways", "Station clerk", "Nakuru Town", "Railways"), ("Nairobi City Council", "Records clerk", "Nairobi", None),
                  ("Nyeri Coffee Growers Cooperative", "Field officer", "Nyeri", "Farmer"), ("Kangema Hardware", "Shop owner", "Kangema", "Entrepreneur")],
    "college": [("Ministry of Education", "Teacher", "town", "Teacher"), ("Kenyatta National Hospital", "Nurse", "Nairobi", "Nurse"),
                ("Kenya Power", "Electrical technician", "Thika", "Engineer"), ("Mukurwe-ini Health Centre", "Clinical officer", "Mukurwe-ini", "Health worker")],
    "university": [("Highlands Savings Bank", "Branch manager", "Nyeri", "Banker"), ("Rift Valley Millers", "Process engineer", "Nakuru Town", "Engineer"),
                   ("Lakeview Software", "Software developer", "Kilimani", "Technology"), ("Nyali Medical Centre", "Doctor", "Nyali", "Doctor"),
                   ("Jacaranda Architects", "Architect", "Karen", "Architect"), ("Ministry of Agriculture", "Agronomist", "Nanyuki", "Agriculture")],
}
ABROAD_JOBS = {"London": ("City Hospital Trust", "Staff nurse", "Nurse"), "Leeds": ("Northern Rail Engineering", "Systems engineer", "Engineer"),
               "Boston": ("Harborview Pharmacy", "Pharmacist", "Pharmacist"), "Dallas": ("Lone Star Logistics", "Operations manager", None),
               "Toronto": ("Maple Data Labs", "Data analyst", "Technology"), "Dubai": ("Gulf Aviation Services", "Aircraft engineer", "Engineer"),
               "Johannesburg": ("Jacaranda Architects", "Architect", "Architect")}
TAG_CATEGORIES = {
    "Farmer": "occupation", "Tea industry": "occupation", "Entrepreneur": "occupation", "Railways": "occupation",
    "Teacher": "occupation", "Nurse": "occupation", "Engineer": "occupation", "Health worker": "occupation",
    "Banker": "occupation", "Technology": "occupation", "Doctor": "occupation", "Architect": "occupation",
    "Agriculture": "occupation", "Pharmacist": "occupation", "Elder": "role", "Church elder": "faith",
    "Choir member": "faith", "Chama chair": "community", "Independence-era veteran": "heritage",
    "Diaspora": "community", "Athlete": "other",
}

PHOTO_SCENES = ["Wedding day", "Christmas at the family home", "Harvest season", "Graduation", "Family gathering",
                "Visiting the grandparents", "Church choir", "Homecoming", "Ruracio ceremony", "Sunday lunch",
                "First day of school", "Tea picking", "New Year's Day", "Naming ceremony"]
RECORDINGS = [
    ("How the family settled in Gatugi", "Gĩkũyũ", "Othaya",
     "An elder recalls how the first homestead was built and how the land was later shared among the children."),
    ("Wedding songs from Kangema", "Gĩkũyũ", "Kangema",
     "Songs sung at ruracio and wedding ceremonies, with the story behind each one."),
    ("Grandmother's recipes: irio and mũkimo", "English", "Kiriaini",
     "How the family's favourite dishes were cooked for celebrations, and who taught whom."),
    ("Leaving home for London", "English", "London",
     "Moving abroad in the late 1990s, and the ways the family stayed close across the distance."),
    ("The coffee harvest and the cooperative", "Kiswahili", "Karatina",
     "Memories of picking seasons, the cooperative society and what the coffee money paid for."),
]


def ordinal_word(number):
    return ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"][number - 1] if number <= 8 else f"{number}th"


class DemoFamily:
    def __init__(self, rng, limit, today):
        self.rng = rng
        self.limit = limit
        self.today = today
        self.places = {}
        self.tags = {}
        self.people = []
        self.info = {}
        self.father = {}
        self.mother = {}
        self.children_of = defaultdict(list)  # parent pk -> [child]
        self.unions_of = defaultdict(list)  # person pk -> [union]

    # -- Basics --------------------------------------------------------------

    def place(self, name):
        return self.places[name]

    def tag(self, name):
        if name not in self.tags:
            self.tags[name] = Tag.objects.create(name=name, category=TAG_CATEGORIES.get(name, "other"))
        return self.tags[name]

    def create_places(self):
        for name, kind, parent, lat, lon in PLACES:
            self.places[name] = Place.objects.create(
                name=name, kind=kind, parent=self.places.get(parent), latitude=round(lat, 6), longitude=round(lon, 6)
            )

    def year_of(self, person):
        return self.info[person.pk]["year"]

    def alive_in(self, person, year):
        death = person.death_date
        return self.year_of(person) <= year and (death is None or death.year >= year)

    def kikuyu_name(self, person):
        return person.middle_name or person.first_name

    def random_date(self, year):
        return date(year, self.rng.randint(1, 12), self.rng.randint(1, 28))

    def death_date(self, birth):
        year, rng = birth.year, self.rng
        chance = 1.0 if year < 1925 else 0.8 if year < 1945 else 0.4 if year < 1960 else 0.1 if year < 1975 else 0.02
        if rng.random() >= chance:
            return None
        age = rng.randint(58, 96) if year < 1975 else rng.randint(19, 45)
        death = birth + timedelta(days=int(age * 365.25) + rng.randint(0, 300))
        if death < self.today:
            return death
        return self.today - timedelta(days=rng.randint(200, 2500)) if year < 1925 else None

    def given_names(self, gender, year, kikuyu):
        rng = self.rng
        if year < 1925:
            return kikuyu, ""
        if year < 1990:
            return rng.choice(GIVEN_NAMES.get(gender, GIVEN_NAMES["F"])), kikuyu
        return rng.choice(MODERN_NAMES.get(gender, MODERN_NAMES["O"])), kikuyu

    # -- People --------------------------------------------------------------

    def make_person(self, gender, year, *, kikuyu, last, clan, home, gen, homeland, named_after=None, dates=True, birth_order=None):
        first, middle = self.given_names(gender, year, kikuyu)
        birth = self.random_date(year)
        if birth >= self.today:
            birth = self.today - timedelta(days=self.rng.randint(20, 200))
        death = self.death_date(birth)
        person = Person.objects.create(
            first_name=first,
            middle_name=middle,
            last_name=last,
            gender=gender,
            birth_date=birth if dates else None,
            birth_date_approx=dates and birth.year < 1940,
            birth_place=self.place(home),
            is_living=death is None,
            death_date=death,
            lineage=clan,
            named_after=named_after,
            birth_order=birth_order,
        )
        self.people.append(person)
        self.info[person.pk] = {
            "year": birth.year, "home": home, "gen": gen, "homeland": homeland, "moves": [(birth.year, home)],
            "tags": set(), "abroad": None,
        }
        self.plan_life(person)
        return person

    def link(self, parent, child, union=None, rtype=ParentChild.Type.BIOLOGICAL):
        ParentChild.objects.create(parent=parent, child=child, union=union, relationship_type=rtype)
        if rtype == ParentChild.Type.BIOLOGICAL:
            (self.father if parent.gender == "M" else self.mother)[child.pk] = parent
        self.children_of[parent.pk].append(child)

    def siblings(self, person, gender):
        parents = [p for p in (self.father.get(person.pk), self.mother.get(person.pk)) if p]
        seen, result = {person.pk}, []
        for parent in parents:
            for child in self.children_of[parent.pk]:
                if child.pk not in seen and child.gender == gender:
                    seen.add(child.pk)
                    result.append(child)
        return result

    def namesake(self, father, mother, gender, index):
        """Who the ``index``-th son or daughter is named after, following Kikuyu custom."""
        parent_key = self.father if gender == "M" else self.mother
        order = [parent_key.get(father.pk) if father else None, parent_key.get(mother.pk) if mother else None]
        for parent in (father, mother):
            if parent:
                order += self.siblings(parent, gender)
        order = [person for person in order if person]
        return order[index] if index < len(order) else None

    def home_at(self, person, year):
        moves = sorted(self.info[person.pk]["moves"])
        home = moves[0][1]
        for start, place in moves:
            if start <= year:
                home = place
        return home

    def create_child(self, father, mother, union, gen, year, index_in_gender, **extra):
        rng = self.rng
        gender = rng.choice(["M", "F"])
        if year >= 1995 and rng.random() < 0.03:
            gender = "O"
        target = self.namesake(father, mother, "F" if gender == "O" else gender, index_in_gender)
        used = {self.kikuyu_name(c) for p in (father, mother) if p for c in self.children_of[p.pk]}
        pool = [n for n in KIKUYU_NAMES["F" if gender == "O" else gender] if n not in used] or KIKUYU_NAMES["M"]
        kikuyu = self.kikuyu_name(target) if target else rng.choice(pool)
        lead = father or mother
        child = self.make_person(
            gender,
            year,
            kikuyu=kikuyu,
            last=self.kikuyu_name(father) if father else mother.last_name,
            clan=lead.lineage,
            home=self.home_at(lead, year),
            gen=gen,
            homeland=self.info[lead.pk]["homeland"],
            named_after=target,
            **extra,
        )
        for parent in (father, mother):
            if parent:
                self.link(parent, child, union)
        return child

    def make_in_law(self, spouse, gen):
        rng = self.rng
        year = self.year_of(spouse)
        same_sex = year >= 1980 and rng.random() < 0.05 and spouse.gender in ("M", "F")
        if same_sex:
            gender = spouse.gender
        elif spouse.gender == "O":
            gender = rng.choice(["M", "F"])
        else:
            gender = "F" if spouse.gender == "M" else "M"
        offset = rng.randint(-7, 2) if gender == "F" else rng.randint(-2, 7)
        birth_year = min(max(year - offset, 1880), self.today.year - 23)
        homes = RURAL + (TOWNS if birth_year > 1950 else []) + (CITY if birth_year > 1970 else [])
        home = rng.choice(homes)
        clan = rng.choice([c for c in CLANS if c != spouse.lineage])
        kikuyu_pool = KIKUYU_NAMES["F" if gender == "O" else gender]
        person = self.make_person(
            gender, birth_year, kikuyu=rng.choice(kikuyu_pool), last=rng.choice(KIKUYU_NAMES["M"]),
            clan=clan, home=home, gen=gen, homeland=home,
        )
        if 3 <= gen <= 5 and rng.random() < 0.35 and len(self.people) < self.limit * 0.8:
            self.in_law_parents(person, gen - 1)
        return person, same_sex

    def in_law_parents(self, person, gen):
        """Record an in-law's own parents (and so their siblings' naming), a family joining the tree."""
        year, home, clan = self.year_of(person), self.info[person.pk]["home"], person.lineage
        dad = self.make_person("M", year - self.rng.randint(26, 34), kikuyu=self.kikuyu_name(person) if person.gender == "M" else self.rng.choice(KIKUYU_NAMES["M"]),
                               last=person.last_name, clan=clan, home=home, gen=gen, homeland=home)
        mum = self.make_person("F", year - self.rng.randint(22, 28), kikuyu=self.rng.choice(KIKUYU_NAMES["F"]),
                               last=person.last_name, clan=self.rng.choice(CLANS), home=home, gen=gen, homeland=home)
        union = self.marry(dad, mum, min(year - 1, self.year_of(mum) + 22))
        self.link(dad, person, union)
        self.link(mum, person, union)

    def marry(self, a, b, year, kind=None):
        rng = self.rng
        year = min(max(year, self.year_of(a) + 18, self.year_of(b) + 18), self.today.year)
        union_type = kind or (Union.Type.CUSTOMARY if year < 1950 and rng.random() < 0.7 else Union.Type.MARRIAGE)
        union = Union.objects.create(partner_a=a, partner_b=b, union_type=union_type, start_date=self.random_date(year))
        for person in (a, b):
            self.unions_of[person.pk].append(union)
        wife = b if b.gender == "F" and a.gender == "M" else a if a.gender == "F" and b.gender == "M" else None
        husband = a if wife is b else b if wife is a else None
        if wife and year < 1975:
            self.info[wife.pk]["moves"].append((year, self.home_at(husband, year)))
        if wife and year < 1990 and wife.maiden_name == "" and rng.random() < 0.7:
            wife.maiden_name, wife.last_name = wife.last_name, husband.last_name
            wife.save(update_fields=["maiden_name", "last_name"])
        first_death = min((p.death_date for p in (a, b) if p.death_date), default=None)
        if first_death and first_death.year >= year:
            union.end_date, union.end_reason = first_death, Union.EndReason.DEATH
            union.save(update_fields=["end_date", "end_reason"])
        elif year >= 1965 and rng.random() < 0.1:
            end = year + rng.randint(5, 12)
            if end < self.today.year:
                union.end_date, union.end_reason = self.random_date(end), Union.EndReason.DIVORCE
                union.save(update_fields=["end_date", "end_reason"])
        return union

    # -- Life stories ----------------------------------------------------------

    def plan_life(self, person):
        rng, info = self.rng, self.info[person.pk]
        year, home = info["year"], info["home"]
        end = person.death_date.year if person.death_date else self.today.year
        gender = person.gender if person.gender in ("M", "F") else rng.choice(["M", "F"])
        moves, tags = info["moves"], info["tags"]

        def study(institution, level, place, start, finish, field=""):
            if start > end:
                return False
            Education.objects.create(
                person=person, institution=institution, level=level, field_of_study=field, place=self.place(place),
                start_year=start, end_year=finish if finish <= end and finish <= self.today.year else None,
            )
            return finish <= end

        roll = rng.random()
        if year < 1925:
            stages = ["mission"] if roll < 0.4 else []
        elif year < 1945:
            stages = ["primary"] + (["secondary"] if roll < 0.3 else []) + (["college"] if roll < 0.15 else [])
        elif year < 1975:
            stages = ["primary"] + (["secondary"] if roll < 0.75 else []) + ([rng.choice(["college", "university"])] if roll < 0.45 else [])
        else:
            stages = ["primary", "secondary"] + ([rng.choice(["college", "university", "university"])] if roll < 0.7 else [])
        abroad = year >= 1960 and info["gen"] >= 4 and rng.random() < 0.15
        highest = "farm"
        for stage in stages:
            if stage == "mission":
                name, place = rng.choice(MISSION_SCHOOLS)
                if study(name, Education.Level.PRIMARY, place, year + 10, year + 14):
                    highest = "primary"
            elif stage == "primary":
                if study(f"{home} Primary School", Education.Level.PRIMARY, home, year + 6, year + 13):
                    highest = "primary"
            elif stage == "secondary":
                name, place = rng.choice(SECONDARY_SCHOOLS[gender])
                if study(name, Education.Level.SECONDARY, place, year + 14, year + 17):
                    highest = "secondary"
            elif stage == "college":
                name, place, field = rng.choice(COLLEGES)
                if study(name, Education.Level.COLLEGE, place, year + 18, year + 21, field):
                    highest = "college"
                    moves.append((year + 18, place))
            else:
                if abroad and year >= 1970:
                    city = rng.choice(list(ABROAD_UNIVERSITIES))
                    name, place = ABROAD_UNIVERSITIES[city], city
                    info["abroad"] = city
                else:
                    name, place = rng.choice(UNIVERSITIES)
                if study(name, Education.Level.UNIVERSITY, place, year + 19, year + 23, rng.choice(FIELDS)):
                    highest = "university"
                    moves.append((year + 19, place))

        start = year + {"farm": 18, "primary": 18, "secondary": 20, "college": 22, "university": 24}[highest]
        if start > min(end, self.today.year):
            return
        if abroad:
            city = info["abroad"] or rng.choice(ABROAD)
            info["abroad"] = city
            employer, role, tag = ABROAD_JOBS[city]
            place = city
            moves.append((start, city))
            tags.add("Diaspora")
        else:
            employer, role, place, tag = rng.choice(JOBS[highest])
            place = home if place == "home" else rng.choice(TOWNS) if place == "town" else place
            if place != home:
                moves.append((start, place))
        retire = start + rng.randint(28, 40)
        current = person.is_living and retire >= self.today.year
        Employment.objects.create(
            person=person, employer=employer, role=role, place=self.place(place), start_year=start,
            end_year=None if current else min(retire, end), is_current=current,
        )
        if tag:
            tags.add(tag)
        if not current and not abroad and highest != "farm" and rng.random() < 0.5 and retire < end:
            moves.append((retire, info["homeland"]))

        if not person.is_living and year < 1935 and rng.random() < 0.35:
            tags.add("Elder")
        if 1920 <= year <= 1935 and rng.random() < 0.15:
            tags.add("Independence-era veteran")
        if person.gender == "F" and 1940 <= year <= 1975 and rng.random() < 0.3:
            tags.add("Chama chair")
        if end - year >= 50 and rng.random() < 0.12:
            tags.add("Church elder")
        if rng.random() < 0.08:
            tags.add("Choir member")
        if year >= 1990 and rng.random() < 0.08:
            tags.add("Athlete")

    # -- Generations -------------------------------------------------------------

    def child_count(self, gen, start_year):
        low, high = {2: (4, 7), 3: (3, 6), 4: (2, 5), 5: (1, 4), 6: (0, 3)}.get(gen, (0, 2))
        if start_year > 2015:
            high = min(high, 2)
        return self.rng.randint(low, high)

    def have_children(self, couple, gen):
        rng = self.rng
        union, a, b = couple["union"], couple["a"], couple["b"]
        father = a if a.gender == "M" else b if b.gender == "M" else None
        mother = b if b.gender == "F" else a if a.gender == "F" else None
        start = union.start_date.year
        finish = union.end_date.year if union.end_date else self.today.year
        if couple.get("same_sex"):
            year = start + rng.randint(2, 6)
            if year <= self.today.year:
                child = self.create_child(a, None, union, gen, year, 5)
                ParentChild.objects.filter(child=child).update(relationship_type=ParentChild.Type.ADOPTED)
                self.link(b, child, union, ParentChild.Type.ADOPTED)
                return [child]
            return []
        if not (father and mother):
            father, mother = a, b
        kids, counts = [], defaultdict(int)
        year = start + rng.randint(1, 3)
        last_year = min(finish, self.year_of(mother) + 44, self.today.year)
        for _ in range(min(self.child_count(gen, start), couple.get("cap", 9))):
            if year > last_year or len(self.people) >= self.limit + 25:
                break
            if not (self.alive_in(father, year - 1) and self.alive_in(mother, year)):
                break
            child = self.create_child(father, mother, union, gen, year, counts["pending"], **couple.get("child_extra", {}))
            counts["pending"] = 0
            kids.append(child)
            year += rng.randint(2, 4)
        # Recompute namesakes by gender order now that the siblings exist.
        return kids

    def can_marry(self, person):
        years = (person.death_date.year if person.death_date else self.today.year) - self.year_of(person)
        chance = 0.88 if self.year_of(person) < 1990 else 0.45
        return years >= 23 and not self.unions_of[person.pk] and self.rng.random() < chance

    def build(self):
        rng = self.rng
        self.create_places()

        founders = [
            ("A", ("Githinji", "Kamau", "Anjirũ", "Gatugi", 1891), ("Nyambura", "Wachira", "Ambui", "Kiriaini", 1896)),
            ("B", ("Mbugua", "Njuguna", "Aithaga", "Kangema", 1894), ("Wairimu", "Kinyua", "Angare", "Kahuro", 1899)),
            ("C", ("Kinyanjui", "Gitau", "Airimũ", "Githunguri", 1897), ("Gathoni", "Macharia", "Ethaga", "Limuru", 1902)),
        ]
        couples = []
        for key, husband, wife in founders:
            h = self.make_person("M", husband[4], kikuyu=husband[0], last=husband[1], clan=husband[2], home=husband[3], gen=1, homeland=husband[3])
            w = self.make_person("F", wife[4], kikuyu=wife[0], last=wife[1], clan=wife[2], home=wife[3], gen=1, homeland=wife[3])
            union = self.marry(h, w, husband[4] + 24)
            couple = {"union": union, "a": h, "b": w, "key": key}
            if key == "C":
                couple["child_extra"] = {"dates": False}
            couples.append(couple)

        crossings = {2: ("A", "C"), 3: ("A", "B"), 4: ("B", "A")}
        for gen in range(2, 7):
            born = []
            # Share the remaining people across the generations still to come, so small families still run deep.
            cap = max(1, round((self.limit - len(self.people)) / max(1, len(couples) * (7 - gen) * 1.2)))
            for couple in couples:
                couple["cap"] = cap
                kids = self.fix_gender_order(self.have_children(couple, gen), couple)
                if couple["key"] == "C" and gen == 2:
                    for order, kid in enumerate(kids, start=1):
                        kid.birth_order = order
                        kid.save(update_fields=["birth_order"])
                born += [(kid, couple["key"]) for kid in kids]
            rng.shuffle(born)
            couples = []
            crossed = False
            married = set()
            for person, key in born:
                if person.pk in married or not self.can_marry(person):
                    continue
                partner, same_sex = None, False
                if gen in crossings and not crossed and key in crossings[gen]:
                    other_key = crossings[gen][1] if key == crossings[gen][0] else crossings[gen][0]
                    partner = next(
                        (
                            other for other, k in born
                            if k == other_key and other.pk not in married and other.gender in {"M": "F", "F": "M"}.get(person.gender, "")
                            and abs(self.year_of(other) - self.year_of(person)) <= 7 and not self.unions_of[other.pk]
                            and (other.death_date is None or other.death_date.year - self.year_of(other) >= 23)
                        ),
                        None,
                    )
                    crossed = partner is not None
                if partner is None:
                    partner, same_sex = self.make_in_law(person, gen)
                married |= {person.pk, partner.pk}
                start = max(self.year_of(person), self.year_of(partner)) + rng.randint(22, 29)
                union = self.marry(person, partner, start, Union.Type.PARTNERSHIP if same_sex else None)
                couples.append({"union": union, "a": person, "b": partner, "key": key, "same_sex": same_sex})
                couples += self.remarry(person, partner, union, gen, key)

        self.special_cases()
        self.finish()
        return self

    def fix_gender_order(self, kids, couple):
        """Name each son and daughter after the right relative now that birth order is known."""
        a, b = couple["a"], couple["b"]
        father = a if a.gender == "M" else b if b.gender == "M" else None
        mother = b if b.gender == "F" else a if a.gender == "F" else None
        if not (father and mother) or couple.get("same_sex"):
            return kids
        counts = defaultdict(int)
        for kid in kids:
            gender = "F" if kid.gender == "O" else kid.gender
            target = self.namesake(father, mother, gender, counts[gender])
            counts[gender] += 1
            if target and target.pk != kid.pk:
                kid.named_after = target
                name = self.kikuyu_name(target)
                if kid.middle_name:
                    kid.middle_name = name
                else:
                    kid.first_name = name
            else:
                kid.named_after = None
            kid.save(update_fields=["named_after", "first_name", "middle_name"])
        return kids

    def remarry(self, person, partner, union, gen, key):
        if not union.end_reason:
            return []
        survivors = [p for p in (person, partner) if p.death_date is None or p.death_date > union.end_date]
        extra = []
        for survivor in survivors:
            if self.info[survivor.pk]["gen"] != gen or survivor is partner and self.info[partner.pk].get("in_law_done"):
                continue
            age = union.end_date.year - self.year_of(survivor)
            if age < 55 and self.rng.random() < 0.55 and len(self.people) < self.limit:
                new_partner, same_sex = self.make_in_law(survivor, gen)
                second = self.marry(survivor, new_partner, union.end_date.year + self.rng.randint(1, 4),
                                    Union.Type.PARTNERSHIP if same_sex else None)
                extra.append({"union": second, "a": survivor, "b": new_partner, "key": key, "same_sex": same_sex, "step_from": union})
                break
        return extra

    def special_cases(self):
        rng = self.rng
        people = [p for p in self.people if p.is_living and self.info[p.pk]["gen"] in (4, 5)]
        # A step-parent: the new partner of someone who remarried takes on their earlier children.
        for union in Union.objects.filter(start_date__isnull=False).order_by("pk"):
            earlier = Union.objects.filter(end_reason__in=[Union.EndReason.DIVORCE, Union.EndReason.DEATH]).filter(
                partner_a=union.partner_a, start_date__lt=union.start_date
            ).first()
            if earlier:
                for child in self.children_of[union.partner_a.pk][:2]:
                    if not ParentChild.objects.filter(parent=union.partner_b, child=child).exists():
                        self.link(union.partner_b, child, union, ParentChild.Type.STEP)
                break
        couples = [u for u in Union.objects.filter(end_reason="", partner_b__isnull=False).select_related("partner_a", "partner_b")
                   if u.partner_a.is_living and self.info[u.partner_a.pk]["gen"] >= 4 and self.year_of(u.partner_a) < 1990]
        rng.shuffle(couples)
        for union, rtype in zip(couples[:2], [ParentChild.Type.ADOPTED, ParentChild.Type.FOSTER]):
            year = min(union.start_date.year + rng.randint(6, 12), self.today.year - 1)
            lead = union.partner_a
            child = self.make_person(rng.choice(["M", "F"]), year, kikuyu=rng.choice(KIKUYU_NAMES["M"]), last=union.partner_a.last_name,
                                     clan=lead.lineage, home=self.home_at(lead, year), gen=self.info[lead.pk]["gen"] + 1,
                                     homeland=self.info[lead.pk]["homeland"])
            self.link(union.partner_a, child, union, rtype)
            self.link(union.partner_b, child, union, rtype)
        singles = [p for p in people if p.gender == "F" and not self.unions_of[p.pk] and self.year_of(p) < 1998]
        if singles:
            mum = rng.choice(singles)
            year = min(self.year_of(mum) + rng.randint(24, 30), self.today.year - 1)
            child = self.make_person(rng.choice(["M", "F"]), year, kikuyu=rng.choice(KIKUYU_NAMES["F"]), last=mum.last_name,
                                     clan=mum.lineage, home=self.home_at(mum, year), gen=self.info[mum.pk]["gen"] + 1,
                                     homeland=self.info[mum.pk]["homeland"])
            self.link(mum, child)
        early = [p for p in self.people if self.info[p.pk]["gen"] == 2 and not self.unions_of[p.pk]]
        if early:
            unknown = early[0]
            unknown.gender = Person.Gender.UNKNOWN
            unknown.save(update_fields=["gender"])

    # -- Finishing touches ---------------------------------------------------------

    def finish(self):
        rng = self.rng
        for person in self.people:
            info = self.info[person.pk]
            end_year = person.death_date.year if person.death_date else None
            moves = []
            for start, place in sorted(info["moves"]):
                if end_year and start > end_year:
                    continue
                if moves and moves[-1][1] == place:
                    continue
                if moves and moves[-1][0] == start:
                    moves[-1] = (start, place)
                else:
                    moves.append((start, place))
            for index, (start, place) in enumerate(moves):
                last = index == len(moves) - 1
                Residence.objects.create(
                    person=person, place=self.place(place), start_year=start,
                    end_year=None if last and person.is_living else (moves[index + 1][0] if not last else end_year),
                    is_current=last and person.is_living,
                )
                if index and start - info["year"] >= 17:
                    LifeEvent.objects.create(person=person, event_type=LifeEvent.Type.MIGRATION, title=f"Moved to {place}",
                                             date=self.random_date(start), place=self.place(place))
            if person.death_date:
                person.death_place = self.place(moves[-1][1])
                LifeEvent.objects.create(person=person, event_type=LifeEvent.Type.DEATH, title="Passed away",
                                         date=person.death_date, place=person.death_place)
            for education in person.education.filter(level__in=["college", "university"], end_year__isnull=False):
                LifeEvent.objects.create(person=person, event_type=LifeEvent.Type.EDUCATION, title=f"Graduated from {education.institution}",
                                         date=self.random_date(education.end_year), place=education.place)
            person.homeland = self.place(info["homeland"])
            person.tags.set([self.tag(name) for name in sorted(info["tags"])])

            # Leave some records incomplete, the way real family records are.
            if info["year"] >= 1990 and rng.random() < 0.1:
                person.birth_place = None
            if info["year"] >= 1985 and rng.random() < 0.08:
                person.birth_date = None
            person.needs_review = rng.random() < 0.05
            person.biography = "" if rng.random() < 0.15 else self.biography(person)
            person.save()

        for union in Union.objects.filter(start_date__isnull=False).select_related("partner_a", "partner_b"):
            for person, other in ((union.partner_a, union.partner_b), (union.partner_b, union.partner_a)):
                if person and other:
                    LifeEvent.objects.create(person=person, event_type=LifeEvent.Type.MARRIAGE, title=f"Married {other.first_name}",
                                             date=union.start_date, place=self.place(self.home_at(union.partner_a, union.start_date.year)))

    def biography(self, person):
        rng = self.rng
        subject, possessive = {"M": ("He", "his"), "F": ("She", "her")}.get(person.gender, ("They", "their"))
        verb_was = "were" if subject == "They" else "was"
        info = self.info[person.pk]
        sentences = []
        father, mother = self.father.get(person.pk), self.mother.get(person.pk)
        birth = f"{person.first_name} {verb_was} born"
        if person.birth_place:
            birth += f" in {person.birth_place}"
        if person.birth_date:
            birth += f" {'around' if person.birth_date_approx else 'in'} {person.birth_date.year}"
        if father and mother:
            birth += f", to {father.first_name} and {mother.first_name}"
        sentences.append(birth + ".")
        if person.named_after:
            target = person.named_after
            side = "father's" if father and target in (self.father.get(father.pk), self.mother.get(father.pk)) else "mother's"
            role = "father" if target.gender == "M" else "mother"
            relation = f"{possessive} {side} {role}" if target not in (father, mother) else f"{possessive} {role}"
            sentences.append(f"{subject} {verb_was} named after {relation}, {target.first_name}.")
        schools = list(person.education.all())
        if schools:
            names = [school.institution for school in schools]
            listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and then {names[-1]}"
            sentence = f"{subject} went to {listed}"
            studied = next((school.field_of_study for school in schools if school.field_of_study), "")
            if studied:
                sentence += f", where {subject.lower()} studied {studied.lower()}"
            sentences.append(sentence + ".")
        for job in person.employment.all():
            when = f" from {job.start_year}" + (f" to {job.end_year}" if job.end_year else "")
            tense = "works" if job.is_current else "worked"
            if subject == "They":
                tense = "work" if job.is_current else "worked"
            sentences.append(f"{subject} {tense} as {'an' if job.role[0].lower() in 'aeiou' else 'a'} {job.role.lower()} at {job.employer} in {job.place.name}{'' if job.is_current else when}.")
        moves = [r for r in person.residences.all()][1:]
        if moves:
            places = [r.place.name for r in moves]
            sentences.append(f"Over the years {subject.lower()} lived in {', '.join(places[:-1]) + ' and ' if len(places) > 1 else ''}{places[-1]}.")
        unions = self.unions_of[person.pk]
        for union in unions:
            other = union.other(person)
            kids = ParentChild.objects.filter(parent=person, union=union).count()
            line = f"{subject} married {other.first_name} {other.last_name} in {union.start_date.year}"
            if kids:
                line += f"; they had {kids} {'child' if kids == 1 else 'children'}"
            sentences.append(line + ".")
        tags = info["tags"]
        if "Church elder" in tags:
            sentences.append(f"A respected church elder, {subject.lower()} {verb_was} often asked to lead family gatherings.")
        if "Chama chair" in tags:
            sentences.append(f"{subject} chaired a women's chama that helped members buy land and pay school fees.")
        if "Independence-era veteran" in tags:
            sentences.append(f"{possessive.capitalize()} memories of the years before independence are part of the family's oral history.")
        if person.death_date:
            sentences.append(f"{subject} died in {person.death_date.year}" + (f" in {person.death_place.name}." if person.death_place else "."))
        if rng.random() < 0.3:
            sentences.append(rng.choice([
                f"Relatives remember {possessive} laughter and {possessive} love of storytelling.",
                f"{subject} {verb_was} known for a generous table and an open door.",
                f"Family members describe {person.first_name} as patient, hardworking and quick to help.",
            ]))
        return " ".join(sentences)

    # -- Media -----------------------------------------------------------------------

    def photos(self, count=14):
        rng = self.rng
        unions = list(Union.objects.filter(start_date__isnull=False).select_related("partner_a", "partner_b"))
        rng.shuffle(unions)
        made = 0
        for union, scene in zip(unions, PHOTO_SCENES * 2):
            if made >= count:
                break
            year = min(union.start_date.year + rng.randint(0, 25), self.today.year)
            people = [p for p in (union.partner_a, union.partner_b) if p and self.alive_in(p, year)]
            people += [c for c in self.children_of[union.partner_a.pk] if self.alive_in(c, year)][:5]
            if not people:
                continue
            photo = Photo(caption=f"{scene}, {year}", date_taken=self.random_date(year),
                          description=f"A demo image generated for {', '.join(p.first_name for p in people)}.")
            photo.image.save(f"demo-{made + 1:02d}.jpg", ContentFile(scene_image(rng, scene, year, len(people))), save=True)
            photo.people.set(people)
            made += 1
        return made

    def recordings(self):
        rng = self.rng
        elders = sorted((p for p in self.people if p.is_living and self.year_of(p) < 1965), key=self.year_of)
        made = 0
        for (title, language, place, description), speaker in zip(RECORDINGS, elders or self.people):
            recorded = date(rng.randint(2012, min(2025, self.today.year)), rng.randint(1, 12), rng.randint(1, 28))
            seconds = rng.randint(6, 12)
            recording = Recording(
                title=title, language=language, recorded_on=recorded, place=self.place(place), description=description,
                duration_seconds=seconds,
                transcript=f"[Demo transcript. The audio is a placeholder tone.]\n\n{speaker.first_name}: {description}",
            )
            recording.audio.save(f"demo-recording-{made + 1}.wav", ContentFile(tone_wav(rng, seconds)), save=True)
            recording.speakers.set([speaker])
            recording.people.set([p for p in (self.father.get(speaker.pk), self.mother.get(speaker.pk)) if p] + [speaker])
            made += 1
        return made


def scene_image(rng, caption, year, figures):
    width, height = 1200, 800
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    old = year < 1975
    top = (222, 205, 170) if old else rng.choice([(150, 200, 235), (250, 196, 150), (176, 214, 232)])
    bottom = (140, 118, 86) if old else (86, 140, 98)
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)))
    draw.ellipse([880, 90, 1000, 210], fill=(250, 236, 190) if not old else (240, 226, 196))
    for layer in range(3):
        base = height * 0.52 + layer * 70
        phase = rng.random() * 6
        points = [(0, height)] + [(x, base + 38 * math.sin(x / 150 + phase)) for x in range(0, width + 40, 40)] + [(width, height)]
        shade = (150 - layer * 20, 126 - layer * 18, 92 - layer * 14) if old else (96 - layer * 18, 148 - layer * 22, 96 - layer * 16)
        draw.polygon(points, fill=shade)
    figures = max(2, min(figures, 7))
    for i in range(figures):
        x = width * (0.22 + 0.56 * i / (figures - 1))
        size = rng.randint(70, 95)
        body = (48, 44, 40) if old else rng.choice([(40, 70, 120), (150, 60, 80), (60, 90, 70), (90, 60, 120)])
        draw.rounded_rectangle([x - size * 0.45, 600 - size * 1.6, x + size * 0.45, 700], radius=30, fill=body)
        draw.ellipse([x - size * 0.3, 600 - size * 2.25, x + size * 0.3, 600 - size * 1.65], fill=(92, 64, 48))
    draw.rectangle([0, height - 88, width, height], fill=(24, 28, 26))
    draw.text((32, height - 66), f"{caption}, {year} · demo image", fill=(240, 236, 226), font=ImageFont.load_default(size=34))
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=82)
    return buffer.getvalue()


def tone_wav(rng, seconds, rate=8000):
    base = rng.choice([196.0, 220.0, 247.0])
    frames = bytearray()
    for i in range(seconds * rate):
        t = i / rate
        envelope = min(1.0, t * 2, (seconds - t) * 2)
        value = envelope * (math.sin(2 * math.pi * base * t) + 0.4 * math.sin(2 * math.pi * base * 1.5 * t))
        value *= 0.6 + 0.4 * math.sin(2 * math.pi * 0.4 * t)
        frames += struct.pack("<h", int(value * 5000))
    buffer = BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(bytes(frames))
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Fill the database with a large fictional family for development and demos."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete all people, places, tags, photos and recordings first.")
        parser.add_argument("--people", type=int, default=180, help="Rough number of people to create (default 180).")
        parser.add_argument("--seed", type=int, default=2026, help="Random seed. The same seed builds the same family.")
        parser.add_argument("--no-media", action="store_true", help="Skip the generated photos and audio recordings.")
        parser.add_argument("--no-users", action="store_true", help="Don't create the demo admin and editor accounts.")

    def handle(self, *args, reset=False, people=180, seed=2026, no_media=False, no_users=False, **options):
        if Person.objects.exists() and not reset:
            self.stdout.write(self.style.WARNING("People already exist. Re-run with --reset to replace everything."))
            return
        with transaction.atomic():
            if reset:
                Recording.objects.all().delete()
                Photo.objects.all().delete()
                Person.objects.all().delete()
                Place.objects.all().delete()
                Tag.objects.all().delete()
            family = DemoFamily(random.Random(seed), people, date.today()).build()
            photos = recordings = 0
            if not no_media:
                photos, recordings = family.photos(), family.recordings()
            accounts = [] if no_users else self.create_users(family)

        self.stdout.write(self.style.SUCCESS(
            f"Created a demo family of {Person.objects.count()} people in {Union.objects.count()} unions, "
            f"{Place.objects.count()} places, {Tag.objects.count()} tags, {photos} photos and {recordings} recordings."
        ))
        for username in accounts:
            self.stdout.write(f"  Demo account: {username} / {username}")

    def create_users(self, family):
        created = []
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "", "admin")
            created.append("admin")
        if not User.objects.filter(username="editor").exists():
            editor = User.objects.create_user("editor", password="editor")
            editor.groups.add(Group.objects.get_or_create(name=FAMILY_EDITORS)[0])
            created.append("editor")
        admin = User.objects.get(username="admin")
        for person in family.rng.sample(family.people, min(3, len(family.people))):
            Bookmark.objects.get_or_create(user=admin, person=person)
        return created
