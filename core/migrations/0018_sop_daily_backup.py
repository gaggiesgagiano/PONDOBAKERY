"""Adds the SOP "Daily backup" and brings untouched SOP drafts up to date with core/sop_seed.py (same as 0016).

Only drafts nobody has changed in Pondo yet (version 1, no editor) get the new text; in every SOP the old title is replaced."""
from django.db import migrations


def refresh(apps, schema_editor):
    Sop = apps.get_model("core", "Sop")
    from core.sop_seed import S
    seq, seed = {}, {}
    for d in S:
        seq[d["section"]] = seq.get(d["section"], 0) + 1
        seed[(d["section"], seq[d["section"]])] = d
    for s in Sop.objects.all():
        d = seed.get((s.section, s.seq))
        if d and s.version == 1 and s.status == "draft" and s.updated_by_id is None:
            s.title, s.purpose, s.responsible, s.applies, s.body = d["title"], d["purpose"], d["responsible"], d["applies"], d["body"]
        for f in ("title", "purpose", "responsible", "body", "written_by"):
            setattr(s, f, getattr(s, f).replace("Operations Manager", "Manager"))
        s.save()
    have = set(Sop.objects.values_list("section", "seq"))
    for (sec, n), d in seed.items():          # SOPs added to the draft after it was first loaded
        if (sec, n) not in have:
            Sop.objects.create(section=sec, seq=n, title=d["title"], purpose=d["purpose"], responsible=d["responsible"],
                               applies=d["applies"], body=d["body"], status="draft", version=1, written_by="Manager")


class Migration(migrations.Migration):
    dependencies = [("core", "0017_backup_waive")]
    operations = [migrations.RunPython(refresh, migrations.RunPython.noop)]
