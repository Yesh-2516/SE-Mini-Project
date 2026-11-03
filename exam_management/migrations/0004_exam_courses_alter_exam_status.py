# Generated for OEP-F-024 (assign exams to courses and publish)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0001_initial'),
        ('exam_management', '0003_exam_availability_end_exam_availability_start'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='courses',
            field=models.ManyToManyField(blank=True, related_name='exams', to='courses.course'),
        ),
        migrations.AlterField(
            model_name='exam',
            name='status',
            field=models.CharField(choices=[('DRAFT', 'Draft'), ('PUBLISHED', 'Published')], default='DRAFT', max_length=20),
        ),
    ]
