import pandas as pd
from pathlib import Path
import pyreadstat
here = Path(__file__).parent
elections = pd.read_stata(here / "ZA8013_Wahldaten (1).dta")
social = pd.read_stata(here / "ZA8013_Sozialdaten (1).dta")

print(elections.head())
print(social.head())

#print(elections.columns.tolist())
#print(social.columns.tolist())

df, meta = pyreadstat.read_dta(here / "ZA8013_Wahldaten (1).dta")
print(meta.column_names_to_labels)   # variable descriptions
print(meta.number_rows, meta.file_label)

