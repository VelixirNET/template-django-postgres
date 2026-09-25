from django.contrib import admin

from .models import Entry

admin.site.site_header = "Guestbook admin"
admin.site.site_title = "Guestbook admin"
admin.site.index_title = "Moderation"


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ["name", "short_message", "created_at"]
    search_fields = ["name", "message"]

    @admin.display(description="Message")
    def short_message(self, entry):
        return entry.message if len(entry.message) <= 80 else entry.message[:79] + "…"
