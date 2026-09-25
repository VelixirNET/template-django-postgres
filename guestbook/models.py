from django.db import models


class Entry(models.Model):
    """One signature in the guestbook."""

    name = models.CharField(max_length=80)
    message = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "entries"

    def __str__(self):
        return f"{self.name}: {self.message[:50]}"
