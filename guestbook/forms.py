from django import forms

from .models import Entry


class EntryForm(forms.ModelForm):
    """The rules come from the model: both fields required, and its length limits."""

    class Meta:
        model = Entry
        fields = ["name", "message"]
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Your name", "aria-label": "Your name", "autocomplete": "name"}
            ),
            "message": forms.Textarea(
                attrs={"placeholder": "Say something nice", "aria-label": "Message", "rows": 3}
            ),
        }
