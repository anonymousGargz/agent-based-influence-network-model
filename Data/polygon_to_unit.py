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

# Check that the area is the same before and after merging the geometries
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
