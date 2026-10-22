from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0024_staffcard"), ("staff", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AlterField(model_name="staffcard", name="user",
                              field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                         related_name="card", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="staffcard", name="employee",
                            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                                       related_name="staff_card", to="staff.employee")),
    ]
