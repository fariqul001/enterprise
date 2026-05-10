# Generated migration for Payment model updates

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_alter_transaction_investment'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='bank_slip',
            field=models.ImageField(blank=True, null=True, upload_to='payment_slips/'),
        ),
        migrations.AddField(
            model_name='payment',
            name='admin_note',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='payment',
            name='status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('completed', 'Completed')],
                default='pending',
                max_length=50
            ),
        ),
    ]
