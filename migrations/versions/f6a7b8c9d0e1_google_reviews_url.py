"""google reviews page link per client

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-23 12:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None

# where "via Google" should take people: the page listing their Google reviews
LINKS = {
    "rolands-handyman": 'https://www.google.com/search?client=ms-android-samsung-ss&hs=lZg9&sca_esv=7dc7437ea5d14899&sxsrf=AE3TifPAqD-KGXIlkKVwOwrEl1yObK617w:1766335794672&si=AMgyJEtREmoPL4P1I5IDCfuA8gybfVI2d5Uj7QMwYCZHKDZ-E1Rp3wUeVnrw7EH22mZBBxDpQe7Nr5fLoyVL5ZXESipRugQcPmdhiyxsp4UR9STLFTHGrZ3aAFrI7GK_XnBEZaZg6HfVqOV7B0502kQ9KxvMJxd0lGgg1ARKI2p0y8ns-D7Ry8A%3D&q=Rolands-handyman+/+Flatpack+Assembly+Reviews&sa=X&ved=2ahUKEwj6ueHMkc-RAxXXT0EAHRKMGv0Q0bkNegQIIRAD&biw=1387&bih=1323&dpr=1&sei=PSVIacXhJI_OhbIPysHz-A8',
    "ray-g-handyman": 'https://www.google.com/search?q=RayG+Handyman+Services+Wolverhampton+Reviews',
}


def upgrade():
    with op.batch_alter_table('accounts') as b:
        b.add_column(sa.Column('google_reviews_url', sa.String(length=500), nullable=True))
    accounts = sa.table('accounts', sa.column('slug', sa.String), sa.column('google_reviews_url', sa.String))
    for slug, url in LINKS.items():
        op.execute(accounts.update().where(accounts.c.slug == slug).values(google_reviews_url=url))


def downgrade():
    with op.batch_alter_table('accounts') as b:
        b.drop_column('google_reviews_url')
