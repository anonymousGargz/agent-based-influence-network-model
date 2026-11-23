import pandas as pd
import geopandas as gpd
import networkx as nx

DIR = "C://Users//gnisa//Documents//Third Year Project//Data//"

# 1. Load nodes and project to metres
nodes = gpd.read_file(DIR + "nodes.gpkg")
nodes = nodes[["node_id", "geometry"]].to_crs(epsg=3035)
nodes["node_id"] = nodes["node_id"].astype(int)     # gpkg reads IDs back as floats; keep them as ints everywhere

assert nodes["node_id"].is_unique
assert nodes.geometry.is_valid.all()

# 2. Find candidate neighbouring nodes using spatial join
left = nodes.rename(columns={"node_id": "node_a"})
right = nodes.rename(columns={"node_id": "node_b"})

candidates = gpd.sjoin(
    left,
    right,
    how="inner",
    predicate="intersects"
)

# Remove self-pairs and duplicates (keep A-B, not B-A)
candidates = candidates[candidates["node_a"] < candidates["node_b"]]

# 3. Calculate shared border lengths
geometries = nodes.set_index("node_id").geometry

edges = []

for a, b in candidates[["node_a", "node_b"]].itertuples(index=False, name=None):

    border = geometries.loc[a].boundary.intersection(
        geometries.loc[b].boundary
    )

    border_m = border.length

    if border_m >= 100:
        edges.append((int(a), int(b), border_m))

# 4. Create edge dataframe
edges_df = pd.DataFrame(edges, columns=["node_a", "node_b", "border_m"])
edges_df = edges_df.sort_values(["node_a", "node_b"]).reset_index(drop=True)

# 5. Validation (before saving, so a broken file is never written)
assert (edges_df["node_a"] < edges_df["node_b"]).all()
assert (edges_df["border_m"] >= 100).all()
assert not edges_df.duplicated(["node_a", "node_b"]).any()
assert edges_df["node_a"].isin(nodes["node_id"]).all()
assert edges_df["node_b"].isin(nodes["node_id"]).all()

edges_df.to_csv(DIR + "geographic_edges.csv", index=False)

connected = set(edges_df["node_a"]) | set(edges_df["node_b"])
isolated = set(nodes["node_id"]) - connected

print("Number of nodes:", len(nodes))
print("Candidate pairs:", len(candidates))
print("Number of edges:", len(edges_df))
print("Isolated nodes:", isolated)
print(edges_df.head())


#MY CODE
# isolated nodes only takes into account nodes with 0 edges, but East Prussia is disconnected from the rest of mainland Germany

G = nx.Graph()
G.add_nodes_from(nodes["node_id"])
G.add_edges_from(edges_df[["node_a", "node_b"]].itertuples(index=False, name=None))

components = sorted(nx.connected_components(G), key=len, reverse=True)
print("Component sizes:", [len(c) for c in components])


# back to AI generated code


# 6. Connect detached components to mainland Germany
# Rule: up to 3 links per detached component, shortest first, with distinct nodes at both ends.
# (Rugen is a single node, so it only gets 1 link.)

mainland = components[0]
extra_edges = []

for component in components[1:]:

    # Find distances between detached and mainland nodes
    possible_links = []

    for a in component:
        for b in mainland:
            distance = geometries.loc[a].distance(geometries.loc[b])
            possible_links.append((distance, int(a), int(b)))

    # Sort by shortest distance
    possible_links.sort()

    # Choose up to 3 links with distinct nodes at both ends
    used_a = set()
    used_b = set()

    for distance, a, b in possible_links:

        if a in used_a or b in used_b:
            continue

        # keep the same ordering as the border edges (node_a < node_b)
        extra_edges.append((min(a, b), max(a, b), distance))
        used_a.add(a)
        used_b.add(b)

        if len(used_a) == 3 or len(used_a) == len(component):
            break

# 7. Add artificial links to graph
G.add_edges_from([(a, b) for a, b, distance in extra_edges])

# Check graph is now connected
assert nx.is_connected(G)
print("New component sizes:",
      [len(c) for c in nx.connected_components(G)])

# 8. Save the new edge list
extra_df = pd.DataFrame(
    extra_edges, columns=["node_a", "node_b", "distance_m"]
)

# Artificial links share no border, so border_m is missing (NaN), not 0.
# A 0 would look like a real measurement and would silently give the link zero weight
# in the border-weighted variant.
extra_df["border_m"] = float("nan")
extra_df["edge_type"] = "artificial"

edges_df["edge_type"] = "geographic"
edges_df["distance_m"] = 0.0          # neighbours touch, so their distance is 0

all_edges = pd.concat([edges_df, extra_df], ignore_index=True)
all_edges = all_edges[["node_a", "node_b", "edge_type", "border_m", "distance_m"]]

assert (all_edges["node_a"] < all_edges["node_b"]).all()
assert not all_edges.duplicated(["node_a", "node_b"]).any()

# Later stages read THIS file (use edge_type to drop the artificial links for robustness checks)
all_edges.to_csv(DIR + "geographic_edges_connected.csv", index=False)

print("Artificial links added:")
print(extra_df)
print("Total edges:", len(all_edges))



# 9. Create geographic weights for the Linear Threshold model
# source = influencing node, target = receiving node
# Incoming weights for each target must sum to 1

# Create both directions for every undirected edge
forward = all_edges[["node_a", "node_b", "edge_type", "border_m"]].copy()
forward.columns = ["source", "target", "edge_type", "border_m"]

reverse = all_edges[["node_b", "node_a", "edge_type", "border_m"]].copy()
reverse.columns = ["source", "target", "edge_type", "border_m"]

weights = pd.concat([forward, reverse], ignore_index=True)

# 9.1 Equal weights: 1 / number of neighbours of target
weights["w_equal"] = 1 / weights.groupby("target")["source"].transform("count")

# 9.2 Border weights: shared border / total border of target
# Artificial links get a proxy length of the median(about 22km) for weighting only
median_border = all_edges.loc[all_edges["edge_type"] == "geographic", "border_m"].median()
weights["effective_border"] = weights["border_m"].fillna(median_border)

weights["w_border"] = (
    weights["effective_border"] /
    weights.groupby("target")["effective_border"].transform("sum")
)

# 9.3 Keep only required columns
weights = weights[
    ["source", "target", "edge_type", "border_m", "w_equal", "w_border"]
]

weights = weights.sort_values(["source", "target"]).reset_index(drop=True)

# 9.4 Validation
assert len(weights) == 2 * len(all_edges)
assert not weights.duplicated(["source", "target"]).any()

assert weights["w_equal"].between(0, 1).all()
assert weights["w_border"].between(0, 1).all()

# Every node's incoming weights must sum to 1
equal_sums = weights.groupby("target")["w_equal"].sum()
border_sums = weights.groupby("target")["w_border"].sum()

assert ((equal_sums - 1).abs() < 1e-9).all()
assert ((border_sums - 1).abs() < 1e-9).all()

# Every node must appear as a target
assert set(weights["target"]) == set(nodes["node_id"])

# 9.5 Export
weights.to_csv(DIR + "geographic_weights.csv", index=False)

print("Number of directed edges:", len(weights))
print("Number of target nodes:", weights["target"].nunique())
print(weights.head())
