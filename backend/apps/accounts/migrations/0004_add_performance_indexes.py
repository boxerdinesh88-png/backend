# Generated manually for performance optimization
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_remove_user_aadhar_number_user_aadhar_document'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['email'], name='user_email_idx'),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['is_email_verified'], name='user_email_verified_idx'),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['role', 'is_active'], name='user_role_active_idx'),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['date_joined'], name='user_date_joined_idx'),
        ),
        migrations.AddIndex(
            model_name='otpcode',
            index=models.Index(fields=['user', 'purpose', 'is_used'], name='otp_user_purpose_used_idx'),
        ),
        migrations.AddIndex(
            model_name='otpcode',
            index=models.Index(fields=['expires_at'], name='otp_expires_at_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['user', 'created_at'], name='audit_user_created_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['actor_email', 'created_at'], name='audit_email_created_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['created_at'], name='audit_created_idx'),
        ),
    ]
