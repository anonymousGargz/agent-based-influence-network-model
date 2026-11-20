
import matplotlib.pyplot as plt
import geopandas as gpd
import folium
import pandas as pd

# --------------------------------------------------
# 1. Load shapefile
# --------------------------------------------------

SHP_FILE = r"C:\Users\gnisa\Documents\Third Year Project\Data\nazi_wgs84.shp"

gdf = gpd.read_file(SHP_FILE)
#Repairs invalid geometries
gdf["geometry"] = gdf.geometry.make_valid()

print("First five rows:")
print(gdf.head())

print("\nCoordinate Reference System:")
print(gdf.crs)

print("\nGeometry types:")
print(gdf.geom_type.value_counts())


saar_kreise = [
    "Saarbrücken-Stadt",
    "Saarbrücken-Land",
    "Saarlouis",
    "Ottweiler",
    "Merzig",
    "St. Wendel",
    "St. Ingbert",
    "Homburg"
]

print("\nNumber of geographic features:", len(gdf))

# ---------------------------------------
# determine Kreise in the Saar by listing all Kreise in a CSV file and then checking which ones to filter
# Basically discovered that if it's occupied by France it all comes under the label "OccupiedByFrance"- these 8 
# individual Kreise have been labelled under one "OccupiedByFrance" label, so that's why the features labelled has
# just been reduced by one
# ---------------------------------------------------------------------
kreise = gdf["KREISE"].dropna().unique()
pd.Series(sorted(kreise), name="KREISE").to_csv("kreise.csv", index=False, encoding="utf-8-sig")
print("Before removal:", len(gdf))

# Identify Saar Territory
saar = gdf[gdf["KREISE"] == "OccupiedByFrance"]

print("Features labelled OccupiedByFrance:", len(saar))

# Remove Saar Territory
gdf = gdf[gdf["KREISE"] != "OccupiedByFrance"].copy()

gdf["poly_id"]=range(len(gdf))

print("After removal:", len(gdf))

# Verify
print("Remaining OccupiedByFrance:",
      (gdf["KREISE"] == "OccupiedByFrance").sum())

gdf.to_file("boundaries_clean.gpkg")
#----------------------------------
# 2. Plot shapefile using Matplotlib
# --------------------------------------------------

fig, ax = plt.subplots(figsize=(12, 10))

gdf.plot(
    ax=ax,
    edgecolor="gray",
    alpha=0.5
)

ax.set_title("Geographic Data - Weimar Germany")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")

plt.show()

# --------------------------------------------------
# 3. Convert coordinates to WGS84 for Folium
# --------------------------------------------------

if gdf.crs is None:
    raise ValueError(
        "The shapefile has no defined CRS. "
        "Please verify its coordinate system."
    )

gdf = gdf.to_crs(epsg=4326)

# Remove missing and empty geometries
gdf = gdf[
    gdf.geometry.notna() & ~gdf.geometry.is_empty
].copy()

# --------------------------------------------------
# 4. Calculate map centre
# --------------------------------------------------

# Use the centre of the bounding box
bounds = gdf.total_bounds

minx, miny, maxx, maxy = bounds

center_lat = (miny + maxy) / 2
center_lon = (minx + maxx) / 2

# --------------------------------------------------
# 5. Create interactive Folium map
# --------------------------------------------------

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=5,
    tiles=None
)

# OpenStreetMap
folium.TileLayer(
    "OpenStreetMap",
    name="OpenStreetMap"
).add_to(m)

# CartoDB Positron
folium.TileLayer(
    "CartoDB positron",
    name="Light Map"
).add_to(m)

# Esri Satellite
folium.TileLayer(
    tiles=(
        "https://server.arcgisonline.com/ArcGIS/rest/"
        "services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    ),
    attr="Esri World Imagery",
    name="Satellite",
    overlay=False,
    control=True
).add_to(m)

# --------------------------------------------------
# 6. Add geographic features
# --------------------------------------------------

# Get attribute columns for tooltips
tooltip_fields = [
    col for col in gdf.columns
    if col != "geometry"
]

tooltip_fields = tooltip_fields[:5]

geojson_options = {
    "data": gdf,
    "name": "Geographic Features",
    "style_function": lambda feature: {
        "color": "yellow",
        "weight": 2,
        "fillColor": "blue",
        "fillOpacity": 0.15
    }
}

# Add tooltips only if attribute columns exist
if tooltip_fields:
    geojson_options["tooltip"] = folium.GeoJsonTooltip(
        fields=tooltip_fields,
        aliases=tooltip_fields,
        sticky=True
    )

folium.GeoJson(**geojson_options).add_to(m)

# --------------------------------------------------
# 7. Fit map to geographic boundaries
# --------------------------------------------------

m.fit_bounds([
    [miny, minx],
    [maxy, maxx]
])

# --------------------------------------------------
# 8. Add layer control
# --------------------------------------------------

folium.LayerControl(
    collapsed=False
).add_to(m)

# --------------------------------------------------
# 9. Save interactive map
# --------------------------------------------------

OUTPUT_FILE = "weimar_geographic_map.html"

m.save(OUTPUT_FILE)

print(f"\nInteractive map saved to: {OUTPUT_FILE}")

