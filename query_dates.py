
from app import app
from database import db
import pandas as pd
with app.app_context():
    df = pd.read_sql("SELECT DISTINCT data_extracao FROM \"GAC-02\"", con=db.engine)
    print(df)

