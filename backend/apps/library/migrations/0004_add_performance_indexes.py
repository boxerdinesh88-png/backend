# Generated manually for performance optimization
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('library', '0003_section_seat_grid_col_seat_grid_row_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='section',
            index=models.Index(fields=['sort_order'], name='section_sort_order_idx'),
        ),
        migrations.AddIndex(
            model_name='shift',
            index=models.Index(fields=['is_active'], name='shift_is_active_idx'),
        ),
        migrations.AddIndex(
            model_name='shift',
            index=models.Index(fields=['start_time', 'end_time'], name='shift_time_idx'),
        ),
        migrations.AddIndex(
            model_name='seat',
            index=models.Index(fields=['section', 'is_active'], name='seat_section_active_idx'),
        ),
        migrations.AddIndex(
            model_name='seat',
            index=models.Index(fields=['is_active'], name='seat_is_active_idx'),
        ),
        migrations.AddIndex(
            model_name='seat',
            index=models.Index(fields=['zone'], name='seat_zone_idx'),
        ),
    ]
