import pandas as pd
from pathlib import Path
here = Path(__file__).parent
elections = pd.read_stata(here / "ZA8013_Wahldaten (1).dta")
social = pd.read_stata(here / "ZA8013_Sozialdaten (1).dta")

print(elections.head())
print(social.head())

print(elections.columns.tolist())
print(social.columns.tolist())

elections.to_csv("elections.csv", index=False)
social.to_csv("social.csv", index=False)