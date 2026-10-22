"""Letters: type a letter, save it, print it on the letterhead (page 1; next pages plain), print again, delete."""
import datetime

from django import forms
from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import EDIT, VIEW, need
from .models import Letter, log_change
from .richtext import clean


class LetterForm(forms.ModelForm):
    class Meta:
        model = Letter
        fields = ["date", "to", "subject", "body", "sign_name", "sign_title", "add_signature"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "to": forms.Textarea(attrs={"rows": 4, "placeholder": "Mr T. Moyo\nABC Suppliers (Pvt) Ltd\n12 Main Road\nHarare"}),
                   "subject": forms.TextInput(attrs={"placeholder": "e.g. Order for December"}),
                   "body": forms.Textarea(attrs={"rows": 4, "class": "rt-store"})}

    def __init__(self, *a, can_sign=False, **kw):
        super().__init__(*a, **kw)
        self.can_sign = can_sign
        if not can_sign:
            self.fields.pop("add_signature")
        else:
            self.fields["add_signature"].help_text = "Prints the scanned signature above the name"

    def clean_body(self):
        html = clean(self.cleaned_data.get("body", ""))
        if not html.replace("<p><br></p>", "").strip():
            raise forms.ValidationError("Type the letter first.")
        return html


OWNER_NAME = "Jurie Gagiano"   # the owner login always signs as Jurie


@need("letters", VIEW)
def letter_list(request):
    q = request.GET.get("q", "").strip()
    rows = Letter.objects.select_related("created_by")
    if q:
        rows = rows.filter(Q(subject__icontains=q) | Q(to__icontains=q) | Q(body__icontains=q))
    return render(request, "core/letters/list.html", {"rows": rows[:300], "q": q, "total": Letter.objects.count()})


@need("letters", EDIT)
def letter_edit(request, pk=None):
    letter = get_object_or_404(Letter, pk=pk) if pk else None
    if request.method == "POST":
        form = LetterForm(request.POST, instance=letter, can_sign=request.user.is_superuser)
        if form.is_valid():
            obj = form.save(commit=False)
            if not obj.pk:
                obj.created_by = request.user
            if request.user.is_superuser and not obj.sign_name.strip():
                obj.sign_name = OWNER_NAME
            obj.save()
            log_change(request.user, "Letters", str(obj), "saved")
            messages.success(request, f"Letter {obj.number} saved.")
            if request.POST.get("print"):
                return redirect(f"/letters/{obj.pk}/?print=1")
            return redirect("core:letter", pk=obj.pk)
    else:
        if letter:
            form = LetterForm(instance=letter, can_sign=request.user.is_superuser,
                              initial={"body": letter.body_html()})
        else:
            u = request.user
            form = LetterForm(initial={"date": datetime.date.today(),
                                       "sign_name": OWNER_NAME if u.is_superuser else (f"{u.first_name} {u.last_name}".strip() or u.username),
                                       "sign_title": "Operations Manager" if u.is_superuser else "",
                                       "add_signature": u.is_superuser}, can_sign=u.is_superuser)
    return render(request, "core/letters/form.html", {"form": form, "letter": letter})


@need("letters", VIEW)
def letter_detail(request, pk):
    """The printable letter: page 1 on the letterhead, more pages plain."""
    letter = get_object_or_404(Letter, pk=pk)
    return render(request, "forms/letter_print.html", {"letter": letter, "form_name": f"Letter {letter.number}",
                                                       "auto_print": request.GET.get("print") == "1"})


@need("letters", EDIT)
@require_POST
def letter_delete(request, pk):
    letter = get_object_or_404(Letter, pk=pk)
    name = str(letter)
    letter.delete()
    log_change(request.user, "Letters", name, "deleted")
    messages.success(request, f"{name} deleted.")
    return redirect("core:letters")


@need("letters", VIEW)
def signature_image(request):
    """The scanned signature – kept in the private data folder, only shown to people who may see letters."""
    f = settings.DATA_DIR / "signatures" / "jurie.png"
    if not f.exists():
        raise Http404("No signature")
    resp = FileResponse(open(f, "rb"), content_type="image/png")
    resp["Cache-Control"] = "private, max-age=3600"
    return resp
