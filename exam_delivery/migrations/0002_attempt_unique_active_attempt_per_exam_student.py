# Hand-written to match what `makemigrations` produces for the Attempt
# constraint added in exam_delivery.models (OEP-F-034).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exam_delivery', '0001_initial'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='attempt',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'IN_PROGRESS')), fields=('exam', 'student'), name='unique_active_attempt_per_exam_student'),
        ),
    ]
