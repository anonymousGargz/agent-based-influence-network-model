import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt


# 1. Merge the files on the kreis column 
DIR= "C://Users//gnisa//Documents//Third Year Project//Data//"
poly_kreis=pd.read_csv(DIR +'poly_to_kreis.csv')
lookup=pd.read_csv(DIR+'lookup.csv')

merged=pd.merge(poly_kreis, lookup, on='kreis_id', how='left')
assert merged["unit_id"].isna().sum()==0

#The data is currently just a pandas dataframe, it needs to include the geometry information

boundaries_clean=gpd.read_file(DIR +"boundaries_clean.gpkg")

#merge only on the required values
merged_geo= boundaries_clean.merge(merged[["poly_id", "kreis_id", "unit_id"]], on="poly_id")
print(merged_geo)
assert merged_geo["unit_id"].isna().sum()==0


# Dissolve duplicate units-> merges all polygons with the same unit_id into one shape
merged_geo_dissolved= merged_geo.dissolve(by="unit_id")
merged_geo_dissolved=merged_geo_dissolved.reset_index()

# Check that the area is the same before and after merging the geometries; this shows that the merging was done correctly
before = merged_geo.to_crs(3035).area.sum()
after = merged_geo_dissolved.to_crs(3035).area.sum()
print(before / 1e6, after / 1e6)   # km²

assert abs(before - after) / before < 0.001, "area changed during dissolve"

# Highlight only the merged shapes
counts = merged_geo.groupby("unit_id").size().rename("n_polys")
merged_geo_dissolved = merged_geo_dissolved.merge(counts, on="unit_id")
plt.show()

ax = merged_geo_dissolved.plot(color="lightgrey", edgecolor="black", linewidth=0.2, figsize=(10, 12))
merged_geo_dissolved[merged_geo_dissolved["n_polys"] > 1].plot(ax=ax, color="red", edgecolor="black", linewidth=0.4)
plt.show()


#4. List the missing units
diff = lookup.merge(merged_geo_dissolved[["unit_id"]], on="unit_id", how="left", indicator=True)
diff = diff[diff["_merge"] == "left_only"].drop(columns="_merge")
diff = diff[diff["unit_id"].notna()]   # drop Kreise with no 1928–32 results

# Now I need to get one row per missing unit, and I'm doing this by selecting the Kreis with the largest population in that unit
kreis_raw = pd.read_csv(DIR + "kreis_raw.csv")

diff= diff.merge(kreis_raw[["kreis_id", "pop_1928"]], on="kreis_id", how="left")

missing_units=diff.sort_values("pop_1928", ascending=False)
missing_units=missing_units[["unit_id", "kreis_id", "name", "level", "wahlkreis", "pop_1928"]]

#4.b Now I need to find a search name/ coordinates for each missing unit
# I'm re-using the clean and remove bracket functions from the match_boundaries.py

def remove_brackets(s):
    result = ""
    while "(" in s:
        start = s.find("(")
        end = s.find(")", start)
        if end == -1:
            end = len(s)
        result = result + s[:start]
        s = s[end + 1:]
    return result + s

def clean(name):
    s = str(name).lower()
    s = s.replace("ß", "ss").replace("ä", "a").replace("ö", "o").replace("ü", "u")
    s = s.replace("ae", "a").replace("oe", "o").replace("ue", "u")
    letters = ""
    for ch in s:
        if "a" <= ch <= "z":
            letters = letters + ch
    return letters

def place_name(za_name):
    s=str(za_name).split("/")[0]
    s=remove_brackets(s)
    keep=[]
    digi=False
    for ch in s:
        if ch.isdigit():
            digi=True
    for w in s.split():
        #Skip S/L markers, Berlin "BA" and anything with a digit (BA numbers, dates)
        
        if w in ["S", "L", "BA", "-"] or any(ch.isdigit() for ch in w):
            continue
        keep.append(w)
    return clean(" ".join(keep))


missing_units["key"] = missing_units["name"].map(place_name)

# Build the GeoNames dictionary 
# This turns GeoNames' big table into a dictionary you can lookup a name in and find the coordinates
cols = ["geonameid", "name", "asciiname", "alternatenames", "lat", "lon",
        "feature_class", "feature_code", "country", "cc2", "admin1", "admin2",
        "admin3", "admin4", "population", "elevation", "dem", "timezone", "modified"]

# GeoNames files have no header row, so we name the 19 columns ourselves (order from the GeoNames readme)

frames=[]
for country in ["DE", "PL", "RU"]:
    gn = pd.read_csv(DIR + country + ".txt",
                     sep="\t", header=None, names=cols, usecols=["name", "asciiname", "alternatenames",
                                                                 "lat", "lon", "feature_class", "population"],
                        dtype=str, quoting=3, keep_default_na=False)
    # tab-separated, no header
    # only what we need
    # read everything as text
    # ignore stray quote marks in names
    #empty cells stay "" instead of NaN


    frames.append(gn)

gn=pd.concat(frames)

gn=gn[gn["feature_class"]== "P"] # P= populated places
print (len(gn), "populated places")

places= {}
for row in gn.itertuples(): # one place at a time
    # every name this place goes by
    names = [row.name, row.asciiname] + row.alternatenames.split(",")
    keys=set(clean(n) for n in names if n!="") #set: same key from two names only counts on
    if row.population != "":
        pop= int(row.population)
    else:
        pop=0
    for key in keys:
        if key== "":
            continue
        if key not in places:
            places[key]=[] # first time we see this name: start a list
        places[key].append((float(row.lat), float(row.lon), pop)) # many places can share a name, so keep them all
print(len(places), "distinct names")
print(places.get("stolp"))


#3. Attach candidate coordinates to each missig unit

#look up eah key: .get(k, []) gives an empty list if the name isn't in GeoNames at all
missing_units["candidates"] = missing_units["key"].map(lambda k: places.get(k, []))
missing_units["n_cand"]= missing_units["candidates"].map(len)

print((missing_units["n_cand"]==0).sum(), "with no candidate") #these go to manual review
print((missing_units["n_cand"]>1).sum(), "with several candidatrs") #Wahlkreis check picks one in 4.5


#explode: a unit with 3 candidates become 3 rows, one per candidate
cand = missing_units.explode("candidates")
cand = cand[cand["candidates"].notna()]

#split each (lat, lon, pop) tuple into its own column
cand["lat"]= cand["candidates"].map(lambda c: c[0])
cand["lon"] = cand["candidates"].map(lambda c: c[1])
cand["gn_pop"]= cand["candidates"].map(lambda c: c[2])

print(len(cand), "candidate rows")
print(cand[["unit_id", "name", "wahlkreis", "lat", "lon", "gn_pop"]].head(10))

#Hmm something is going wrong
# I dom't really know what to fix
