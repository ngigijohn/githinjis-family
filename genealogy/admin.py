from django.contrib import admin

from .models import (
    Bookmark,
    ContactMessage,
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


class ParentLinkInline(admin.TabularInline):
    model = ParentChild
    fk_name = "child"
    extra = 0
    autocomplete_fields = ["parent", "union"]
    verbose_name = "parent"
    verbose_name_plural = "parents"


class ChildLinkInline(admin.TabularInline):
    model = ParentChild
    fk_name = "parent"
    extra = 0
    autocomplete_fields = ["child", "union"]
    verbose_name = "child"
    verbose_name_plural = "children"


class UnionInline(admin.TabularInline):
    model = Union
    fk_name = "partner_a"
    extra = 0
    autocomplete_fields = ["partner_b"]
    fields = ["partner_b", "union_type", "start_date", "end_date", "end_reason"]
    verbose_name = "union"
    verbose_name_plural = "unions (recorded with this person as first partner)"


class ResidenceInline(admin.TabularInline):
    model = Residence
    extra = 0
    autocomplete_fields = ["place"]
    fields = ["place", "start_year", "end_year", "is_current", "notes"]


class EducationInline(admin.TabularInline):
    model = Education
    extra = 0
    autocomplete_fields = ["place"]
    fields = ["institution", "level", "field_of_study", "place", "start_year", "end_year"]


class EmploymentInline(admin.TabularInline):
    model = Employment
    extra = 0
    autocomplete_fields = ["place"]
    fields = ["employer", "role", "place", "start_year", "end_year", "is_current"]


class LifeEventInline(admin.TabularInline):
    model = LifeEvent
    extra = 0
    autocomplete_fields = ["place"]
    fields = ["event_type", "title", "date", "place"]


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ["display_name", "gender", "lifespan", "lineage", "is_living", "needs_review", "updated_at"]
    list_filter = ["gender", "is_living", "needs_review", "lineage", "tags"]
    search_fields = ["first_name", "middle_name", "last_name", "maiden_name", "nickname"]
    readonly_fields = ["created_by", "created_at", "updated_at"]
    autocomplete_fields = ["birth_place", "death_place", "homeland", "named_after", "tags"]
    inlines = [
        ParentLinkInline,
        ChildLinkInline,
        UnionInline,
        ResidenceInline,
        EducationInline,
        EmploymentInline,
        LifeEventInline,
    ]
    fieldsets = [
        ("Name", {"fields": [("first_name", "middle_name", "last_name"), ("maiden_name", "nickname"), "gender"]}),
        (
            "Life",
            {
                "fields": [
                    ("birth_date", "birth_date_approx"),
                    "birth_place",
                    "is_living",
                    ("death_date", "death_place"),
                ]
            },
        ),
        ("Family", {"fields": ["birth_order", "named_after", "homeland", "lineage"]}),
        ("Story", {"fields": ["photo", "biography", "tags", "needs_review"]}),
        ("Record", {"fields": ["created_by", "created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "parent", "latitude", "longitude"]
    list_filter = ["kind"]
    search_fields = ["name", "parent__name"]
    autocomplete_fields = ["parent"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "slug"]
    list_filter = ["category"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Union)
class UnionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "union_type", "start_date", "end_date", "end_reason"]
    list_filter = ["union_type", "end_reason"]
    search_fields = [
        "partner_a__first_name",
        "partner_a__last_name",
        "partner_b__first_name",
        "partner_b__last_name",
    ]
    autocomplete_fields = ["partner_a", "partner_b"]


@admin.register(ParentChild)
class ParentChildAdmin(admin.ModelAdmin):
    list_display = ["parent", "child", "relationship_type", "union"]
    list_filter = ["relationship_type"]
    search_fields = ["parent__first_name", "parent__last_name", "child__first_name", "child__last_name"]
    autocomplete_fields = ["parent", "child", "union"]


@admin.register(Residence)
class ResidenceAdmin(admin.ModelAdmin):
    list_display = ["person", "place", "years", "is_current"]
    list_filter = ["is_current"]
    search_fields = ["person__first_name", "person__last_name", "place__name"]
    autocomplete_fields = ["person", "place"]


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ["person", "institution", "level", "years"]
    list_filter = ["level"]
    search_fields = ["person__first_name", "person__last_name", "institution", "field_of_study"]
    autocomplete_fields = ["person", "place"]


@admin.register(Employment)
class EmploymentAdmin(admin.ModelAdmin):
    list_display = ["person", "employer", "role", "years", "is_current"]
    list_filter = ["is_current"]
    search_fields = ["person__first_name", "person__last_name", "employer", "role"]
    autocomplete_fields = ["person", "place"]


@admin.register(LifeEvent)
class LifeEventAdmin(admin.ModelAdmin):
    list_display = ["person", "heading", "date", "place"]
    list_filter = ["event_type"]
    search_fields = ["title", "person__first_name", "person__last_name", "place__name"]
    autocomplete_fields = ["person", "place"]


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ["user", "person", "created_at"]
    autocomplete_fields = ["person"]


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "created_at", "handled"]
    list_filter = ["handled"]
    list_editable = ["handled"]
    search_fields = ["name", "email", "message"]
    readonly_fields = ["name", "email", "message", "created_at"]
