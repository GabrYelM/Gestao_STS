
import sqlalchemy
from app import app
from database import db

with app.app_context():
    db.session.execute(sqlalchemy.text("DROP TABLE IF EXISTS \"CG-01\""))
    db.session.execute(sqlalchemy.text("DROP TABLE IF EXISTS \"CG-05\""))
    db.session.execute(sqlalchemy.text("DROP TABLE IF EXISTS \"CG-06\""))
    db.session.execute(sqlalchemy.text("DROP TABLE IF EXISTS \"GAC-02\""))
    db.session.commit()
    db.create_all()
    print("Tabelas recriadas!")

