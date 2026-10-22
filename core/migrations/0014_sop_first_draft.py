"""Loads the first draft of the SOP file (core/sop_seed.py) – once. After that the SOPs are changed in Pondo."""
from django.db import migrations


def load(apps, schema_editor):
    Sop = apps.get_model("core", "Sop")
    if Sop.objects.exists():
        return
    from core.sop_seed import S
    seq = {}
    for d in S:
        seq[d["section"]] = seq.get(d["section"], 0) + 1
        Sop.objects.create(section=d["section"], seq=seq[d["section"]], title=d["title"], purpose=d["purpose"],
                           responsible=d["responsible"], applies=d["applies"], body=d["body"], status="draft", version=1,
                           written_by="Manager")


class Migration(migrations.Migration):
    dependencies = [("core", "0013_sop_file")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
