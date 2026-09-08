from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analysis", "0008_marketsignal_news_count_marketsignal_news_sentiment"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketsignal",
            name="completed_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="marketsignal",
            name="exit_price",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
