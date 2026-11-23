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
missing_units=missing_units.rename(columns={"unit_id": "missing_unit_id"})

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
 # Removes duplicate missing_unit_id rows
missing_units = missing_units.drop_duplicates(
    subset="missing_unit_id",
    keep="first"
).copy()
assert len(missing_units) == 254
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
print(cand[["missing_unit_id", "name", "wahlkreis", "lat", "lon", "gn_pop"]].head(10))


# 4.5 ------------------------------- 4.5 IS AI GENERATED
# ONLY auto-assign when candidates point to exactly one host
#1. Give every candidate its own ID
cand= cand.reset_index(drop=True)
cand["cand_id"]= range(len(cand))

#2. The 749 nodes, with their Wahlkreis
# One Wahlkreis per unit (Kreise in the same unit are in the same Wahlkreis)
unit_wk= lookup.dropna(subset=["unit_id"]).drop_duplicates("unit_id")[["unit_id", "wahlkreis"]]

nodes= merged_geo_dissolved[["unit_id", "geometry"]].merge(unit_wk)
#Rename so they don't clash with the candidate's own wahlkreis after the join
nodes= nodes.rename(columns={"unit_id": "node_id", "wahlkreis": "host_wahlkreis" })


# 3. Which shape does each candidate point fall in?

points = gpd.GeoDataFrame(
    cand,
    geometry=gpd.points_from_xy(cand["lon"], cand["lat"]),
    crs="EPSG:4326"
)

# Ensure points and polygons share the same CRS
nodes = nodes.to_crs(points.crs)

# Main case: candidate lies inside a polygon
inside = gpd.sjoin(
    points,
    nodes,
    how="inner",
    predicate="within"
)

inside["how"] = "within"
inside["distance_m"] = 0.0

# Fallback: candidates not inside any polygon
outside = points[
    ~points["cand_id"].isin(inside["cand_id"])
].copy()

# Project into metres for distance calculations
outside_m = outside.to_crs(epsg=3035)
nodes_m = nodes.to_crs(epsg=3035)

# Find nearest polygon within 5 km
near = gpd.sjoin_nearest(
    outside_m,
    nodes_m,
    how="inner",
    max_distance=5000,
    distance_col="distance_m"
)

near = near.to_crs(points.crs)
near["how"] = "nearest"

# Combine both sets of spatial matches
matches = pd.concat(
    [inside, near],
    ignore_index=True
)

print("Candidates matched to a polygon:",
      matches["cand_id"].nunique())

print("Candidates with no polygon within 5 km:",
      len(points) - matches["cand_id"].nunique())


# Now we check whether the missing unit's Wahlkreis agrees with the potential host polygon's Wahlkreis


# --------------------------------------------------
# 4. Wahlkreis referee
# --------------------------------------------------

# Compare candidate Wahlkreis with host Wahlkreis
matches["wk_match"] = (
    matches["wahlkreis"] == matches["host_wahlkreis"]
)

# Keep candidates whose host belongs to the correct Wahlkreis
valid = matches[matches["wk_match"]].copy()

# Remove duplicate candidate-host combinations
valid = valid.drop_duplicates(
    subset=["missing_unit_id", "node_id"]
)

# Count distinct valid host polygons for each missing unit
host_counts = (
    valid.groupby("missing_unit_id")["node_id"]
    .nunique()
    .rename("n_hosts")
)

valid = valid.merge(
    host_counts,
    on="missing_unit_id",
    how="left"
)

# Automatically assign only units with exactly one valid host
assigned = valid[
    valid["n_hosts"] == 1
].copy()

assigned = assigned[
    ["missing_unit_id", "node_id"]
].drop_duplicates()

# Everything else goes to manual review
review = missing_units[
    ~missing_units["missing_unit_id"].isin(assigned["missing_unit_id"])
].copy()

print("Automatically assigned units:", len(assigned))
print("Units requiring manual review:", len(review))

# Sanity checks
assert assigned["missing_unit_id"].is_unique
assert not assigned["node_id"].isna().any()

assert (
    len(assigned) + len(review)
    == len(missing_units)
)

# Save results
assigned.to_csv(
    DIR + "missing_hosts_auto.csv",
    index=False
)

review.to_csv(
    DIR + "missing_hosts_review.csv",
    index=False
)


manual = pd.read_csv(DIR + "manual_hosts.csv")
auto = pd.read_csv(DIR + "missing_hosts_auto.csv")

auto = auto[~auto["missing_unit_id"].isin(manual["missing_unit_id"])]    # manual wins
hosts = pd.concat([auto, manual[["missing_unit_id", "node_id"]]])
hosts = hosts[hosts["missing_unit_id"].isin(missing_units["missing_unit_id"])]   # only current missing units

assert hosts["missing_unit_id"].is_unique
assert set(hosts["missing_unit_id"]) == set(missing_units["missing_unit_id"])   # all 254 covered
assert set(hosts["node_id"]) <= set(merged_geo_dissolved["unit_id"])             # every host is a real node


# ------------------- 4.6 ----------------------------

# Give every unit a node_id
# Missing units use their assigned host's node_id
# All other units keep their own unit_id as their node_id

#1. Create a mapping from units to nodes
unit_to_node=dict(zip(hosts["missing_unit_id"], hosts["node_id"]))

kreis_map=lookup[["kreis_id", "unit_id"]].dropna().copy()

#Start by giving every unit its own node_id
kreis_map["node_id"]= kreis_map["unit_id"]

#Replace the node_id fo th units that have been assigned a host
kreis_map["node_id"]= kreis_map["unit_id"].map(unit_to_node).fillna(kreis_map["node_id"])

assert kreis_map["unit_id"].nunique()==1003
assert kreis_map["node_id"].nunique()==749

#2. Match each Kreis to its node
k= kreis_raw.merge(kreis_map, on="kreis_id")

#3. Combine the election results for Kreise belonging to the same node
vote_cols=[]

for year in ["1928", "1930", "1932j"]:
    vote_cols.append("eligible_"+year)
    vote_cols.append("valid_"+year)
    vote_cols.append("nsdap_"+year)

#Add together the votes and population for each node
node_data= k.groupby("node_id")[vote_cols + ["pop_1928"]].sum(min_count=1)
node_data=node_data.reset_index()

#Calculatethe NSDAP vote share for each election
for year in ["1928", "1930", "1932j"]:
    node_data["nsdap_share_" + year] = node_data["nsdap_" + year] / node_data["valid_" + year]


#Check that combining Kreise hasn't changed the overall vote shares
for year in  ["1928", "1930", "1932j"]:
    total_votes_before=k["nsdap_"+ year].sum()
    valid_votes_before=k["valid_"+year].sum()

    total_votes_after= node_data["nsdap_"+ year].sum()
    valid_votes_after=node_data["valid_"+year].sum()

    before= total_votes_before/ valid_votes_before
    after=total_votes_after/ valid_votes_after

    print(year, round(before*100, 1), round(after*100, 1))

    assert abs(before-after)<1e-9
    assert node_data["nsdap_share_" + year].notna().all()


#4. Calculate census shares for each node
# Only include Kreise where both values are available

def census_share(k, num, den):
    valid_rows=k [k[num].notna() & k[den].notna()]

    totals=valid_rows.groupby("node_id")[[num, den]].sum()

    shares= totals[num]/totals[den]
    return shares

#Calculate Wahlkreis shares as a fallback formissing node data
def wahlkreis_share(k, num, den):
    valid_rows = k[k[num].notna() & k[den].notna()]

    totals = valid_rows.groupby("wahlkreis")[[num, den]].sum()

    shares = totals[num] / totals[den]

    return shares



#Assign each node to the Wahlkreis of its largest Kreis

largest_kreis= k.sort_values("pop_1928", ascending=False)
largest_kreis=largest_kreis.drop_duplicates("node_id")

node_wk= largest_kreis.set_index("node_id")["wahlkreis"]
node_data["wahlkreis"]=node_data["node_id"].map(node_wk)

#Census variables and their numerator/denominator columns

census= {
    "catholic_share": ("c25_catholic", "c25_pop"),
    "agri_share": ("c25_agri", "c25_occ_total"),
    "unemp_1933": ("c33_unemployed", "c33_active")

}

for share, (num, den) in census.items():
    #First try to calculate the share using the node's own Kreise

    node_shares=census_share(k, num, den)
    node_data[share]= node_data["node_id"].map(node_shares)

    #Record which nodes have missing census data
    node_data[share + "_approx"]= node_data[share].isna()

    #For missing nodes, use the share from their Wahlkreis instead
    wk_shares= wahlkreis_share(k, num, den)
    fallback=node_data["wahlkreis"].map(wk_shares)

    node_data[share]= node_data[share].fillna(fallback)

    missing_count=node_data[share + "_approx"].sum()
    print(share, missing_count, "nodes use the Wahlkreis value")

    assert node_data[share].notna().all()

assert len(node_data)==749


# 5. Attach the node data to the geographic boundaries

nodes_geo = merged_geo_dissolved[["unit_id", "geometry"]].copy()

nodes_geo = nodes_geo.rename(columns={"unit_id": "node_id"})

nodes_geo = nodes_geo.merge(node_data, on="node_id")

assert len(nodes_geo) == 749

#AI generated below this
# 6. Save the results
kreis_map.to_csv(DIR + "kreis_to_node.csv", index=False)
node_data.to_csv(DIR + "nodes.csv", index=False)
nodes_geo.to_file(DIR + "nodes.gpkg", driver="GPKG")

    
nodes_geo = gpd.read_file(DIR + "nodes.gpkg")
nodes_geo.plot(column="nsdap_share_1932j", cmap="Reds", legend=True,
               edgecolor="black", linewidth=0.1, figsize=(10, 12))
plt.show()