# extract.py
# Pulls the variables I need out of the two ZA8013 files (elections + social data)
# and saves them as CSVs with English column names.
#
# Run: python extract.py ZA8013_Wahldaten.dta ZA8013_Sozialdaten.dta out

import sys
import os
import numpy as np
import pandas as pd

# ID columns (same in both files)
ID_COLS = {
    "lfnr": "row_id",       # unique row number, links the two files
    "krnr": "kreis_id",     # Kreis number (municipalities have their parent Kreis's number)
    "agglvl": "level",      # 4 = Stadtkreis, 5/6 = Landkreis, 8 = municipality, 9 = Restkreis
    "name": "name",
    "wkr": "wahlkreis",
    "regbez": "regbez",
}

# Boundary keys from Haenisch (1989). Each value is the row number of the
# row this one gets combined with (0 = not used).
KEY_COLS = {
    "agg2830": "key_1928_1930",   # municipal level
    "agg3032": "key_1930_1932",   # Kreis level
    "agg3232": "key_1932_1932",   # July -> Nov 1932
    "agg3233": "key_1932_1933",   # Nov 1932 -> March 1933
}

# Election variable names are prefix + suffix, e.g. n285nsda = NSDAP votes May 1928
ELECTIONS = {"n285": "1928", "n309": "1930", "n327": "1932j", "n32n": "1932n"}
FIELDS = {"pop": "pop", "wb": "eligible", "as": "cast", "gs": "valid", "nsda": "nsdap"}

SOCIAL_COLS = {
    "c25pop": "c25_pop",            # 1925 census population
    "c25kath": "c25_catholic",
    "c25prot": "c25_protestant",
    "c25juden": "c25_jewish",
    "c25wohn": "c25_occ_total",     # everyone counted in the occupational census
    "c25bland": "c25_agri",         # people in agriculture/forestry
    "c33erwp": "c33_active",        # 1933: economically active
    "c33erlos": "c33_unemployed",   # 1933: unemployed
    "alos30d": "unemp_dec1930",     # supported unemployed, towns 20k+ only
    "alos31d": "unemp_dec1931",
    "alos32d": "unemp_dec1932",
}


def main():
    if len(sys.argv) != 4:
        print("usage: python extract.py WAHLDATEN.dta SOZIALDATEN.dta OUT_DIR")
        sys.exit(1)
    wahl_file, sozial_file, out_dir = sys.argv[1:]
    os.makedirs(out_dir, exist_ok=True)

    # -9 is the missing value code in ZA8013
    wahl = pd.read_stata(wahl_file, convert_categoricals=False).replace(-9, np.nan)
    sozial = pd.read_stata(sozial_file, convert_categoricals=False).replace(-9, np.nan)

    # the two files should line up row for row
    assert (wahl["lfnr"].values == sozial["lfnr"].values).all()

    election_cols = {}
    for prefix, year in ELECTIONS.items():
        for suffix, field in FIELDS.items():
            election_cols[prefix + suffix] = f"{field}_{year}"

    df = wahl[list(ID_COLS) + list(KEY_COLS) + list(election_cols)].copy()
    for col in SOCIAL_COLS:
        df[col] = sozial[col]

    df = df.rename(columns={**ID_COLS, **KEY_COLS, **election_cols, **SOCIAL_COLS})
    df["name"] = df["name"].str.strip()
    for col in KEY_COLS.values():
        df[col] = df[col].fillna(0).astype(int)

    # Kreis level = 4, 5, 6. Municipal level = 4, 6, 8, 9 (only needed for the 1928-30 key)
    kreise = df[df["level"].isin([4, 5, 6])]
    municipalities = df[df["level"].isin([4, 6, 8, 9])]

    kreise.to_csv(os.path.join(out_dir, "kreis_raw.csv"), index=False)
    municipalities.to_csv(os.path.join(out_dir, "municipal_raw.csv"), index=False)

    print(len(kreise), "Kreis rows,", len(municipalities), "municipal rows")
    for year in ELECTIONS.values():
        print(f"  Kreise with results in {year}: {kreise['nsdap_' + year].notna().sum()}")


if __name__ == "__main__":
    main()